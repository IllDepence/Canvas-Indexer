from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()


term_canvas_assoc = db.Table('term_canvas_assoc',
              db.Column('term_id', db.Integer, db.ForeignKey('term.id')),
              db.Column('canvas_id', db.Integer, db.ForeignKey('canvas.id')))


class Term(db.Model):
    __tablename__ = 'term'
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(255), unique=True)
    canvases = db.relationship('Canvas',
                               secondary=term_canvas_assoc,
                               back_populates='terms')


class Canvas(db.Model):
    __tablename__ = 'canvas'
    id = db.Column(db.Integer, primary_key=True)
    canvas_uri = db.Column(db.String(2048), unique=True)
    json_string = db.Column(db.UnicodeText())
    terms = db.relationship('Term',
                            secondary=term_canvas_assoc,
                            back_populates='canvases')


class CrawlLog(db.Model):
    __tablename__ = 'crawllog'
    log_id = db.Column(db.Integer(), autoincrement=True, primary_key=True)
    datetime = db.Column(db.DateTime(timezone=True), server_default=func.now())
    new_canvases = db.Column(db.Integer())
