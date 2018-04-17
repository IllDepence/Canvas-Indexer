from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()


class TermCanvasAssoc(db.Model):
    __tablename__ = 'term_canvas_assoc'
    term_id = db.Column('term_id', db.Integer, db.ForeignKey('term.id'),
                        primary_key=True)
    canvas_id = db.Column('canvas_id', db.Integer, db.ForeignKey('canvas.id'),
                          primary_key=True)
    assoc_type = db.Column('assoc_type', db.String(255))
    term = db.relationship('Term', back_populates='canvases')
    canvas = db.relationship('Canvas', back_populates='terms')


class Term(db.Model):
    __tablename__ = 'term'
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(255), unique=True)
    canvases = db.relationship('TermCanvasAssoc', back_populates='term')


class Canvas(db.Model):
    __tablename__ = 'canvas'
    id = db.Column(db.Integer, primary_key=True)
    canvas_uri = db.Column(db.String(2048), unique=True)
    json_string = db.Column(db.UnicodeText())
    terms = db.relationship('TermCanvasAssoc', back_populates='canvas')


class CrawlLog(db.Model):
    __tablename__ = 'crawllog'
    log_id = db.Column(db.Integer(), autoincrement=True, primary_key=True)
    datetime = db.Column(db.DateTime(timezone=True), server_default=func.now())
    new_canvases = db.Column(db.Integer())
