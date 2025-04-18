from nltk.stem import WordNetLemmatizer
from re import split

# need to import wordnet
# Uncomment lines below when running the first time
#
# import nltk
# nltk.download('wordnet')


def index(text_to_crawl: list) -> list:
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


inp = split(' |,|\n |\.|;|"|-|\'|\'s', input())  # noqa:W605

index(inp)
