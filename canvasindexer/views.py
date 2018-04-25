import json
import uuid
import requests
from collections import OrderedDict
from flask import (abort, Blueprint, current_app, redirect, request, jsonify,
                   Response, url_for, render_template)
from util.iiif import Curation as CurationObj
from canvasindexer.models import (db, Term, Canvas, Curation,
                                  TermCanvasAssoc, TermCurationAssoc)

pd = Blueprint('pd', __name__)


def combine(cr1, cr2):
    """ Combine a Curation metadata and a Canvas metadata based Curation search
        result.
    """

    if cr1['curationHit']:
        has_cur = cr1
        has_can = cr2
    else:
        has_cur = cr2
        has_can = cr1
    has_cur['canvasHit'] = has_can['canvasHit']
    return has_cur


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
        canvases = Canvas.query.join('terms', 'term').filter(Term.term == q)
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

    # parse request arguments
    q = request.args.get('q', False)
    prprty = request.args.get('property', False)
    value = request.args.get('value', False)
    if not (q or (prprty and value)):
        return abort(400, 'No query or property value pair given.')
    source = request.args.get('source', 'canvas')
    if source in ['curation|canvas', 'canvas|curation']:
        granularity = 'curation'
    else:
        granularity = request.args.get('granularity', source)
        if granularity not in ['canvas', 'curation']:
            granularity = 'canvas'
    if request.args.get('fuzzy') == 'false':
        fuzzy = False
    else:
        fuzzy = True
    start = int(request.args.get('start', 0))
    limit = int(request.args.get('limit', -1))

    # start building response
    ret = OrderedDict()
    if q:
        ret['query'] = q
    else:
        ret['property'] = prprty
        ret['value'] = value
    ret['granularity'] = granularity
    ret['source'] = source
    ret['fuzzy'] = fuzzy

    # select tables
    results = []
    if granularity == 'canvas':
        Doc = Canvas
        Assoc = TermCanvasAssoc
    elif granularity == 'curation':
        Doc = Curation
        Assoc = TermCurationAssoc

    # filter records
    docs = Doc.query.join('terms', 'term')
    if source not in ['curation|canvas', 'canvas|curation']:
        docs = docs.filter(Assoc.metadata_type == source)
    if q:
        if fuzzy:
            docs = docs.filter(Term.term.ilike('%{}%'.format(q)))
        else:
            docs = docs.filter(Term.term == q)
    elif prprty:
        if fuzzy:
            docs = docs.filter(Term.term.ilike('%{}%'.format(value)),
                               Term.qualifier == prprty)
        else:
            docs = docs.filter(Term.term == value, Term.qualifier == prprty)

    if docs:
        all_results = [json.loads(doc.json_string,
                                  object_pairs_hook=OrderedDict)
                       for doc in docs]
        if granularity == 'curation':
            # combine curation and canvas hits
            unique_cur_urls = []
            merged_results = []
            for r in all_results:
                dupes = [d for d in all_results
                                    if d['curationUrl'] == r['curationUrl']]
                if len(dupes) == 2:
                    if r['curationUrl'] not in unique_cur_urls:
                        merged_results.append(combine(*dupes))
                else:
                    merged_results.append(r)
                unique_cur_urls.append(r['curationUrl'])
            all_results = merged_results
    else:
        all_results = []

    # finish building response
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

    cur = CurationObj(str(uuid.uuid4()), label)
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
