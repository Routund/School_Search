from app import app
from flask import render_template, redirect, request, jsonify
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


@app.route('/admin/documents', methods=['POST', 'GET'])
def admin():
    source_list = db.session.query(crawler.models.Source).all()
    ids = [x.source_id for x in source_list]
    names = [x.name for x in source_list]
    urls = [x.home_url for x in source_list]
    return render_template('admin_documents.html', ids=ids, names=names, urls=urls)


@app.route('/search')
def search_start():
    return render_template('search.html')


# Okapi BM25 search based of Medium article by Emma Park
# https://medium.com/@readwith_emma/understanding-okapi-bm25-document-ranking-algorithm-70d81adab001
@app.route('/search/<query>')
def okapi_search(query):
    if query is None:
        return redirect('/search')
    # Saturation Parameter
    # (Sets how much a word appearing in a document improves it's score)
    k = 2

    # Make query set to avoid duplicate work for the same word
    set_words = set(query.split('_'))
    n_docs = db.session.query(crawler.models.Document).count()
    document_rankings = {}

    for word in set_words:
        # lemma is root word of word e. steamed -> steam
        lemma = crawler.stemmer.stem(word.lower().translate(crawler.translator))
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
                score = idf * frequency * (k+1) / ((frequency + k))
                doc_id = doc.document_id
                document_rankings[doc_id] = document_rankings.get(doc_id, 0) + score # noqa
    results = []

    for doc_id in document_rankings.keys():
        doc_query = db.session.query(crawler.models.Document).filter_by(document_id=doc_id).first() # noqa
        results.append((document_rankings[doc_id],
                        doc_query.link,
                        doc_query.title,
                        doc_query.source_obj.name,
                        doc_query.intro
                        ))

    return render_template('results.html',
                           title="Search",
                           results=reversed(sorted(results)),
                           query=" ".join(query.split('_')))


@app.route('/get_folders', methods=['POST'])
def get_folders():
    folder_list = crawler.get_folders_for_selection()
    return jsonify({'folders': folder_list})


@app.route('/new_source', methods=['POST'])
def new_source():
    data = request.get_json()
    url = data.get('url')
    name = data.get('name')

    q_source = db.session.query(crawler.models.Source).filter_by(name=name).first()
    if bool(q_source):
        return jsonify({'status': 'name_present'})

    q_source = db.session.query(crawler.models.Source).filter_by(home_url=url).first()
    if bool(q_source):
        return jsonify({'status': 'url_present'})

    new_source = crawler.models.Source()
    new_source.home_url = url
    new_source.name = name
    db.session.add(new_source)
    db.session.commit()

    source_id = new_source.source_id

    crawler.new_source(url, source_id)
    return jsonify({'status': 'success'})


# @app.route('/insert_pdf', methods=['POST'])
# def insert_pdf():
#     if request.method == 'POST':
#         pdf = request.files['pdf']
#         url = request.form.get('url')
#         crawler.start_scraping_documents([(pdf, 2, url)])
#         return redirect('/')
