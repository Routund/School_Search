from nltk.stem import WordNetLemmatizer
from string import punctuation
from urllib import request
from bs4 import BeautifulSoup
from re import sub

# need to import wordnet
# Uncomment lines below when running the first time
#
# import nltk
# nltk.download('wordnet')


def index(text_to_crawl: list) -> dict:
    # Dictionary to contain frequency of each word in the document
    raw_word_freqs = {
    }

    for word in text_to_crawl:
        raw_word_freqs[word.lower()] = raw_word_freqs.get(word.lower(), 0) + 1

    # Dictionary to contain frequency of each lemma (root word) in the document
    word_freqs = {
    }

    lemmatizer = WordNetLemmatizer()

    for key in raw_word_freqs.keys():
        lemma = lemmatizer.lemmatize(key)
        word_freqs[lemma] = word_freqs.get(lemma, 0) + raw_word_freqs[key]

    print(word_freqs)

    return word_freqs

def scrape_webpage(url : str):

    link = request.Request(url)
    
    try:
        # Get full HTML of a given website
        response = request.urlopen(link)
        htmlbytes = response.read()
        htmlstr = htmlbytes.decode("utf8")

        # Take out only the text
        soup = BeautifulSoup(htmlstr,"html.parser")
        str_clean = soup.get_text()

        return str_clean
    except:
        print("Unable to open page")
        return ""


# translator = str.maketrans(' ', ' ', punctuation)

# inp = scrape_webpage("https://www.burnside.school.nz/explore-burnside/vision-and-values/").translate(translator).split()

# index(inp)