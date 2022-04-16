import datetime
import dateutil.parser
import json
import re
import requests
import stat
import os
from collections import OrderedDict
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from canvasindexer.models import (db, Term, Canvas, Curation, FacetList,
                                  TermCanvasAssoc, TermCurationAssoc, CrawlLog,
                                  CanvasParentMap)
from canvasindexer.crawler.enhancer import post_job
from sqlalchemy import desc, not_
from canvasindexer.config import Cfg

cfg = Cfg()


def requests_retry_session(retries=5, backoff_factor=0.2,
                           status_forcelist=(500, 502, 504),
                           session=None):
    """ Method to use instead of requests.get to allow for retries during the
        crawling process. Ideally the crawler should, outside of this method,
        keep track of resources that could not be dereferenced, and offer some
        kind of way to retry for those resources at a later point in time (e.g.
        the next crawling run.

        Code from and discussion at:
        https://www.peterbe.com/plog/best-practice-with-retries-with-requests
    """

    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def build_facet_list():
    """ From the current DB state, pre build the response for requests to the
        /facets path.
    """

    terms = db.session.query(Term).filter(not_(Term.term == cfg.e_term()))
    terms = terms.join(TermCanvasAssoc)
    terms = terms.filter(TermCanvasAssoc.metadata_type == 'canvas').all()
    facet_map = {}
    for term in terms:
        if term.qualifier not in facet_map:
            facet_map[term.qualifier] = []
        if term.term not in facet_map[term.qualifier]:
            facet_map[term.qualifier].append(term.term)

    # create
    pre_facets = {}
    for label, vals in facet_map.items():
        assocs = db.session.query(TermCanvasAssoc).join(Term)
        assocs = assocs.filter(TermCanvasAssoc.metadata_type == 'canvas',
                               TermCanvasAssoc.term_id == Term.id,
                               Term.qualifier == label).all()
        facet = OrderedDict()
        facet['label'] = label
        # create
        facet['value'] = []
        for val in vals:
            unkown_count = 0
            human_count = 0
            machine_count = 0
            for a in assocs:
                if a.term.term == val:
                    if a.actor == 'human':
                        human_count += 1
                    elif a.actor == 'machine':
                        machine_count += 1
                    else:
                        # unkown_count += 1
                        human_count += 1
                        # Currently the API part of Canvas Indexer works with
                        # the assumption that unknown metadata is human
                        # generated. Since build_facet_list pre generates a
                        # reply of the API, unknown is treated as human here
                        # as well
        # agents are humans.
            # unknwon actor
            if unkown_count > 0:
                entry = OrderedDict()
                entry['label'] = val
                entry['value'] = unkown_count
                facet['value'].append(entry)
            # human actor
            if human_count > 0:
                entry = OrderedDict()
                entry['label'] = val
                entry['value'] = human_count
                entry['agent'] = 'human'
                facet['value'].append(entry)
            # machine actor
            if machine_count > 0:
                entry = OrderedDict()
                entry['label'] = val
                entry['value'] = machine_count
                entry['agent'] = 'machine'
                facet['value'].append(entry)
        # sort
        if label in cfg.facet_value_sort_alphanum():
            facet['value'] = sorted(facet['value'],
                                    key=lambda k: k['label'],
                                    reverse=False)
        elif label in cfg.facet_value_sort_frequency() or True:
            # default                                      ↑
            facet['value'] = sorted(facet['value'],
                                    key=lambda k: k['value'],
                                    reverse=True)
        if label in cfg.custom_value_sorts():
            # custom sorting is done in addition to freq/alhpanum, this means
            # that all values not specified in the custom sort will be sorted
            # as specified in the 'api' config section or according to the
            # default by frequency
            top_labels = cfg.custom_value_sorts()[label]['sort_top']
            bottom_labels = cfg.custom_value_sorts()[label]['sort_bottom']
            dictionary = OrderedDict()
            for item in facet['value']:
                dictionary[item['label']] = item
            facet['value'] = custom_sort(dictionary, top_labels, bottom_labels)

        pre_facets[label] = facet


    # order
    facets = custom_sort(pre_facets,
                         cfg.facet_label_sort_top(),
                         cfg.facet_label_sort_bottom())

    ret = {}
    ret['facets'] = facets

    return ret


