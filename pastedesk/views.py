import json
import uuid
import requests
from collections import OrderedDict
from flask import (abort, Blueprint, current_app, redirect, request, jsonify,
                   Response, url_for, render_template)
from util.iiif import Curation
from pastedesk.models import db, TermEntry, CrawlLog

pd = Blueprint('pd', __name__)


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
    num_docs = 0
    for entry in term_entries:
        doc_list = json.loads(entry.json_string)
        index[entry.term] = doc_list
        num_docs += len(doc_list)
    # select canvases
    docs = []
    for term, can_list in index.items():
        if not q or term == q:
            for doc in can_list:
                if not doc in docs:
                    docs.append(doc)
    canvases = [(doc['manifestUrl'],
                 '{}#{}'.format(doc['canvasId'], doc['fragment']),
                 doc['canvasThumbnail'])
                for doc in docs]


    status = ('&gt; Crawling canvas cutouts from: "{}".<br>&gt; Currently storing {} canva'
              'ses associated with {} keywords.<br>&gt; Available keywords: "{}"'
             ).format('", "'.join(current_app.cfg.as_sources()), num_docs,
                      len(index), '", "'.join(term for term in index.keys()))

    return render_template('index.html', canvases=canvases, status=status)

@pd.route('/api', methods=['GET'])
def api():

    q = request.args.get('q', False)
    if not q:
        return abort(400, 'No query given.')
    start = int(request.args.get('start', 0))
    limit = int(request.args.get('limit', -1))

    ret = OrderedDict()
    ret['query'] = q

    results = []
    term_entry = TermEntry.query.filter_by(term=q).first()
    if term_entry:
        all_results = json.loads(term_entry.json_string,
                                 object_pairs_hook=OrderedDict)
    else:
        all_results = []
    ret['total'] = len(all_results)
    ret['start'] = start
    results = all_results[start:]
    if limit >= 0:
        ret['limit'] = limit
        if len(results) > limit:
            results = results[0:limit]
    else:
        ret['limit'] = None

    ret['results'] = results

    resp = Response(json.dumps(ret, indent=4))
    resp.headers['Content-Type'] = 'application/json'
    return resp

# @pd.route('/build/', methods=['POST'])
def build():
    """ Build a Curation.
    """

    canvases = json.loads(request.form.get('json'))
    label = request.form.get('title')
    man_dict = {}
    for can in canvases:
        if not man_dict.get(can['man']):
            man_dict[can['man']] = []
        man_dict[can['man']].append(can['can'])

    cur = Curation(str(uuid.uuid4()), label)
    for within in man_dict.keys():
        cans = []
        for can in man_dict[within]:
            cans.append(cur.create_canvas(can))
        cur.add_and_fill_range(within, cans)

    headers = {'Accept': 'application/json',
               'Content-Type': 'application/ld+json'}
    resp = requests.post(current_app.cfg.curation_upload_url(),
                         headers=headers,
                         data=cur.get_json())

    if resp.status_code == 201:
        viewer_prefix = ('http://codh.rois.ac.jp/software/iiif-curation-viewer'
                         '/demo/?curation=')
        url = '{}{}'.format(viewer_prefix, resp.headers['Location'])
        return redirect(url)

    return redirect(url_for('pd.index'))
