from app.routes import db


class Document(db.Model):
    __table_name__ = "Document"
    document_id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String())
    title = db.Column(db.String(50))
    intro = db.Column(db.Text())

    words = db.relationship('KeywordDocument', back_populates='document')

    def __str__(self):
        return self.title


class Keyword(db.Model):
    __tablename__ = "Keyword"
    word_id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(30))
    frequency = db.Column(db.Integer)

    documents = db.relationship('KeywordDocument', back_populates='word')

    def __str__(self):
        return self.word


class KeywordDocument(db.Model):
    __tablename__ = "KeywordDocument"

    frequency = db.Column(db.Integer())
    document_id = db.Column(db.Integer, db.ForeignKey('Document.document_id'),
                            primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('Keyword.word_id'),
                        primary_key=True)

    word = db.relationship('Keyword', back_populates='documents')
    document = db.relationship('Document', back_populates='words')

    def __str__(self):
        return self.word + ' ' + self.document