def custom_sort(dictionary, sort_top_labels, sort_bottom_labels):
    """ Given a dictionary in the form of

            {'<a_label>': {
                          'label': '<a_label>'
                          'value': '<a_value>'
                          },
                          ...
            }

        and two lists (for top and bottom)

            ['<a_label>', '<c_label>', '<b_label>', ...]

        return a list of the dictonaries values ordered

            <all top items found in dictionary, in the given order>
            <others>
            <all bottom items found in dictionary, in the given order>
    """

    ret = []
    for l in sort_top_labels:
        if l in dictionary:
            ret.append(dictionary[l])
    for label, facet in dictionary.items():
        if label not in sort_top_labels + sort_bottom_labels:
            ret.append(facet)
    for l in sort_bottom_labels:
        if l in dictionary:
            ret.append(dictionary[l])
    return ret


def get_attrib_uri(json_dict, attrib):
    """ Get the URI for an attribute.
    """

    url = None
    if type(json_dict[attrib]) == str:
        url = json_dict[attrib]
    elif type(json_dict[attrib]) == dict:
        if json_dict[attrib].get('id', False):
            url = json_dict[attrib]['id']
        elif json_dict[attrib].get('@id', False):
            url = json_dict[attrib]['@id']
    return url


def get_referenced(json_dict, attrib):
    """ Get a value (of an attribute in a dict) that is not included in its
        entirety but just referenced by a URI or an object with a URI as its
        id.
    """

    url = get_attrib_uri(json_dict, attrib)

    try:
        resp = requests_retry_session().get(url)
        if resp.status_code != 200:
            raise
    except Exception as e:
        log('Could not dereference resource at {}. Error {}.'.format(
            url,
            e.__class__.__name__
            )
        )
        return '{}'

    return resp.json()


def get_img_compliance_level(profile):
    """ Try to figure out the IIIF Image API compliance level given the
        `profile` value from a info.json.
    """

    patt_iiif = re.compile('level([0-2])\.json$')
    patt_stan = re.compile('#level([0-2])$')

    def get_from_str(s):
        m = None
        if 'http://iiif.io/api/image/2/' in s:
            m = patt_iiif.search(s)
        elif 'http://library.stanford.edu/iiif/image-api/' in s:
            m = patt_stan.search(s)
        if m:
            return int(m.group(1))
        return -1

    lvl = -1
    if type(profile) == str:
        lvl = get_from_str(profile)
    elif type(profile) == list:
        for p in [x for x in profile if type(x) == str]:
            found = get_from_str(p)
            if found != -1:
                lvl = found
                break
    if lvl == -1:
        log('Could not find compliance level in info.json.')
    return lvl


def thumbnail_url(img_uri, canvas_uri, width, height, compliance_lvl,
                  canvas_dict):
    """ Create a URL for a thumbnail image.
    """

    can_uri_parts = canvas_uri.split('#xywh=')
    fragment = 'full'
    if len(can_uri_parts) == 2:
        fragment = can_uri_parts[1]
    if compliance_lvl >= 2:
        size = '!{},{}'.format(width, height)  # !200,200
    elif compliance_lvl == 1:
        size = '{},'.format(width)  # 200,
    elif compliance_lvl == 0:
        if canvas_dict.get('thumbnail'):
            # Special case that e.g. Getty uses. Example:
            # https://data.getty.edu/museum/api/iiif/287186/manifest.json
            return canvas_dict.get('thumbnail')
        else:
            size = 'full'
    else:
        size = '!{},{}'.format(width, height)  # compliance level unknown
    thumb_url = img_uri.replace('full/full', '{}/{}'.format(fragment, size))
    return thumb_url


