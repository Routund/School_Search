from app import app
from flask import render_template, redirect
from flask_sqlalchemy import SQLAlchemy
from os import path

basedir = path.abspath(path.dirname(__file__))
db = SQLAlchemy()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + path.join(basedir,
                                                                 "main.db")
db.init_app(app)

from app import crawler # noqa


@app.route('/')
def home():
    print("Hit")
    return render_template('base.html', title="Search")


@app.route('/admin')
def admin():
    return render_template('admin.html')


@app.route('/search/<query>')
def okapi_search(query):
    set_words = set(query.split('_'))

    # document_rankings = {}

    for word in set_words:
        pass

    return list(set_words)


@app.route('/insert_docs')
def insert_docs():
    crawler.start_scraping_documents(['https://www.burnside.school.nz/enrol/'])
    return redirect('/')
