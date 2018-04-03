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


@pd.route('/', methods=['GET', 'POST'])
def index():
    """ Index page.
    """

    # look for query
    q = False
    if request.method == 'POST' and request.form.get('q', False):
        q = request.form.get('q')

    # get index
    term_entries = TermEntry.query.all()
    index = {}
    for entry in term_entries:
        index[entry.term] = json.loads(entry.json_string)
    # select canvases
    docs = [v[0] for k, v in index.items() if not q or k == q]
    canvases = [(doc['can'], cutout_thumbnail(doc['img'], doc['can']))
                for doc in docs]

    return render_template('index.html', canvases=canvases)