def build_canvas_doc(man, cur_can):
    """ Given a manifest and canvas cutout dictionary, build a document
        (OrderedDict) with all information necessary to display the cutout as
        a search result.
    """

    doc = OrderedDict()
    doc['manifestUrl'] = man['@id']
    doc['manifestLabel'] = man['label']
    for seq in man.get('sequences', []):
        canvas_index = 1
        for man_can in seq.get('canvases', []):
            # if man_can['@id'] in cur_can['@id']:
            # ↑ this selects wrong pages for ID schemes like
            # http://dcollections.lib.keio.ac.jp/ [...] NRE/110X-444-2-2/page1
            # http://dcollections.lib.keio.ac.jp/ [...] NRE/110X-444-2-2/page10

            # ↓ this should always find a match, right?
            if man_can['@id'] == cur_can['@id'].split('#')[0]:
                # > canvas
                # info.json
                if man_can['images'][0]['resource'].get('service'):
                    service = man_can['images'][0]['resource'].get('service')
                    url_base = service['@id']
                #     ↑ maybe more robust than solution below?
                else:
                    mby_img_url = man_can['images'][0]['resource']['@id']
                    url_base = '/'.join(mby_img_url.split('/')[0:-4])
                #     ↑ if img resource @id in recommended format
                #       {scheme}://{server}{/prefix}/{identifier}/
                #       {region}/{size}/{rotation}/{quality}.
                #       {format}
                #       then [0:-4] cuts off /{size}/...{format}
                info_url = '{}/info.json'.format(url_base)
                doc['canvas'] = info_url
                try:
                    resp = requests_retry_session().get(info_url)
                    info_dict = resp.json()
                except Exception as e:
                    log(('Could not get info.json at {}.'
                         ' Error {}.').format(
                        info_url,
                        e.__class__.__name__
                        )
                    )
                    info_dict =  {}
                profile = info_dict.get('profile')
                quality = None
                quality_options = info_dict.get('qualities', [])
                if 'default' in quality_options:
                    quality = 'default'
                elif 'native' in quality_options:
                    quality = 'native'
                elif len(quality_options) > 0 and \
                     type(quality_options[0]) == str:
                    quality = quality_options[0]
                else:
                    quality = 'default'
                formad = None
                formad_options = info_dict.get('formats', [])
                if 'jpg' in formad_options:
                    formad = 'jpg'
                elif len(formad_options) > 0 and \
                     type(formad_options[0]) == str:
                    formad = formad_options[0]
                else:
                    formad = 'jpg'
                img_url = '{}/full/full/0/{}.{}'.format(info_dict.get('@id'),
                                                        quality,
                                                        formad)

                # > canvasId
                doc['canvasId'] = man_can['@id']
                # > canvasCursorIndex (CODH Cursor API specific)
                doc['canvasCursorIndex'] = man_can.get('cursorIndex', None)
                # > canvasLabel
                doc['canvasLabel'] = man_can.get('label')
                # > canvasThumbnail
                comp_lvl = get_img_compliance_level(profile)
                doc['canvasThumbnail'] = thumbnail_url(img_url, cur_can['@id'],
                                                       200, 200, comp_lvl,
                                                       man_can)
                # > canvasIndex
                doc['canvasIndex'] = canvas_index
                # > fragment
                url_parts = cur_can['@id'].split('#')
                if len(url_parts) == 2:
                    doc['fragment'] = url_parts[1]
                else:
                    doc['fragment'] = ''
                # > metadata
                if len(cur_can.get('metadata', [])) > 0:
                    doc['metadata'] = cur_can['metadata']

                # found the maching canvas, so there's no need to continue
                break
            canvas_index += 1

    return doc


def build_curation_doc(cur, activity, canvas_doc=None, cur_can_idx=None):
    """ Build a document (OrderedDict) with all information necessary to
        display a search result for a Curation.

        If canvas_doc is given, this is assumed to be a sarch result associated
        with Canvas metadata. Otherwise (search result associated with Curation
        top level metadata) the method enhance_top_meta_curation_doc is to be
        used to retroactively add missing information.
    """

    doc = OrderedDict()
    doc['curationUrl'] = cur['@id']
    doc['curationLabel'] = cur['label']
    if canvas_doc:
        doc['curationThumbnail'] = canvas_doc['canvasThumbnail']
    else:
        doc['curationThumbnail'] = None
    num_canvases = 0
    for ran in cur.get('selections', []):
        num_canvases += len(ran.get('members', []))
        num_canvases += len(ran.get('canvases', []))
    doc['totalImages'] = num_canvases
    if activity['type'] == 'Update':
        doc['crawledAt'] = activity['endTime']
    else:
        doc['crawledAt'] = datetime.datetime.utcnow().isoformat()
    # - - -
    if canvas_doc:
        canvas_hit = OrderedDict()
        canvas_hit['canvasId'] = canvas_doc['canvasId']
        canvas_hit['fragment'] = canvas_doc['fragment']
        canvas_hit['curationCanvasIndex'] = cur_can_idx + 1
        doc['curationHit'] = None
        doc['canvasHit'] = canvas_hit
    else:
        doc['curationHit'] = True
        doc['canvasHit'] = None

    return doc


def enhance_top_meta_curation_doc(cur_doc, canvas_doc):
    """ Retroactively add missing information to a Curation search result
        associated with Curation top level metadata.
    """

    cur_doc['curationThumbnail'] = canvas_doc['canvasThumbnail']


