import json
from flask import (abort, Blueprint, current_app, redirect, request, jsonify,
                   Response, url_for, render_template)
from util.iiif import Curation
from pastedesk.models import db, TermEntry, CrawlLog

pd = Blueprint('pd', __name__)


def cutout_thumbnail(iiif_img_uri, iiif_canvas_uri):
    can_uri_parts = iiif_canvas_uri.split('#xywh=')
    fragment = 'full'
    if len(can_uri_parts) == 2:
        fragment = can_uri_parts[1]
    thumb_uri = iiif_img_uri.replace('full/full', '{}/!300,300'.format(fragment))
    return thumb_uri


@pd.route('/')
def index(methods=['GET', 'POST']):
    """ Index page.
    """

    if request.method == 'POST':
        pass

    term_entries = TermEntry.query.all()
    index = {}
    for entry in term_entries:
        index[entry.term] = json.loads(entry.json_string)
    docs = [x[0] for x in index.values()]
    all_canvases = [(doc['can'], cutout_thumbnail(doc['img'], doc['can']))
                    for doc in docs]

    return render_template('index.html', canvases=all_canvases)

