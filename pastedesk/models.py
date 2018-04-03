from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()


class TermEntry(db.Model):
    __tablename__ = 'termentry'
    term = db.Column(db.String(255), primary_key=True)
    json_string = db.Column(db.UnicodeText())


class CrawlLog(db.Model):
    __tablename__ = 'crawllog'
    log_id = db.Column(db.Integer(), autoincrement=True, primary_key=True)
    datetime = db.Column(db.DateTime(timezone=True), server_default=func.now())
    new_entries = db.Column(db.Integer())
