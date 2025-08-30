from app import app
from flask import render_template, redirect, request, jsonify, session, abort
from flask_sqlalchemy import SQLAlchemy
from os import path
from math import log
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from key import key

basedir = path.abspath(path.dirname(__file__))
db = SQLAlchemy()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + path.join(basedir,
                                                                 "main.db")
db.init_app(app)

from app import crawler # noqa

app.secret_key = key


@app.errorhandler(404)
def not_found_error(error):
    return render_template('Errors.html',
                           Error='''Either we could not find the page,
                             or you do not have access to it'''), 404


@app.errorhandler(403)
def no_permission(error):
    return render_template('Errors.html',
                           Error='''Either we could not find the page,
                            or you do not have access to it'''), 403


@app.errorhandler(400)
def bad_request(error):
    return render_template('Errors.html',
                           Error='''Malformed request,
                           try logging out then logging back in'''), 400


@app.errorhandler(500)
def general_error(error):
    return render_template('Errors.html',
                           Error='''Something seemed to have gone wrong'''), 500


@app.route('/')
def home():
    if 'user' in session:
        return redirect('/search')
    return render_template('home.html')


@app.route('/admin/documents', methods=['POST', 'GET'])
def admin():
    if "user" not in session:
        abort(403)
    source_list = db.session.query(crawler.models.Source).all()
    ids = [x.source_id for x in source_list]
    names = [x.name for x in source_list]
    urls = [x.home_url for x in source_list]
    return render_template('admin_documents.html', ids=ids, names=names, urls=urls)


@app.route('/search')
def search_start():
    if "user" not in session:
        abort(403)
    return render_template('search.html', username=session["user"]["name"])


# Okapi BM25 search based of Medium article by Emma Park
# https://medium.com/@readwith_emma/understanding-okapi-bm25-document-ranking-algorithm-70d81adab001
@app.route('/search/<query>')
def okapi_search(query):
    if "user" not in session:
        abort(403)
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
                           query=" ".join(query.split('_')),
                           username=session["user"]["name"])


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


@app.route("/logout")
def logout():
    session.clear()
    return redirect('/')


@app.route("/login", methods =['POST'])
def login():
    token = request.args.get("credential") or request.form.get("credential")
    if not token:
        return "Missing token", 400

    try:
        idinfo = id_token.verify_oauth2_token(token,
                                              grequests.Request(),
                                              "436525077927-itvcusib54q0k3894qq7m3dta8nvunoi.apps.googleusercontent.com")

        # Extract claims
        email = idinfo.get("email")
        name = idinfo.get("name")
        domain = idinfo.get("hd")  # will be None for normal Gmail accounts

        # ✅ Enforce school domain
        if domain != "burnside.school.nz" and email != "routundity@gmail.com":
            return f"Access denied: {email} is not part of {"burnside.school.nz"}", 403

        # Save to session
        session["user"] = {
            "email": email,
            "name": name,
            "domain": domain
        }

        return redirect("/search")

    except ValueError as e:
        return f"Invalid token: {e}", 400


# Route to prevent Cross Site Scripting. Borrowed from
# https://stackoverflow.com/questions/63290047/flask-csp-content-security-policy-best-practice-against-attack-such-as-cross
@app.after_request
def add_security_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://accounts.google.com/gsi/client https://code.jquery.com/jquery-3.6.0.min.js;"
        "frame-src https://accounts.google.com/gsi/;"
        "connect-src 'self' https://accounts.google.com/gsi/; "
        "img-src 'self' https://accounts.google.com/gsi/;"
        "style-src 'self' https://accounts.google.com/gsi/style"
    )
    return resp
