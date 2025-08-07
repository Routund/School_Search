from nltk.stem import WordNetLemmatizer, SnowballStemmer
from urllib import request, parse
from bs4 import BeautifulSoup
import threading
from app import app
import app.models as models
from app.routes import db
from string import punctuation
# from pypdf import PdfReader
from pdf2image import convert_from_bytes
import easyocr
from numpy import array
from io import BytesIO
import google.auth
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
problematic = []
translator = str.maketrans(' ', ' ', punctuation)
reader = easyocr.Reader(['en'])

class file_query_result():

    def __init__(self,id,name,link):
        self.id=id
        self.name=name
        self.link=link


def scraping_thread():
    i = 0
    while i < len(documents_to_parse):
        url = ""
        url_or_html = documents_to_parse[i][1]
        result = []

        # This means that the input data is a url
        if url_or_html == 1:
            url = documents_to_parse[i][0]
            # results is list of [text, title, source]
            result = scrape_webpage(url)

            # Check if error is thrown when trying to fetch info from website
            if result == 0:
                problematic.append(url)
                i += 1
                continue
        # This means that the input is a pdf
        elif url_or_html == 2:
            pdf_image = convert_from_bytes(documents_to_parse[i][0].read())
            total_text = ""
            for page_number, page_data in enumerate(pdf_image):
                pdf_array = array(page_data)
                results = reader.readtext(pdf_array, detail=0)
                for detected_string in results:
                    total_text = total_text + " " + detected_string

            url = documents_to_parse[i][2]
            result = (total_text, documents_to_parse[i][0].filename[:-4], parse.urlsplit(url).netloc)
        # This means that document is straight html
        else:
            soup = BeautifulSoup(documents_to_parse[i][0], "html.parser")
            result = (soup.get_text(), soup.title.text, parse.urlsplit(documents_to_parse[i][2]).netloc)
            url = documents_to_parse[i][2]
        with app.app_context():
            # Returns tuple of (dictionary_words, length of document)
            dict_words = index(result[0].translate(translator).split())

            new_document = models.Document()
            new_document.title = result[1]
            new_document.source = result[2]
            new_document.intro = result[0][0:min(len(result[0])-1, 100)] + "..." # noqa
            new_document.link = url
            new_document.length = dict_words[1]

            db.session.add(new_document)
            db.session.commit()
            doc_id = new_document.document_id

            for word in dict_words[0]:
                q = db.session.query(models.Keyword).filter_by(word=word).first() # noqa
                word_id = 0
                if not bool(q):
                    new_word = models.Keyword()
                    new_word.word = word
                    new_word.frequency = dict_words[0][word]
                    db.session.add(new_word)
                    db.session.commit()
                    word_id = new_word.word_id

                else:
                    word_id = q.word_id
                    q.frequency = q.frequency + dict_words[0][word]
                    db.session.commit()

                KeywordDocument = models.KeywordDocument()
                KeywordDocument.document_id = doc_id
                KeywordDocument.word_id = word_id
                KeywordDocument.frequency = dict_words[0][word]
                db.session.add(KeywordDocument)
                db.session.commit()
        i += 1

    documents_to_parse.clear()
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


def start_scraping_documents(list_urls: str):
    documents_to_parse.extend(list_urls)
    if len(threads) > 0:
        if threads[0].is_alive():
            return
        else:
            threads.clear()
    t1 = threading.Thread(target=scraping_thread)
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
                folders.append((item['id'],item['name']))

            if page_token is None:
                break
    except HttpError as error:
        print(f"An error occurred: {error}")
    return folders


def get_files_in_folder(folder_id):
    try:
        service = build("drive", "v3", credentials=get_credentials())

        files = []

        # Call the Drive v3 API
        results = (
            service.files()
            .list(q=f"'{folder_id}' in parents", pageSize=10, fields="nextPageToken, files(id, name, webViewLink)")
            .execute()
        )
        
        items = results.get("files", [])

        if not items:
            print("No files found.")
            return
        print("Files:")
        for item in items:
            new_file = file_query_result(id=item['id'],name=items['name'])
            files.append(new_file)
            print(f"{item['name']} ({item['id']})")
    except HttpError as error:
        # TODO(developer) - Handle errors from drive API.
        print(f"An error occurred: {error}")


print(get_folders_for_selection())

# inp = scrape_webpage("https://www.burnside.school.nz/explore-burnside/vision
# -and-values/").translate(translator).split()

# index(inp)