def build_qualifier_tuple(something):
    """ Given something, build a (<optional_qualifier>, <term>) tuple.

        This function is written to be able to deal with a wide range of
        metadata. This should hold throughout the indexing process. Other parts
        of the code, however, discard metadata that is not a list of dicts with
        a label and value (e.g. the preservation of metadata in result
        documents).
    """

    if type(something) == str:
        # 'foo' → ('', 'foo')
        return ('', something.strip())
    elif type(something) in [tuple, list]:
        # ['foo', 'bar', ...] / ('foo', 'bar', ...) → ('foo', 'bar')
        label = something[0]
        value = something[1]
        if type(label) == str and type(value) == str:
            return (something[0].strip(), something[1].strip())
    elif type(something) == dict:
        label = something.get('label')
        value = something.get('value')
        if (label == '' or label) and (value == '' or value):
            # {'label': 'foo', 'value': 'bar', ...} → ('foo', bar')
            if type(value) == str:
                return (label.strip(), value.strip())
            elif type(value) in [tuple, list]:
                return (label.strip(),
                        ', '.join([x.__repr__() for x in value]))
            else:
                return (label.strip(), value.__repr__())
        else:
            # {'foo': 'bar', ...} → ('foo', bar')
            return (list(something.keys())[0], list(something.values())[0])
    # <?> → ('', <?>.__repr__())
    return ('', '{}'.format(something))


def get_metadata_actor(something):
    """ Try to get actor/agent information from a piece of metadata.
    """

    fail = 'unknown'
    ret = fail
    if type(something) == dict:
        ret = something.get('agent', fail)
    return ret


def merge_iiif_doc_metadata(old_doc, new_doc):
    """ Given two IIIF documents (e.g. Canvases) as dictionaries, merge the
        contents of their `metadata` attribute on the root level.
        This assumes metadata to be a list of dictionaries with `label` and
        `value` keys as recommended in iiif.io/api/presentation/2.1/#metadata.
    """

    old_meta = old_doc.get('metadata', [])
    if type(old_meta) != list:
        old_meta = []
    new_meta = new_doc.get('metadata', [])
    if type(new_meta) != list:
        new_meta = []
    # clean
    result_meta = []
    seen = []
    for meta in old_meta + new_meta:
        if type(meta) != dict:
            continue
        label = meta.get('label')
        value = meta.get('value')
        if not label or not value:
            continue
        if (label, value) not in seen:
            result_meta.append(meta)
            seen.append((label, value))
    # sort
    sort_top_labels = cfg.facet_label_sort_top()
    sort_bottom_labels = cfg.facet_label_sort_bottom()
    top_bin = []
    center_bin = []
    bottom_bin = []
    for meta in result_meta:
        if meta['label'] in sort_top_labels:
            top_bin.append(meta)
        elif meta['label'] in sort_bottom_labels:
            bottom_bin.append(meta)
        else:
            center_bin.append(meta)
    result_meta = top_bin + center_bin + bottom_bin
    # assemble
    result_doc = old_doc
    result_doc['metadata'] = result_meta

    return result_doc


def log(msg):
    """ Write a log message.
    """

    timestamp = str(datetime.datetime.now()).split('.')[0]
    fn = cfg.crawler_log_file()
    # make /dev/stdout usable as log file
    # https://www.bugs.python.org/issue27805
    # side note: stat.S_ISCHR(os.stat(fn).st_mode) doesn't seem to work in an
    #            alpine linux docker container running canvas indexer with
    #            gunicorn although manually executing it on a python shell in
    #            the container works
    if fn == '/dev/stdout':
        mode = 'w'
    else:
        mode = 'a'
    with open(fn, mode) as f:
        f.write('[{}]   {}\n'.format(timestamp, msg))


