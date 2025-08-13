from nltk.stem import SnowballStemmer
from urllib import request, parse
from bs4 import BeautifulSoup
import threading
from app import app
import app.models as models
from app.routes import db
from string import punctuation
import easyocr
from pypdf import PdfReader
from io import BytesIO
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os
from google_auth_oauthlib.flow import InstalledAppFlow
import json

# need to import wordnet
# Uncomment lines below when running the first time
#
# import nltk
# nltk.download('wordnet')

documents_to_parse = []
folders_to_parse = []
problematic = []
translator = str.maketrans(' ', ' ', punctuation)
reader = easyocr.Reader(['en'])


class file_query_result():

    def __init__(self, id, name, link):
        self.id = id
        self.name = name
        self.link = link


def scraping_thread_folders():
    i = 0
    with app.app_context():
        while i < len(folders_to_parse):
            folder_id = folders_to_parse[i]
            q_folder = db.session.query(models.Source).filter_by(source_id=folder_id).first()

            # Check folder exists
            if not bool(q_folder):
                problematic.append(folder_id)
                i += 1
                continue

            # Get important info about folder
            folder_drive_id = q_folder.drive_id
            # We load the json twice, once to remove \\'s
            # And again to make it to a dict
            creds = Credentials.from_authorized_user_info(json.loads(json.loads(q_folder.creds)))
            files_to_search = get_files_in_folder(folder_drive_id, creds)
            stored_files = [x.document_id for x in q_folder.documents]

            for file_result in files_to_search:
                # Convert the bytes that google docs gives documents as to pdfs
                file_bytes = get_file_from_drive(file_result.id, creds)
                file_bytes.seek(0, os.SEEK_END)
                reader = PdfReader(file_bytes)

                text = ""
                for j in range(len(reader.pages)):
                    text = text + reader.pages[j].extract_text(0)

                # Get all words out of pdf
                dict_words = index(text.translate(translator).split())
                # Query to check if the document already exists
                q_document = db.session.query(models.Document).filter_by(link=file_result.link).first()
                if not bool(q_document):
                    # Path that runs if document doesn't exist
                    new_document = models.Document()
                    new_document.title = file_result.name
                    new_document.source = folder_id
                    new_document.intro = text[0:min(len(text)-1, 100)] + "..."
                    new_document.link = file_result.link
                    new_document.length = dict_words[1]

                    db.session.add(new_document)
                    db.session.commit()
                    doc_id = new_document.document_id
                    for word in dict_words[0]:
                        freq = dict_words[0][word]
                        q_word = db.session.query(models.Keyword).filter_by(word=word).first() # noqa
                        word_id = 0
                        if not bool(q_word):
                            word_id = insert_new_word(word=word, frequency=freq)

                        else:
                            word_id = q_word.word_id
                            q_word.frequency = q_word.frequency + freq
                            db.session.commit()

                        insert_keyword_doc(doc_id, word_id, freq)
                else:
                    # Path that runs if document does exist
                    doc_id = q_document.document_id
                    if doc_id in stored_files:
                        stored_files.remove(doc_id)
                    prev_connections = [x.word_id for x in q_document.words]
                    for word in dict_words[0]:
                        freq = dict_words[0][word]
                        q_word = db.session.query(models.Keyword).filter_by(word=word).first()
                        word_id = None
                        if not bool(q_word):
                            word_id = insert_new_word(word=word, frequency=freq)
                        else:
                            word_id = q_word.word_id
                            if word_id in prev_connections:
                                prev_connections.remove(word_id)
                                q_connection = db.session.query(models.KeywordDocument).filter_by(document_id=doc_id, word_id=word_id).first()
                                if q_connection.frequency == freq:
                                    continue
                                q_word.frequency -= q_connection.frequency
                                q_word.frequency += freq
                                q_connection.frequency = freq
                                db.session.commit()
                                continue
                        insert_keyword_doc(doc_id, word_id, freq)

                    # Delete indexed words not in document anymore
                    for conn_left in prev_connections:
                        conn = db.session.query(models.KeywordDocument).filter_by(document_id=doc_id, word_id=conn_left).first()
                        word = db.session.query(models.Keyword).filter_by(word_id=conn.word_id).first()
                        word.frequency -= conn.frequency
                        if word.frequency == 0:
                            db.session.delete(word)
                        db.session.delete(conn)
                        db.session.commit()

            # Delete all the indexed files that aren't in the folder anymore
            for file_left in stored_files:
                doc = db.session.query(models.Document).filter_by(document_id=file_left).first()
                words = [x.word_id for x in doc.words]
                for word_id in words:
                    conn = db.session.query(models.KeywordDocument).filter_by(document_id=doc.document_id, word_id=word_id).first()
                    word_obj = db.session.query(models.Keyword).filter_by(word_id=word_id).first()
                    word_obj.frequency -= conn.frequency
                    db.session.delete(conn)
                    if word_obj.frequency == 0:
                        db.session.delete(word_obj)
                db.session.commit()
                db.session.delete(doc)
                db.session.commit()
            del creds
            del q_folder
            i += 1
    folders_to_parse.clear()
    return None


