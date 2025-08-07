from app.routes import db


class Document(db.Model):
    __tablename__ = "Document"
    document_id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String())
    title = db.Column(db.String(50))
    intro = db.Column(db.Text())
    source = db.Column(db.INTeger(50))
    length = db.Column(db.Integer)

    words = db.relationship('KeywordDocument', back_populates='Document',
                            foreign_keys='KeywordDocument.document_id')

    def __str__(self):
        return self.title


class Keyword(db.Model):
    __tablename__ = "Keyword"
    word_id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(30))
    frequency = db.Column(db.Integer)

    documents = db.relationship('KeywordDocument', back_populates='Word',
                                foreign_keys='KeywordDocument.word_id')

    def __str__(self):
        return self.word


class KeywordDocument(db.Model):
    __tablename__ = "KeywordDocument"

    id = db.Column(db.Integer, primary_key=True)
    frequency = db.Column(db.Integer)
    document_id = db.Column(db.Integer, db.ForeignKey('Document.document_id'),
                            primary_key=True)
    word_id = db.Column(db.Integer, db.ForeignKey('Keyword.word_id'))

    Word = db.relationship('Keyword', back_populates='documents')
    Document = db.relationship('Document', back_populates='words')

    def __str__(self):
        return self.word_id + ' ' + self.document_id

calss Source(db.Model):
    __table_name__ = "Source"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String("50"))
    drive_id = db.Column(db.String("80"))
    creds = db.Column(db.Json)