def index_canvases_in_cur_selection(lo,
                                    cp_map,
                                    activity,
                                    cur,
                                    man,
                                    canvases,
                                    found_top_metadata,
                                    top_cur_db,
                                    top_doc_has_thumbnail,
                                    top_cur_doc,
                                    top_term,
                                    top_term_db_id,
                                    top_actor):
    """ Iterate over a list of Canvases in one of the ranges of a Curation, and
        write the resulting index entries into the DB.
    """

    new_canvases = 0
    for cur_can_idx, cur_can_dict in enumerate(canvases):
        log('canvas #{}'.format(cur_can_idx))
        # TODO: mby get read and include man[_can] metadata
        can_doc = build_canvas_doc(man, cur_can_dict)
        # ↓ canvas URIs w/o fragment end with a "#"
        can_uri = '{}#{}'.format(can_doc['canvasId'], can_doc['fragment'])
        can_cur_doc = build_curation_doc(cur, activity, can_doc,
                                     cur_can_idx)
        # Canvas parent map
        # # upward
        if can_uri not in cp_map['upward']:
            cp_map['upward'][can_uri] = []
        if can_cur_doc['curationUrl'] not in cp_map['upward'][can_uri]:
            cp_map['upward'][can_uri].append(can_cur_doc['curationUrl'])
        # # downward
        if can_cur_doc['curationUrl'] not in cp_map['downward']:
            cp_map['downward'][can_cur_doc['curationUrl']] = []
        if can_uri not in cp_map['downward'][can_cur_doc['curationUrl']]:
            cp_map['downward'][can_cur_doc['curationUrl']].append(can_uri)
        # canvas
        if can_uri not in lo['canvas_uri_dict']:
            log('creating new canvas {}'.format(can_uri))
            new_canvases += 1
            can_db = Canvas(canvas_uri=can_uri,
                         json_string=json.dumps(can_doc))
            db.session.add(can_db)
            db.session.flush()
            lo['canvas_uri_dict'][can_uri] = can_db.id
            can_db_id = can_db.id
        else:
            log('using exiting canvas {}'.format(can_uri))
            can_db_id = lo['canvas_uri_dict'][can_uri]
            can_db = db.session.query(Canvas).filter(
                            Canvas.canvas_uri == can_uri).first()
            old_can_dict = json.loads(can_db.json_string)
            merged_doc = merge_iiif_doc_metadata(old_can_dict, cur_can_dict)
            can_db.json_string = json.dumps(merged_doc)
            db.session.add(can_db)
            db.session.flush()
        # still curation metadata
        if found_top_metadata and top_cur_db and \
                not top_doc_has_thumbnail:
            # enhance (cur metadata-) cur
            log(('enhancing curation {} search result (thumbnail, etc.)'
                ).format(top_cur_db.curation_uri))
            enhance_top_meta_curation_doc(top_cur_doc, can_doc)
            top_cur_db.json_string = json.dumps(top_cur_doc)
            top_doc_has_thumbnail = True
            # can assoc
            tcaa_key = (lo['term_tup_dict'][top_term],
                        lo['canvas_uri_dict'][can_uri])
            if tcaa_key not in lo['term_can_assoc_list']:
                log('associating top term {} with  canvas {}'.format(top_term,
                                                                     can_uri))
                lo['term_can_assoc_list'].append(tcaa_key)
                assoc = TermCanvasAssoc(term_id=top_term_db_id,
                                        canvas_id=can_db_id,
                                        metadata_type='curation',
                                        actor=top_actor)
                db.session.add(assoc)

        # canvas metadata
        log('going through canvas level metadata')
        for can_md in cur_can_dict.get('metadata', []) + [cfg.e_term()]:
            can_term = build_qualifier_tuple(can_md)
            if not can_term[1]:
                # don't allow empty values
                continue
            # term
            if can_term not in lo['term_tup_dict']:
                log('creating new term {}'.format(can_term))
                term = Term(term=can_term[1],
                            qualifier=can_term[0])
                db.session.add(term)
                db.session.flush()
                lo['term_tup_dict'][can_term] = term.id
                can_term_id = term.id
            else:
                log('using existing term {}'.format(can_term))
                can_term_id = lo['term_tup_dict'][can_term]
            # can assoc
            tcaa_key = (lo['term_tup_dict'][can_term],
                        lo['canvas_uri_dict'][can_uri])
            can_actor = get_metadata_actor(can_md)
            if tcaa_key not in lo['term_can_assoc_list']:
                log(('creating new association between {} and {}'
                    ).format(can_term, can_uri))
                assoc = TermCanvasAssoc(term_id=can_term_id,
                                        canvas_id=can_db_id,
                                        metadata_type='canvas',
                                        actor=can_actor)
                db.session.add(assoc)
                lo['term_can_assoc_list'].append(tcaa_key)
            # cur
            can_cur_uri = '{}{}{}'.format(can_cur_doc['curationUrl'],
                                          can_term[1],
                                          'canvas')
            if can_cur_uri not in lo['curation_uri_dict']:
                log('creating new canvas hit curation {}'.format(can_cur_uri))
                can_cur_db = Curation(curation_uri=can_cur_uri,
                                      json_string=json.dumps(can_cur_doc))
                db.session.add(can_cur_db)
                db.session.flush()
                lo['curation_uri_dict'][can_cur_uri] = can_cur_db.id
                can_cur_id = can_cur_db.id
            else:
                log(('using existing canvas hit curation {}'
                    ).format(can_cur_uri))
                can_cur_id = lo['curation_uri_dict'][can_cur_uri]
            # cur assoc
            tcua_key = (lo['term_tup_dict'][can_term],
                        lo['curation_uri_dict'][can_cur_uri])
            can_actor = get_metadata_actor(can_md)
            if tcua_key not in lo['term_cur_assoc_list']:
                log(('creating new association between {} and {}'
                    ).format(can_term, can_cur_uri))
                assoc = TermCurationAssoc(term_id=can_term_id,
                                          curation_id=can_cur_id,
                                          metadata_type='curation',
                                          actor=can_actor)
                db.session.add(assoc)
                lo['term_cur_assoc_list'].append(tcua_key)
    return new_canvases


