from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()


class TermCurationAssoc(db.Model):
    __tablename__ = 'term_curation_assoc'
    term_id = db.Column('term_id', db.Integer, db.ForeignKey('term.id'),
                        primary_key=True)
    curations_id = db.Column('curation_id', db.Integer,
                             db.ForeignKey('curation.id'), primary_key=True)
    metadata_type = db.Column('metadata_type', db.String(255))
    actor = db.Column('actor', db.String(255))
    term = db.relationship('Term', back_populates='curations')
    curation = db.relationship('Curation', back_populates='terms')


class TermCanvasAssoc(db.Model):
    __tablename__ = 'term_canvas_assoc'
    term_id = db.Column('term_id', db.Integer, db.ForeignKey('term.id'),
                        primary_key=True)
    canvas_id = db.Column('canvas_id', db.Integer, db.ForeignKey('canvas.id'),
                          primary_key=True)
    metadata_type = db.Column('metadata_type', db.String(255))
    actor = db.Column('actor', db.String(255))
    term = db.relationship('Term', back_populates='canvases')
    canvas = db.relationship('Canvas', back_populates='terms')


class Term(db.Model):
    __tablename__ = 'term'
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(255))
    qualifier = db.Column(db.String(255))
    __table_args__ = (db.UniqueConstraint('term', 'qualifier'), )
    canvases = db.relationship('TermCanvasAssoc', back_populates='term')
    curations = db.relationship('TermCurationAssoc', back_populates='term')


class Canvas(db.Model):
    __tablename__ = 'canvas'
    id = db.Column(db.Integer, primary_key=True)
    canvas_uri = db.Column(db.String(2048), unique=True)
    json_string = db.Column(db.UnicodeText())
    terms = db.relationship('TermCanvasAssoc', back_populates='canvas')


class Curation(db.Model):
    __tablename__ = 'curation'
    id = db.Column(db.Integer, primary_key=True)
    curation_uri = db.Column(db.String(2048), unique=True)
    json_string = db.Column(db.UnicodeText())
    terms = db.relationship('TermCurationAssoc', back_populates='curation')


class CrawlLog(db.Model):
    __tablename__ = 'crawllog'
    log_id = db.Column(db.Integer(), autoincrement=True, primary_key=True)
    datetime = db.Column(db.DateTime(timezone=True), server_default=func.now())
    new_canvases = db.Column(db.Integer())


class FacetList(db.Model):
    __tablename__ = 'facetlist'
    id = db.Column(db.Integer(), autoincrement=True, primary_key=True)
    json_string = db.Column(db.UnicodeText())
