from flask import Flask,render_template,session
import crawler


app = Flask(__name__)

@app.route('/')
def home():
    return render_template('base.html',title = "Search")

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/search/<query>')
def okapi_search(query):
    list_words = set(query.split('_'))
    
    document_rankings = {}

if __name__ == "__main__":
    app.run(debug=True)