def process_curation_create(lo, cp_map, activity):
    """ Process a create activity that has a cr:Curation as its object.
    """

    new_canvases = 0
    log('retrieving curation {}'.format(activity['object']['@id']))
    cur_dict = get_referenced(activity, 'object')
    top_cur_doc = build_curation_doc(cur_dict, activity)
    found_top_metadata = False
    log('going through top level metadata')
    # curation metadata
    for cur_md in cur_dict.get('metadata', []) + [cfg.e_term()]:
        top_term = build_qualifier_tuple(cur_md)
        if not top_term[1]:
            # don't allow empty values
            continue
        # term
        if top_term not in lo['term_tup_dict']:
            log('creating term {}'.format(top_term))
            term = Term(term=top_term[1], qualifier=top_term[0])
            db.session.add(term)
            db.session.flush()
            lo['term_tup_dict'][top_term] = term.id
            top_term_db_id = term.id
        else:
            log('using existing term {}'.format(top_term))
            top_term_db_id = lo['term_tup_dict'][top_term]
        # cur
        top_cur_uri = top_cur_doc['curationUrl']+top_term[1]+'curation'
        if top_cur_uri not in lo['curation_uri_dict']:
            # new
            log('creating curation {}'.format(top_cur_uri))
            top_cur_db = Curation(curation_uri=top_cur_uri,
                                  json_string=json.dumps(top_cur_doc))
            db.session.add(top_cur_db)
            db.session.flush()
            lo['curation_uri_dict'][top_cur_uri] = top_cur_db.id
            top_cur_db_id = top_cur_db.id
        else:
            # existing
            log('using existing curation {}'.format(top_cur_uri))
            top_cur_db_id = lo['curation_uri_dict'][top_cur_uri]
            top_cur_db = None
        # cur assoc
        tcua_key = (lo['term_tup_dict'][top_term],
                    lo['curation_uri_dict'][top_cur_uri])
        top_actor = get_metadata_actor(cur_md)
        if tcua_key not in lo['term_cur_assoc_list']:
            log(('creating new association between {} and {}'
                ).format(top_term, top_cur_uri))
            assoc = TermCurationAssoc(term_id=top_term_db_id,
                                      curation_id=top_cur_db_id,
                                      metadata_type='curation',
                                      actor=top_actor)
            db.session.add(assoc)
            db.session.flush()
            lo['term_cur_assoc_list'].append(tcua_key)
        found_top_metadata = True

    top_doc_has_thumbnail = False
    log('entering ranges')
    for ran in cur_dict.get('selections', []):
        # Manifest is the same for all Canvases ahead, so get it now
        man = get_referenced(ran, 'within')
        if man == '{}':
            # if the manifest can not be accessed, skip this range
            continue
        todo = len(ran.get('members', []) + ran.get('canvases', []))
        log('processing {} canvases'.format(todo))

        canvases = ran.get('members', []) + ran.get('canvases', [])
        new_canvases += index_canvases_in_cur_selection(lo,
                                                cp_map,
                                                activity,
                                                cur_dict,
                                                man,
                                                canvases,
                                                found_top_metadata,
                                                top_cur_db,
                                                top_doc_has_thumbnail,
                                                top_cur_doc,
                                                top_term,
                                                top_term_db_id,
                                                top_actor)
        log('done')
    return new_canvases


