from app import app
from flask import render_template, redirect, request, jsonify, session, abort
from flask import url_for
from flask_sqlalchemy import SQLAlchemy
from os import path
from math import log
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from json import loads as jsloads
from google_auth_oauthlib.flow import InstalledAppFlow
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
                           Error='Something seemed to have gone wrong'), 500


@app.route('/')
def home():
    if 'user' in session:
        return redirect('/search')
    return render_template('home.html')


@app.route('/admin/documents', methods=['POST', 'GET'])
def admin():

    if "user" not in session:
        abort(403)

    # Get list of all current sources
    source_list = db.session.query(crawler.models.Source).all()
    ids = [x.source_id for x in source_list]
    names = [x.name for x in source_list]
    urls = [x.home_url for x in source_list]

    return render_template('admin_documents.html', ids=ids, names=names, urls=urls) # noqa


@app.route('/search/')
def search_redirecter():
    return redirect('/search')


@app.route('/search')
def search_start():
    if "user" not in session:
        abort(403)
    return render_template('search.html', username=session["user"]["name"])


# Okapi BM25 search based of Medium article by Emma Park
# https://medium.com/@readwith_emma/understanding-okapi-bm25-document-ranking-algorithm-70d81adab001
# parameters such as k and idf are taken
# from the mathematical formula for okapi search
@app.route('/search/<query>')
def okapi_search(query):
    if len(query) > 100:
        abort(400)
    if "user" not in session:
        abort(403)
    if not bool(query):
        return redirect('/search')

    creds = get_credentials()
    if isinstance(creds, str):
        return redirect(creds)

    # Saturation Parameter
    # (Sets how much a word appearing in a document improves it's score)
    k = 2

    # Make query set to avoid duplicate work for the same word
    set_words = set(query.split('_'))
    n_docs = db.session.query(crawler.models.Document).count()
    document_rankings = {}

    for word in set_words:
        # lemma is root word of word e. steamed -> steam
        lemma = crawler.stemmer.stem(word.lower().translate(crawler.translator)) # noqa
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

    google_files = get_files_from_query(creds, " ".join(query.split('_')))

    if bool(google_files):
        for file in google_files:
            results.append((
                0.1,
                file["link"],
                file["name"],
                "Google Drive",
                "No Preview Available"
            ))

    results = list(reversed(sorted(results)))

    return render_template('results.html',
                           title="Search",
                           results=results,
                           query=" ".join(query.split('_')),
                           username=session["user"]["name"])


@app.route('/new_source', methods=['POST'])
def new_source():
    data = request.get_json()
    url = data.get('url')
    name = data.get('name')

    q_source = db.session.query(crawler.models.Source).filter_by(name=name).first() # noqa
    if bool(q_source):
        return jsonify({'status': 'name_present'})

    q_source = db.session.query(crawler.models.Source).filter_by(home_url=url).first() # noqa
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


@app.route("/login", methods=['POST'])
def login():
    token = request.args.get("credential") or request.form.get("credential")
    if not token:
        return "Missing token", 400

    try:
        # Load credentials to get the client_id
        with open('authentication2.json', 'r') as f:
            auth_info = jsloads(f.read())
            client_id = auth_info["web"].get("client_id")
            if not client_id:
                return abort(500)

        # Validate the ID token with the client_id
        idinfo = id_token.verify_oauth2_token(token, grequests.Request(), client_id) # noqa

        # Extract claims
        email = idinfo.get("email")
        name = idinfo.get("name")
        domain = idinfo.get("hd")

        # Enforce school domain
        if domain != "burnside.school.nz" and email != "routundity@gmail.com":
            abort(403)

        # Save to session
        session["user"] = {
            "email": email,
            "name": name
        }
        session["queries"] = {}

        return redirect("/search")

    except ValueError as e:
        print(e)
        abort(400)
    except FileNotFoundError:
        abort(500)


SCOPES = ["https://www.googleapis.com/auth/drive.metadata.readonly",
          "https://www.googleapis.com/auth/userinfo.profile",
          "openid",
          "https://www.googleapis.com/auth/userinfo.email"
          ]


