from nltk.stem import SnowballStemmer
from urllib import request, parse
import requests as filerequest
from bs4 import BeautifulSoup
import threading
from app import app
import app.models as models
from app.routes import db
from string import punctuation
import easyocr
from enum import Enum
from io import BytesIO
import time
from os import SEEK_END
from pypdf import PdfReader

# need to import wordnet
# Uncomment lines below when running the first time
#
# import nltk
# nltk.download('wordnet')

pages_to_parse = []
problematic = []
translator = str.maketrans(' ', ' ', punctuation)
reader = easyocr.Reader(['en'])

parsing_threads = []
stemmer = SnowballStemmer("english")

searching_threads = []


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
    def __init__(self, link, source_id, type=parse_type.WEBPAGE, pdf_bytes=None): # noqa
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
            q_doc = db.session.query(models.Document).filter_by(link=url).first() # noqa
            title = ""
            if current_item.type == parse_type.WEBPAGE:
                result = scrape_webpage(url, current_item.source_id)
                if not isinstance(result, dict):
                    problematic.append(problematic_file(url,
                                                        result,
                                                        time.asctime))
                    i += 1
                    continue
                else:
                    text = result["text"]
                    title = result["title"]

            # If the document has already been checked within the last hour, skip it.
            if bool(q_doc):
                if q_doc.last_time + 3600 > time.time():
                    i += 1
                    continue

            if current_item.type == parse_type.PDF:
                result = scrape_pdf(url)
                if not isinstance(result, dict):
                    problematic.append(problematic_file(url,
                                                        result,
                                                        time.asctime))
                    i += 1
                    continue
                else:
                    text = result["text"]
                    title = result["title"]

            dict_words = index(text)
            dict_title = index(title)

            title_factor = int(dict_words[1] / 3) + 1
            for word in dict_title[0].keys():
                dict_words[0][word] = dict_words[0].get(word, 0) + title_factor

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
                        else:
                            q_word.frequency = q_word.frequency + freq
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
                db.session.commit(),
            i += 1
        pages_to_parse.clear()


alphanumeric = [
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
    'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0'
]


def index(text_to_crawl: str) -> dict:

    list_words = text_to_crawl.translate(translator).split()

    # Dictionary to contain frequency of each word in the document
    raw_word_freqs = {
    }

    for word in list_words:
        raw_word_freqs[word.lower()] = raw_word_freqs.get(word.lower(), 0) + 1

    # Dictionary to contain frequency of each lemma (root word) in the document
    word_freqs = {
    }

    for key in raw_word_freqs.keys():
        list_key = list(key)
        for i in range(len(list_key)):
            if list_key[i] not in alphanumeric:
                list_key[i] = ''
        stripped_key = "".join(list_key)
        if bool(stripped_key) and len(stripped_key) < 13:
            lemma = stemmer.stem(stripped_key)
            word_freqs[lemma] = word_freqs.get(lemma, 0) + raw_word_freqs[key]

    # print(word_freqs)

    return (word_freqs, len(raw_word_freqs.keys()))


def scrape_webpage(url: str, source_id):
    try:
        link = request.Request(url)
        # Get full HTML of a given website
        response = request.urlopen(link)
        source_split = parse.urlsplit(url)
        source_split = source_split._replace(path="", query="", fragment="")
        htmlbytes = response.read()
        htmlstr = htmlbytes.decode("utf8")

        # Take out only the text
        soup = BeautifulSoup(htmlstr, "html.parser")
        str_clean = soup.get_text(separator=' ', strip=True)

        # Get all links out of the page, and it they are in same domain
        # add them to list of links to parse
        # (Check for domain to avoid accidentaly scraping the entire web)
        anchors = soup.find_all('a')
        baseurl = db.session.query(models.Source).filter_by(source_id=source_id).first().home_url
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
                    source_split = source_split._replace(path=href)
                    total_link = parse.urlunsplit(source_split)
                    if total_link not in urllist:
                        add_link(total_link, source_id)
                        urllist.append(total_link)
            elif baseurl in href:
                if href not in urllist:
                    add_link(href, source_id)
                    urllist.append(href)

        return {
            "text": str_clean,
            "title": soup.title.text,
            }
    except Exception as e:
        print(e)
        return e


reader = easyocr.Reader(['en'])


def scrape_pdf(url: str):
    response = filerequest.get(url)
    file_bytes = BytesIO(response.content)
    file_bytes.seek(0, SEEK_END)
    pypdfReader = PdfReader(file_bytes)
    total_text = ""
    for j in range(len(pypdfReader.pages)):
        total_text = total_text + " " + pypdfReader.pages[j].extract_text(0)

    if bool(pypdfReader.metadata):
        if bool(pypdfReader.metadata.title):
            return {
                "text": total_text,
                "title": pypdfReader.metadata.title
            }

    # this path runs when the metadata is empty, or contains no title
    # it creates a title based off of the url
    url_title = []
    for i in reversed(range(len(url))):
        if url[i] != '/':
            url_title.insert(0, url[i])
        else:
            break
    url_title = "".join(url_title)
    return {
        "text": total_text,
        "title": url_title
    }


content_type_headers = [
    'content_type',
    'content-type',
]

opener = request.build_opener()
opener.addheaders = [('User-Agent', 'Burnside/1.0')]
request.install_opener(opener)


def add_link(link, source_id):
    try:
        # Check the headers of a link to see if data type is parsable
        # ie. a PDF, an HTML page, or an unsupported type
        header_test = request.urlopen(link)
        header_list = header_test.headers.items()
        final_type = None
        for header in header_list:
            if header[0].lower() in content_type_headers:
                content = header[1]
                if "text/html" in content:
                    final_type = parse_type.WEBPAGE
                    break
                if 'application/pdf' in content:
                    final_type = parse_type.PDF
                    break
        if not bool(final_type):
            return
        print(link)
        pages_to_parse.append(parse_input(link=link,
                                          source_id=source_id,
                                          type=final_type))
    except Exception as e:
        print(e)


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
    if doc is None or word is None:
        return
    with app.app_context():
        KeywordDocument = models.KeywordDocument()
        KeywordDocument.document_id = doc
        KeywordDocument.word_id = word
        KeywordDocument.frequency = frequency
        db.session.add(KeywordDocument)
        db.session.commit()


def new_source(url, source_id):
    add_link(url, source_id)
    if len(parsing_threads) > 0:
        if parsing_threads[0].is_alive():
            return
        else:
            parsing_threads.clear()
    t = threading.Thread(target=page_parsing_routine_thread)
    parsing_threads.append(t)
    parsing_threads[0].start()
    pass