def process_curation_delete(cp_map, activity):
    """ Process a delete activity that has a cr:Curation as its object.
    """

    log(('deletion triggered through activity {}').format(activity['id']))
    # delete Curation
    cur_uri = get_attrib_uri(activity, 'object')
    to_del = db.session.query(Curation).filter(
                Curation.curation_uri.ilike('%{}%'.format(cur_uri))
                ).all()
    if len(to_del) == 0:
        log('nothing to delete')
    for cur_db in to_del:
        log(('deleting curation record {} and all term associations belonging'
             'to it').format(cur_db.curation_uri))
        db.session.query(TermCurationAssoc).filter(
                TermCurationAssoc.curation_id == cur_db.id
                ).delete()
        db.session.query(Curation).filter(
                Curation.id == cur_db.id
                ).delete()
    db.session.commit()

    # delete orphaned Canvases if configured
    if not cfg.allow_orphan_canvases() and \
            cur_uri in cp_map['downward']:
        to_del_uris = list(cp_map['downward'][cur_uri])  # copy
        for can_uri in to_del_uris:
            try:
                cp_map['upward'][can_uri].remove(cur_uri)
                cp_map['downward'][cur_uri].remove(can_uri)
            except ValueError as e:
                log(('tried to delete parent entry {} for canvas {} but co'
                     'uld not find it in the canvas parent map'
                     ).format(cur_uri, can_uri))
            if len(cp_map['upward'][can_uri]) == 0:
                log(('deleting canvas record {} and all term associations belo'
                     'nging to it because it was orphaned').format(can_uri))
                can_db = db.session.query(Canvas).filter(
                            Canvas.canvas_uri == can_uri
                            ).first()
                db.session.query(TermCanvasAssoc).filter(
                        TermCanvasAssoc.canvas_id == can_db.id
                        ).delete()
                db.session.query(Canvas).filter(
                        Canvas.id == can_db.id
                        ).delete()
            else:
                log(('record {} still has {} parent(s) left. not deleting'
                    ).format(can_uri, len(cp_map['upward'][can_uri])))


def get_lookup_dict():
    """ Create a dictionary for records already indexed. This is used during
        crawling to see if a record for a given identifier (e.g. the label +
        value for a metadata entry) already exists, and if so, provide the DB
        ID it was given to create new associations (e.g. with Canvases).
    """

    log('building lookup dictionaries of existing recrods')
    # build lookup dictionaries of existing recrods
    term_tup_dict = {}
    terms = db.session.query(Term).all()
    if terms:
        for term in terms:
            term_tup_dict[(term.qualifier, term.term)] = term.id
    canvas_uri_dict = {}
    cans = db.session.query(Canvas).all()
    if cans:
        for can in cans:
            canvas_uri_dict[can.canvas_uri] = can.id
    curation_uri_dict = {}
    curs = db.session.query(Curation).all()
    if curs:
        for cur in curs:
            curation_uri_dict[cur.curation_uri] = cur.id
    log('building lookup lists of existing associations')
    # build lookup lists of existing associations
    term_can_assoc_list = []
    tcaas = db.session.query(TermCanvasAssoc).all()
    if tcaas:
        for tcaa in tcaas:
            term_can_assoc_list.append((tcaa.term_id, tcaa.canvas_id))
    term_cur_assoc_list = []
    tcuas = db.session.query(TermCurationAssoc).all()
    if tcuas:
        for tcua in tcuas:
            term_cur_assoc_list.append((tcua.term_id, tcua.curation_id))
    lo = {}
    lo['term_tup_dict'] = term_tup_dict
    lo['canvas_uri_dict'] = canvas_uri_dict
    lo['curation_uri_dict'] = curation_uri_dict
    lo['term_can_assoc_list'] = term_can_assoc_list
    lo['term_cur_assoc_list'] = term_cur_assoc_list
    return lo


