""" Canvas Indexer

    A flask web application that crawls Activity Streams for IIIF Canvases and
    offers a search API.
"""

import atexit
from flask import Flask
from flask_cors import CORS
from canvasindexer.config import Cfg
from canvasindexer.crawler.crawler import crawl
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger


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

        from canvasindexer.api.views import pd
        app.register_blueprint(pd)

        if app.cfg.crawler_interval() > 0:
            crawl()
            scheduler = BackgroundScheduler()
            scheduler.start()
            scheduler.add_job(
                func=crawl,
                trigger=IntervalTrigger(seconds=app.cfg.crawler_interval()),
                id='crawl_job',
                name='crawl AS with interval set in config',
                replace_existing=True)
            atexit.register(lambda: scheduler.shutdown())

        return app
