""" Canvas Indexer

    A flask web application that crawls Activity Streams for IIIF Canvases and
    offers a search API.
"""

from flask import Flask
from flask_cors import CORS
from canvasindexer.config import Cfg


def create_app(**kwargs):
    app = Flask(__name__)
    with app.app_context():
        CORS(app)
        app.cfg = Cfg()

        app.config['SQLALCHEMY_DATABASE_URI'] = app.cfg.db_uri()
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        from canvasindexer.models import db
        db.init_app(app)
        db.create_all()

        from canvasindexer.views import pd
        app.register_blueprint(pd)

        return app
