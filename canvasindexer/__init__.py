""" PasteDesk

    A flask web application for combining (pasting) pre cut IIIF Canvases into
    Curations.
"""

from flask import Flask
from canvasindexer.config import Cfg

def create_app(**kwargs):
    app = Flask(__name__)
    with app.app_context():
        app.cfg = Cfg()
        if kwargs:
            app.testing = True

        app.config['SQLALCHEMY_DATABASE_URI'] = app.cfg.db_uri()
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        from canvasindexer.models import db
        db.init_app(app)
        db.create_all()

        from canvasindexer.views import pd
        app.register_blueprint(pd)

        return app
