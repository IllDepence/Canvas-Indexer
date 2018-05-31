import json
import uuid
import requests
from collections import OrderedDict
from flask import (abort, Blueprint, current_app, redirect, request,
                   Response, url_for, render_template)
from util.iiif import Curation as CurationObj
from canvasindexer.crawler.crawler import crawl
from canvasindexer.api.models import (Term, Canvas, Curation, FacetList,
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
    """ Index page. Only accessible when running in debug mode.
    """

    if not current_app.debug:
        return abort(404)

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

    status = ('&gt; Crawling canvas cutouts from: "{}".<br>&gt; Currently stor'
              'ing {} canvases associated with {} keywords.<br>&gt; Available '
              'keywords: "{}"'
             ).format('", "'.join(current_app.cfg.as_sources()),
                      len(all_canvases),
                      len(all_terms),
                      '", "'.join(term.term for term in all_terms)
                     )

    return render_template('index.html', canvases=canvas_digests,
                           status=status)


@pd.route('/facets', methods=['GET'])
def facets():
    """ Facets. Returns an overview of the indexed metadata.
    """

    db_entry = FacetList.query.first()
    if db_entry:
        facet_list = json.loads(db_entry.json_string,
                                object_pairs_hook=OrderedDict)
    else:
        facet_list = {'facets': []}

    resp = Response(json.dumps(facet_list, indent=4))
    resp.headers['Content-Type'] = 'application/json'
    return resp


@pd.route('/api', methods=['GET'])
def api():
    """ Search API.
    """

    # parse request arguments
    # select
    select = request.args.get('select', 'curation')
    if select not in ['curation', 'canvas']:
        return abort(400, 'Parameter "select" must be either "curation" or "ca'
                          'nvas" or not set.')
    # from
    valid_froms = True
    from_default = 'curation,canvas'
    vrom = request.args.get('from', 'curation,canvas')
    if vrom == '':
        vrom = from_default
    for v in vrom.split(','):
        if v not in ['curation', 'canvas']:
            valid_froms = False
    if not valid_froms:
        return abort(400, 'Parameter "from" must be a comma seperated list (le'
                          'ngth >= 1), containing only the terms "curation" an'
                          'd "canvas".')
    # where*
    where = request.args.get('where', False)
    where_metadata_label = request.args.get('where_metadata_label', False)
    where_metadata_value = request.args.get('where_metadata_value', False)
    if (where and where_metadata_label and where_metadata_value) or \
            (where_metadata_label and not where_metadata_value) or \
            (where_metadata_value and not where_metadata_label):
        return abort(400, 'You can either set parameter "where" or set both pa'
                          'rameters "where_metadata_label" and "where_metadata'
                          '_value')
    valid_where_agent = True
    where_agent_detault = 'human,machine'
    where_agent = request.args.get('where_agent', where_agent_detault)
    if where_agent == '':
        where_agent = where_agent_detault
    for wa in where_agent.split(','):
        if wa not in ['human', 'machine']:
            valid_where_agent = False
    if not valid_where_agent:
        return abort(400, 'Parameter "where_agent" must be a comma seperated l'
                          'ist (length >= 1), containing only the terms "human'
                          '" and "machine".')
    if where:
        fuzzy = True
    else:
        fuzzy = False
    start = int(request.args.get('start', 0))
    limit = int(request.args.get('limit', -1))

    # start building response
    ret = OrderedDict()
    ret['select'] = select
    ret['from'] = vrom
    if where:
        ret['where'] = where
    else:
        ret['where_metadata_label'] = where_metadata_label
        ret['where_metadata_value'] = where_metadata_value
    ret['where_agent'] = where_agent
    # ret['fuzzy'] = fuzzy

    # select tables
    results = []
    if select == 'canvas':
        Doc = Canvas
        Assoc = TermCanvasAssoc
    elif select == 'curation':
        Doc = Curation
        Assoc = TermCurationAssoc

    # filter records
    docs = Doc.query
    assocs = Assoc.query
    terms = Term.query
    if vrom not in ['curation,canvas', 'canvas,curation']:
        assocs = assocs.filter(Assoc.metadata_type == vrom)
    if where_agent in ['human,machine', 'machine,human']:
        # NOTE: this should actually filter for 'human' or 'machine' or
        # 'unknown', but in its current, controlled application setup there are
        # no values except those three, so we just skip the filtering to avoid
        # unnecessary processing
        pass
    elif where_agent == 'human':
        # the Canvas Indexer crawling process accepts any type of 'agent'
        # value for metadata and sets it to 'unknown' if not specified.
        # the API endpoint, however, currently limits queries to the values
        # 'human' and 'machine' *but* adds the assumption that unknown
        # agents are humans.
        assocs = assocs.filter((Assoc.actor == 'human') |
                               (Assoc.actor == 'unknown'))
    else:
        assocs = assocs.filter(Assoc.actor == where_agent)
    if where:
        if fuzzy:
            terms = terms.filter(Term.term.ilike('%{}%'.format(where)))
        else:
            terms = terms.filter(Term.term == where)
    elif where_metadata_label:
        if fuzzy:
            terms = terms.filter(Term.term.ilike('%{}%'.format(
                                                          where_metadata_value
                                                              )),
                                 Term.qualifier == where_metadata_label)
        else:
            terms = terms.filter(Term.term == where_metadata_value,
                                 Term.qualifier == where_metadata_label)

    docs = docs.join(assocs).join(terms).all()

    if docs:
        if select == 'curation':
            # because of result combining we "need" to go through all results
            #
            # (first selecting for curations with limit applied (if given) and
            # then looking for corresponding canvas results is probably faster)
            all_results = [json.loads(doc.json_string,
                                      object_pairs_hook=OrderedDict)
                           for doc in docs]
            # combine curation and canvas hits
            unique_cur_urls = []
            merged_results = []
            for r in all_results:
                if r['curationLabel'] == ('A mere container for machine tagged'
                                          ' cavanses'):
                    # FIXME: dirty solution to keep "container" curations (that
                    #        only contain canvases + machine generated tags)
                    #        out of search results
                    #        using canvases directly doesn't work here because
                    #        the original canvas url needs to be preserved for
                    #        associating the tags with the canvas
                    #
                    #        solution: use ranges an containers (requires some
                    #        work in the crawling process)
                    continue
                dupes = [d for d in all_results
                         if d['curationUrl'] == r['curationUrl']]
                if len(dupes) == 2:
                    if r['curationUrl'] not in unique_cur_urls:
                        merged_results.append(combine(*dupes))
                elif len(dupes) > 2:
                    # FIXME: 1. this can be done more efficient
                    if r['curationUrl'] not in unique_cur_urls:
                        has_cur = None
                        has_can = None
                        for cr in dupes:
                            if cr['curationHit']:
                                has_cur = cr
                            else:
                                has_can = cr
                            if has_cur and has_can:
                                break
                        if has_cur and has_can:
                            merged_results.append(combine(has_cur, has_can))
                        else:
                            merged_results.append(cr)
                else:
                    merged_results.append(r)
                unique_cur_urls.append(r['curationUrl'])
            all_results = merged_results
            # apply start & limit
            results = all_results[start:]
            if limit >= 0 and len(results) > limit:
                results = results[0:limit]
        else:
            # for canvases, there is no result joining, so we can use start
            # and limit to reduce the amount of result JSON string parsing
            all_results = docs  # later only used for len(all_results)
            results = []
            for i, doc in enumerate(docs):
                if limit >= 0 and i<start:
                    continue
                if limit >= 0 and i>=start+limit:
                    break
                results.append(json.loads(doc.json_string,
                                          object_pairs_hook=OrderedDict))
    else:
        all_results = []

    # finish building response
    ret['total'] = len(all_results)
    ret['start'] = start
    if limit >= 0:
        ret['limit'] = limit
    else:
        ret['limit'] = None

    ret['results'] = results

    resp = Response(json.dumps(ret, indent=4))
    resp.headers['Content-Type'] = 'application/json'
    return resp


@pd.route('/crawl', methods=['GET'])
def crawl_endpoint():
    """ Crawl trigger.
    """

    crawl()

    ret = {'message': 'done'}
    resp = Response(json.dumps(ret, indent=4))
    resp.headers['Content-Type'] = 'application/json'
    return resp


# @pd.route('/build/', methods=['POST'])
def build():
    """ Build a Curation.

        Currently disabled. Could be enabled for debug mode (like index) but
        has to be tested first.
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