def get_credentials():
    creds = None
    user = db.session.query(crawler.models.User).filter_by(email=session['user']['email']).first() # noqa
    if bool(user):
        # We load the json twice, once to remove \\'s
        # And again to make it to a dict
        creds_data = jsloads(user.creds)
        creds = Credentials.from_authorized_user_info(creds_data, scopes=SCOPES) # noqa
        # creds_dict = jsloads(user.creds)
        # creds = Credentials.from_authorized_user_info(info={
        #     'refresh_token': creds_dict['refresh_token'],
        #     'client_id': creds_dict['client_id'],
        #     'client_secret': creds_dict['client_secret']
        #     },
        #     scopes=SCOPES
        #     )
    else:
        user = crawler.models.User()
        db.session.add(user)
        user.email = session['user']['email']
        user.name = session['user']['name']

        # This part handles the initial authorization for new or invalid creds
    flow = InstalledAppFlow.from_client_secrets_file(
        "authorization2.json", SCOPES,
        redirect_uri=url_for('callback_route', _external=True)
    )

    if creds:
        if creds.expired and creds.refresh_token:
            creds.refresh(grequests.Request())
            user.creds = creds.to_json()
            db.session.commit()
        if creds.valid:
            return creds

    # If we have an auth code, exchange it for tokens
    if 'code' in request.args:
        try:
            flow.fetch_token(code=request.args.get('code'))
            creds = flow.credentials
            user.creds = creds.to_json()
            db.session.commit()
            return creds
        except Exception as e:
            # Handle token exchange errors gracefully
            print(f"Error during token exchange: {e}")

            return None
    else:
        # No auth code, so redirect the user to the authorization URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            approval_prompt='force'
        )
        print(f"Redirecting user to: {authorization_url}")
        return authorization_url


def get_files_from_query(creds, query):
    try:
        service = build("drive", "v3", credentials=creds)
        files = []
        page_token = session['queries'].get(query, None)

        # Call the Drive v3 API
        results = (
            service.files().list(
                q=f"fullText contains '{query}'",
                # and visibility = 'domainCanFind'
                pageSize=10,
                fields="nextPageToken, files(id, name, webViewLink)",
                pageToken=page_token
                ).execute()
        )

        items = results.get("files", [])
        nextPageToken = results.get("nextPageToken")
        session['queries'][query] = nextPageToken
        session.modified = True
        if not items:
            print("No files found.")
            return None
        print("Files:")
        for item in items:
            new_file = {
                        "name": item['name'],
                        "link": item['webViewLink']
                        }
            files.append(new_file)
            print(f"{item['name']} ({item['id']})")
        return files
    except Exception as error:
        # TODO(developer) - Handle errors from drive API.
        print(f"An error occurred: {error}")
        return None


@app.route('/files_extend', methods=['POST'])
def fetch_files_extended():
    data = request.get_json()
    query = data.get('query')
    creds = get_credentials()
    if isinstance(creds, str):
        return jsonify({'status': 'error'})
    # Check if there is a valid next page to get files from
    if session['queries'].get(query, None) is None:
        return jsonify({'status': 'error'})
    google_files = get_files_from_query(creds, " ".join(query.split('_')))
    files = []
    if bool(google_files):
        for file in google_files:
            files.append((
                0.1,
                file["link"],
                file["name"],
                "Google Drive",
                "No Preview Available"
            ))
    return jsonify({'status': 'success',
                   'files': files
                    })


@app.route('/reparse', methods=['POST'])
def reparse():
    data = request.get_json()
    try:
        source_id = data.get('source_id')
        url = db.session.query(crawler.models.Source).filter_by(source_id=source_id).first().home_url  # noqa
        crawler.new_source(source_id=source_id, url=url)
        return jsonify({'status': 'success'})
    except Exception as e:
        print(e)
        return jsonify({'status': 'error'})


@app.route('/callback')
def callback_route():
    # This route will get the 'code' from the URL query parameters
    creds = get_credentials()

    if creds and creds.valid:
        return redirect('/search')
    else:
        # Handle the error case
        abort(500)


# Function to prevent Cross Site Scripting. Borrowed from
# https://stackoverflow.com/questions/63290047/flask-csp-content-security-policy-best-practice-against-attack-such-as-cross
@app.after_request
def add_security_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://accounts.google.com/gsi/client https://code.jquery.com/jquery-3.6.0.min.js;" # noqa
        "frame-src https://accounts.google.com/gsi/;"
        "connect-src 'self' https://accounts.google.com/gsi/; "
        "img-src 'self' https://accounts.google.com/gsi/;"
        "style-src 'self' https://accounts.google.com/gsi/style"
    )
    return resp
