import json
import uuid
import requests
from collections import OrderedDict
from flask import (abort, Blueprint, current_app, redirect, request, jsonify,
                   Response, url_for, render_template)
from util.iiif import Curation
from canvasindexer.models import db, Term, Canvas

pd = Blueprint('pd', __name__)


@pd.route('/', methods=['GET', 'POST'])
def index():
    """ Index page.
    """

    # look for query
    q = False
    if request.method == 'POST' and request.form.get('q', False):
        q = request.form.get('q')

    all_canvases = Canvas.query.all()
    all_terms = Term.query.all()

    if q:
        canvases = Canvas.query.filter(Canvas.terms.any(term=q)).all()
    else:
        canvases = all_canvases

    canvas_dicts = [json.loads(can.json_string) for can in canvases]
    canvas_digests = [(can['manifestUrl'],
                      '{}#{}'.format(can['canvasId'], can['fragment']),
                      can['canvasThumbnail'])
                      for can in canvas_dicts]


    status = ('&gt; Crawling canvas cutouts from: "{}".<br>&gt; Currently storing {} canva'
              'ses associated with {} keywords.<br>&gt; Available keywords: "{}"'
             ).format('", "'.join(current_app.cfg.as_sources()),
                      len(all_canvases),
                      len(all_terms),
                      '", "'.join(term.term for term in all_terms)
                     )

    return render_template('index.html', canvases=canvas_digests,
                           status=status)

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
    canvases = Canvas.query.filter(Canvas.terms.any(term=q)).all()
    if canvases:
        all_results = [json.loads(can.json_string,
                                  object_pairs_hook=OrderedDict)
                       for can in canvases]
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