threads = []
stemmer = SnowballStemmer("english")


def index(text_to_crawl: list) -> dict:
    # Dictionary to contain frequency of each word in the document
    raw_word_freqs = {
    }

    for word in text_to_crawl:
        raw_word_freqs[word.lower()] = raw_word_freqs.get(word.lower(), 0) + 1

    # Dictionary to contain frequency of each lemma (root word) in the document
    word_freqs = {
    }

    for key in raw_word_freqs.keys():
        lemma = stemmer.stem(key)
        word_freqs[lemma] = word_freqs.get(lemma, 0) + raw_word_freqs[key]

    print(word_freqs)

    return (word_freqs, len(raw_word_freqs.keys()))


def scrape_webpage(url: str):

    link = request.Request(url)

    try:
        # Get full HTML of a given website
        response = request.urlopen(link)
        source = parse.urlsplit(url).netloc
        htmlbytes = response.read()
        htmlstr = htmlbytes.decode("utf8")

        # Take out only the text
        soup = BeautifulSoup(htmlstr, "html.parser")
        str_clean = soup.get_text()

        return (str_clean, soup.title.text, source)
    except Exception as e:
        print("Unable to open page: " + e)
        return 0


def start_scraping_folders(list_folders: str):
    folders_to_parse.extend(list_folders)
    if len(threads) > 0:
        if threads[0].is_alive():
            return
        else:
            threads.clear()
    t1 = threading.Thread(target=scraping_thread_folders)
    threads.append(t1)
    threads[0].start()
    pass


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_credentials():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(creds.to_json())
    return creds


# Borrowed from https://www.merge.dev/blog/get-folders-google-drive-api
def get_folders_for_selection():
    folders = []

    try:
        service = build("drive", "v3", credentials=get_credentials())
        page_token = None

        while True:
            # Call the Drive v3 API
            results = (
                service.files()
                .list(q="mimeType = 'application/vnd.google-apps.folder'",
                        spaces="drive",
                        fields="nextPageToken, files(id, name)",
                        pageToken=page_token)
                .execute()
            )
            items = results.get("files", [])
            for item in items:
                folders.append((item['id'], item['name']))

            if page_token is None:
                break
    except HttpError as error:
        print(f"An error occurred: {error}")
    return folders


def get_files_in_folder(folder_id, creds):
    try:
        service = build("drive", "v3", credentials=creds)

        files = []

        # Call the Drive v3 API
        results = (
            service.files()
            .list(q=f"'{folder_id}' in parents",
                  pageSize=10,
                  fields="nextPageToken, files(id, name, webViewLink)")
            .execute()
        )

        items = results.get("files", [])

        if not items:
            print("No files found.")
            return None
        print("Files:")
        for item in items:
            new_file = file_query_result(id=item['id'],
                                         name=item['name'],
                                         link=item['webViewLink'])
            files.append(new_file)
            print(f"{item['name']} ({item['id']})")
        return files
    except HttpError as error:
        # TODO(developer) - Handle errors from drive API.
        print(f"An error occurred: {error}")
        return None


def get_file_from_drive(file_id, creds):
    try:
        # create drive api client
        service = build("drive", "v3", credentials=creds)

        # pylint: disable=maybe-no-member
        request = service.files().export_media(
            fileId=file_id, mimeType="application/pdf"
        )
        file = BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        print(f"Download {int(status.progress() * 100)}.")

    except HttpError as error:
        print(f"An error occurred: {error}")
        return None

    return file


def add_folder(name, drive_id, creds):
    with app.app_context():
        new_source = models.Source()
        new_source.name = name
        new_source.drive_id = drive_id
        new_source.creds = creds
        db.session.add(new_source)
        db.session.commit()

# '1OmfhGwLpSEQ2KwZgsiAN3lBIR2TlSSU2'

# inp = scrape_webpage("https://www.burnside.school.nz/explore-burnside/vision
# -and-values/").translate(translator).split()

# index(inp)

# res = get_folders_for_selection()[0]

# print(res)


def insert_new_word(word, frequency):
    with app.app_context():
        new_word = models.Keyword()
        new_word.word = word
        new_word.frequency = frequency
        db.session.add(new_word)
        db.session.commit()
        return new_word.word_id


def insert_keyword_doc(doc, word, frequency):
    with app.app_context():
        KeywordDocument = models.KeywordDocument()
        KeywordDocument.document_id = doc
        KeywordDocument.word_id = word
        KeywordDocument.frequency = frequency
        db.session.add(KeywordDocument)
        db.session.commit()