def crawl_single(lo, cp_map, as_source):
    """ Crawl, given a URL to an Activity Stream
    """

    log('retrieving Activity Stream')
    try:
        resp = requests.get(as_source)
        # ↑ TODO: support multiple sources
        #         need for one last_crawl
        #         date per source?
    except requests.exceptions.RequestException as e:
        msg = 'Could not access Activity Stream. ({})'.format(e)
        log(msg)
        print(msg)
        return
    if resp.status_code != 200:
        msg = ('Could not access Activity Stream. (HTTP {})'
              ).format(resp.status_code)
        log(msg)
        print(msg)
        return
    as_oc = resp.json()
    log('start iterating over Activity Stream pages')
    as_ocp = get_referenced(as_oc, 'last')
    last_crawl = db.session.query(CrawlLog).order_by(desc(CrawlLog.log_id)
                                                    ).first()
    new_canvases = 0
    new_activity = False
    # NOTE: seen_activity_objs is used to prevent processing obsolete
    #       activities. Since we go through the Activity Stream backwards, we
    #       only process the most recent Activity per IIIF doc.
    #       (Not doing so might lead to for example trying to process a Create
    #       for a document for which a Delete was processed just before.)
    seen_activity_objs = []
    # for all AS pages
    loop_counter = 0
    while True:
        # HOTFIX: break out of possible inifine loop by skipping one AS page
        if loop_counter > 10000:
            loop_counter = 0  # reset counter
            continue          # skip single AS page
        # for all AC items
        log('going through AS page {}'.format(as_ocp['id']))
        for activity in as_ocp['orderedItems']:
            log('going through {} item {}'.format(activity['type'],
                                                  activity['id']))
            activity_end_time = dateutil.parser.parse(activity['endTime'])
            if last_crawl:
                last_crawl_time = dateutil.parser.parse(last_crawl.datetime)
            else:
                zero_timestamp = datetime.datetime.fromtimestamp(0)
                last_crawl_time = zero_timestamp.isoformat()
            # if we haven't seen it yet and it's about a Curation
            if (not last_crawl or activity_end_time > last_crawl_time) and \
                    activity['object']['@type'] == 'cr:Curation' and \
                    activity['object'] not in seen_activity_objs:
                new_activity = True
                if activity['type'] == 'Create':
                    new_canvases += process_curation_create(lo, cp_map,
                                                            activity)
                elif activity['type'] == 'Update':
                    process_curation_delete(cp_map, activity)
                    lo = get_lookup_dict()
                    process_curation_create(lo, cp_map, activity)
                    # TODO: possible to determine new canvases?
                elif activity['type'] == 'Delete':
                    process_curation_delete(cp_map, activity)
                db.session.commit()
                seen_activity_objs.append(activity['object'])
            else:
                log('skipping')

        if not as_ocp.get('prev', False):
            break
        as_ocp = get_referenced(as_ocp, 'prev')
        loop_counter += 1

    # persist crawl log
    crawl_log = CrawlLog(new_canvases=new_canvases,
                         datetime=datetime.datetime.utcnow().isoformat())
    db.session.add(crawl_log)
    db.session.commit()
    if new_activity:
        # call bots (if configured)
        post_bot_jobs()
        log('generating facet list')
        # build and persist facet list
        facet_list = build_facet_list()
        log('persisting facet list')
        db_entry = db.session.query(FacetList).first()
        if not db_entry:
            db_entry = FacetList(json_string=json.dumps(facet_list))
        else:
            db_entry.json_string = json.dumps(facet_list)
        db.session.add(db_entry)
        db.session.commit()
    else:
        log('no changes. skipping generation of facet list')

    log('- - - - - - - - - - END - - - - - - - - - -')


def post_bot_jobs():
    # trigger job post to bost (in case new Canvases were craweld)
    for bot_url in cfg.bot_urls():
        post_url = '{}{}'.format(bot_url, '/job')
        callback_url = '{}{}'.format(cfg.serv_url(), '/callback')

        return_code = post_job(post_url, callback_url)
        #  1 = success
        #  0 = nothing to do
        # -1 = bot still busy
        # -2 = something went wrong
        log('posted job to "{}"'.format(post_url))
        if return_code == 1:
            log('success')
        elif return_code == 0:
            log('nothing to do')
        elif return_code == -1:
            log('bot is still busy')
        elif return_code == -2:
            log('failed for unknown reason')
        else:
            log('something went horribly wrong')


def crawl():
    """ Crawl all Activity Streams set in the config.

        This function does not run inside the normal Canvas Indexer app context
        (because it is not triggered by a web request) and "therefore" looks a
        bit messy, has imports inside it, etc.
    """

    from flask import Flask
    app = Flask(__name__)
    with app.app_context():
        cfg = Cfg()
        app.config['SQLALCHEMY_DATABASE_URI'] = cfg.db_uri()
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

        from canvasindexer.models import db
        db.init_app(app)
        db.create_all()
        log('- - - - - - - - - - START - - - - - - - - - -')
        # prepare DB ID lookup structures
        lo = get_lookup_dict()

        # prepare Canvas parent map
        cp_map_db = db.session.query(CanvasParentMap).first()
        if cp_map_db:
            cp_map = json.loads(cp_map_db.json_string)
        else:
            cp_map = {'upward':{}, 'downward':{}}
            cp_map_db = CanvasParentMap(json_string=json.dumps(cp_map))

        # crawl
        for as_source in cfg.as_sources():
            crawl_single(lo, cp_map, as_source)

        # store Canvas parent map
        cp_map_db.json_string = json.dumps(cp_map)
        db.session.add(cp_map_db)
        db.session.commit()
