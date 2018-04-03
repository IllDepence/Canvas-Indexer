import json
from flask import (abort, Blueprint, current_app, redirect, request, jsonify,
                   Response, url_for)
from util.iiif import Curation
from pastedesk.models import TermEntry, CrawlLog

pd = Blueprint('pd', __name__)


@pd.route('/')
def index():
    """ Index page.
    """

    resp = Response('index foo bar')
    return resp, 200

