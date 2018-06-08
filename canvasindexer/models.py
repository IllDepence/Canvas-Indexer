from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()


class TermCurationAssoc(db.Model):
    __tablename__ = 'term_curation_assoc'
    term_id = db.Column('term_id', db.Integer, db.ForeignKey('term.id'),
                        primary_key=True)
    curation_id = db.Column('curation_id', db.Integer,
                            db.ForeignKey('curation.id'), primary_key=True)
    # FIXME: allow for multiple assocs for a term curation pair if metadata
    #        type or actor is different (i.e. extend primary key)
    #        (currently no prob b/c only canvas metadata and language split
    #        between actors types)
    #        when changed has to be reflected in lo['term_cur_assoc_list']
    metadata_type = db.Column('metadata_type', db.String(255))
    actor = db.Column('actor', db.String(255))
    term = db.relationship('Term')
    curation = db.relationship('Curation')


class TermCanvasAssoc(db.Model):
    __tablename__ = 'term_canvas_assoc'
    term_id = db.Column('term_id', db.Integer, db.ForeignKey('term.id'),
                        primary_key=True)
    canvas_id = db.Column('canvas_id', db.Integer, db.ForeignKey('canvas.id'),
                          primary_key=True)
    # FIXME: allow for multiple assocs for a term canvas pair if metadata
    #        type or actor is different (i.e. extend primary key)
    #        (currently no prob b/c only canvas metadata and language split
    #        between actors types)
    #        when changed has to be reflected in lo['term_can_assoc_list']
    metadata_type = db.Column('metadata_type', db.String(255))
    actor = db.Column('actor', db.String(255))
    term = db.relationship('Term')
    canvas = db.relationship('Canvas')


class Term(db.Model):
    __tablename__ = 'term'
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(255))
    qualifier = db.Column(db.String(255))
    __table_args__ = (db.UniqueConstraint('term', 'qualifier'), )
    canvases = db.relationship('TermCanvasAssoc')
    curations = db.relationship('TermCurationAssoc')


class Canvas(db.Model):
    __tablename__ = 'canvas'
    id = db.Column(db.Integer, primary_key=True)
    canvas_uri = db.Column(db.String(2048), unique=True)  # ID + # [+ fragment]
    json_string = db.Column(db.UnicodeText())
    terms = db.relationship('TermCanvasAssoc')


class Curation(db.Model):
    __tablename__ = 'curation'
    id = db.Column(db.Integer, primary_key=True)
    curation_uri = db.Column(db.String(2048), unique=True)
    # ↑ ID + term + m.d.typ.[1]
    json_string = db.Column(db.UnicodeText())
    terms = db.relationship('TermCurationAssoc')
    # [1] the reason for storing each curation once per associated term is that
    #     depending on the search term their representation as a search result
    #     (e.g. thumbnail) is different
    #     furthermore the type of metadata (curation top level vs. canvas) is
    #     used to distinguish between those two kinds of search results


class CrawlLog(db.Model):
    __tablename__ = 'crawllog'
    log_id = db.Column(db.Integer(), autoincrement=True, primary_key=True)
    # datetime = db.Column(db.DateTime(timezone=True),
    #                      server_default=func.now())
    # ↓ saved as isoformat string to ease integration with JSONkeeper AS
    datetime = db.Column(db.UnicodeText())
    new_canvases = db.Column(db.Integer())


class FacetList(db.Model):
    __tablename__ = 'facetlist'
    id = db.Column(db.Integer(), autoincrement=True, primary_key=True)
    json_string = db.Column(db.UnicodeText())


class CanvasParentMap(db.Model):
    __tablename__ = 'canvasparentmap'
    id = db.Column(db.Integer(), autoincrement=True, primary_key=True)
    json_string = db.Column(db.UnicodeText())
