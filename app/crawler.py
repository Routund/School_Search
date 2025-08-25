from nltk.stem import SnowballStemmer
from urllib import request, parse
from bs4 import BeautifulSoup
import threading
from app import app
import app.models as models
from app.routes import db
from string import punctuation
import easyocr
from enum import Enum
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import os
from google_auth_oauthlib.flow import InstalledAppFlow
import time

# need to import wordnet
# Uncomment lines below when running the first time
#
# import nltk
# nltk.download('wordnet')

pages_to_parse = []
problematic = []
translator = str.maketrans(' ', ' ', punctuation)
reader = easyocr.Reader(['en'])

threads = []
stemmer = SnowballStemmer("english")


class problematic_file():

    def __init__(self, link, error, time):
        self.link = link
        self.error = error
        self.time = time
        pass


class parse_type(Enum):
    WEBPAGE = 0
    HTML = 1
    PDF = 2


class parse_input():
    def __init__(self, link, source_id, type=parse_type.WEBPAGE, pdf_bytes=None):
        self.link = link
        self.type = type
        self.pdf_bytes = pdf_bytes
        self.source_id = source_id


def page_parsing_routine_thread():
  with app.app_context():
    i = 0
    while i < len(pages_to_parse):
        current_item: parse_input = pages_to_parse[i]
        url = current_item.link
        text = ""

        # Query to check if the document already exists
        q_doc = db.session.query(models.Document).filter_by(link=url).first()

        title = ""
        source = ""

        if current_item.type == parse_type.WEBPAGE:
            result = scrape_webpage(url, current_item.source_id)
            if not isinstance(result, dict):
                problematic.append(problematic_file(url, result, time.asctime))
                i += 1
                continue
            else:
                text = result["text"]
                title = result["title"]

        # If the document has already been checked within a week, skip it.
        if bool(q_doc):
            if q_doc.last_time + 604800 > time.time():
                i += 1
                continue

        dict_words = index(text.translate(translator).split())

        if not bool(q_doc):
            # Path that runs if document doesn't exist
            new_document = models.Document()
            new_document.title = title
            new_document.source = current_item.source_id
            new_document.intro = text[0:min(len(text)-1, 100)] + "..."
            new_document.link = url
            new_document.length = dict_words[1]
            new_document.last_time = time.time()

            db.session.add(new_document)
            db.session.commit()
            doc_id = new_document.document_id
            for word in dict_words[0]:
                freq = dict_words[0][word]
                q_word = db.session.query(models.Keyword).filter_by(word=word).first() # noqa
                word_id = 0
                if not bool(q_word):
                    # Add the word to the database if it doesn't exist
                    word_id = insert_new_word(word=word, frequency=freq)

                else:
                    # Update cumulative frequency of given word
                    word_id = q_word.word_id
                    q_word.frequency = q_word.frequency + freq
                    db.session.commit()

                insert_keyword_doc(doc_id, word_id, freq)
        else:
            # Path that runs if document does exist
            doc_id = q_doc.document_id

            # Used to store whatever words were previously indexed
            # Is useful to know which word document pairs need to be removed
            prev_connections = [x.word_id for x in q_doc.words]

            for word in dict_words[0]:
                freq = dict_words[0][word]
                q_word = db.session.query(models.Keyword).filter_by(word=word).first()
                word_id = None

                if not bool(q_word):
                    # Add the word to the database if it doesn't exist
                    word_id = insert_new_word(word=word, frequency=freq)
                else:
                    # Update cumulative frequency of given word
                    # If already connected, remove the connected frequency
                    # so that total count stays accurate.
                    word_id = q_word.word_id
                    if word_id in prev_connections:
                        # Used to keep track of which previous words are left
                        # So that the connections that are left
                        # can be deleted at end
                        prev_connections.remove(word_id)
                        q_connection = db.session.query(models.KeywordDocument).filter_by(document_id=doc_id, word_id=word_id).first()
                        if q_connection.frequency == freq:
                            continue
                        q_word.frequency -= q_connection.frequency
                        q_word.frequency += freq
                        q_connection.frequency = freq
                        db.session.commit()

                insert_keyword_doc(doc_id, word_id, freq)

            # Delete indexed words not in document anymore
            for conn_left in prev_connections:
                conn = db.session.query(models.KeywordDocument).filter_by(document_id=doc_id, word_id=conn_left).first()
                word = db.session.query(models.Keyword).filter_by(word_id=conn.word_id).first()
                word.frequency -= conn.frequency
                # Prune orphaned words not connected to any document
                if word.frequency == 0:
                    db.session.delete(word)
                db.session.delete(conn)

            q_doc.last_time = time.time()
            db.session.commit()
        i += 1
    pages_to_parse.clear()


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


def scrape_webpage(url: str, source_id):
    try:
        link = request.Request(url)
        # Get full HTML of a given website
        response = request.urlopen(link)
        source = parse.urlsplit(url).netloc
        htmlbytes = response.read()
        htmlstr = htmlbytes.decode("utf8")

        # Take out only the text
        soup = BeautifulSoup(htmlstr, "html.parser")
        str_clean = soup.get_text(separator=' ', strip=True)

        # Get all links out of the page, and it they are in same domain
        # add them to list of links to parse
        # (Check for domain to avoid accidentaly scraping the entire web)
        anchors = soup.find_all('a')
        baseurl: parse.SplitResult = parse.urlsplit(url)
        baseurl = baseurl._replace(path="", query="", fragment="")
        baseurl = parse.urlunsplit(baseurl)
        # urllist is a list of all pages previously parsed, this is present
        # to prevent repeat links being added to parse
        urllist = [x.link for x in pages_to_parse]
        for a in anchors:
            href = a.get("href", default=" ")
            domain = parse.urlsplit(href).netloc
            if not bool(domain):
                # If no domain is present, check if the href is a relative link
                # And not a link to a section on the page
                if href[0] == '/':
                    total_link = "".join([baseurl, href])
                    if total_link not in urllist:
                        pages_to_parse.append(parse_input(link=total_link), source_id=source_id)
            elif domain == source:
                if href not in urllist:
                    pages_to_parse.append(parse_input(href, source_id=source_id))

        return {
            "text": str_clean,
            "title": soup.title.text,
            "source": source}
    except Exception as e:
        print(e)
        return e


SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly"]


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


# Helper function to add new words to the database
def insert_new_word(word, frequency):
    with app.app_context():
        new_word = models.Keyword()
        new_word.word = word
        new_word.frequency = frequency
        db.session.add(new_word)
        db.session.commit()
        return new_word.word_id


# Helper function to add new connections to database
def insert_keyword_doc(doc, word, frequency):
    with app.app_context():
        KeywordDocument = models.KeywordDocument()
        KeywordDocument.document_id = doc
        KeywordDocument.word_id = word
        KeywordDocument.frequency = frequency
        db.session.add(KeywordDocument)
        db.session.commit()


def new_source(url, source_id):
    parse_obj = parse_input(link=url, source_id=source_id)
    pages_to_parse.append(parse_obj)
    if len(threads) > 0:
        if threads[0].is_alive():
            return
        else:
            threads.clear()
    t1 = threading.Thread(target=page_parsing_routine_thread)
    threads.append(t1)
    threads[0].start()
    pass
