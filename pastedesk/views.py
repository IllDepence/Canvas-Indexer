import json
from flask import (abort, Blueprint, current_app, redirect, request, jsonify,
                   Response, url_for, render_template)
from util.iiif import Curation
from pastedesk.models import db, TermEntry, CrawlLog

pd = Blueprint('pd', __name__)


@pd.route('/')
def index():
    """ Index page.
    """

    term_entries = TermEntry.query.all()
    index = {}
    for entry in term_entries:
        index[entry.term] = json.loads(entry.json_string)
    all_canvases = [(doc['can'], doc['img']) for doc in [x[0] for x in index.values()]]
    status_msg = '<br>'.join(['{}, {}'.format(c[0], c[1]) for c in all_canvases])

    return render_template('index.html', status_msg=status_msg)

