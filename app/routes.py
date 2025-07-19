from app import app
from flask import render_template, redirect, request
from flask_sqlalchemy import SQLAlchemy
from os import path
from math import log


basedir = path.abspath(path.dirname(__file__))
db = SQLAlchemy()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + path.join(basedir,
                                                                 "main.db")
db.init_app(app)

from app import crawler # noqa


@app.route('/')
def home():
    print("Hit")
    return render_template('base.html')


@app.route('/admin/documents')
def admin():
    return render_template('admin_documents.html')


# Okapi BM25 search based of Medium article by Emma Park
# https://medium.com/@readwith_emma/understanding-okapi-bm25-document-ranking-algorithm-70d81adab001
@app.route('/search/<query>')
def okapi_search(query):
    # Saturation Parameter
    # (Sets how much a word appearing in a document improves it's score)
    k = 1.2

    # Make query set to avoid duplicate work for the same word
    set_words = set(query.split('_'))
    n_docs = db.session.query(crawler.models.Document).count()
    document_rankings = {}

    for word in set_words:
        # lemma is root word of word e. steamed -> steam
        lemma = crawler.lemmatizer.lemmatize(word.lower())
        word_obj = db.session.query(crawler.models.Keyword).filter_by(word=lemma).first()  # noqa
        if bool(word_obj):
            # freq_total = word_obj.frequency
            connections = db.session.query(crawler.models.KeywordDocument).filter_by(word_id=word_obj.word_id) # noqa
            n_with_word = connections.count()
            # Inverse Document Frequency
            # It measures specificity of word across docs
            idf = log((n_docs - n_with_word + 0.5)/(n_with_word + 0.5)+1)
            for doc in connections.all():
                frequency = doc.frequency
                score = idf * (frequency*k+1) / ((frequency + k))
                doc_id = doc.document_id
                document_rankings[doc_id] = document_rankings.get(doc_id, 0) + score # noqa
    results = []

    for doc_id in document_rankings.keys():
        doc_query = db.session.query(crawler.models.Document).filter_by(document_id=doc_id).first() # noqa
        results.append((document_rankings[doc_id],
                        doc_query.link,
                        doc_query.title,
                        doc_query.source,
                        doc_query.intro
                        ))
    print(results)

    return render_template('results.html', title="Search", results=results, query=" ".join(query.split('_')))


@app.route('/insert_docs')
def insert_docs():
    if request.method == 'POST':
        html = request.form.get('html')
        url = request.form.get('url')
        crawler.start_scraping_documents([(html, 0, url)])

        return redirect('/')


@app.route('/insert_pdf', methods=['POST'])
def insert_pdf():
    if request.method == 'POST':
        pdf = request.files['pdf']
        url = request.form.get('url')
        crawler.start_scraping_documents([(pdf, 2, url)])
        return redirect('/')
