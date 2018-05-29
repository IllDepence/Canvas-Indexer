import datetime
import dateutil.parser
import json
import re
import requests
import sys
from collections import OrderedDict
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from sqlalchemy import (Column, Integer, ForeignKey, UniqueConstraint,
                        String, UnicodeText, DateTime, create_engine, desc)
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from canvasindexer.config import Cfg

cfg = Cfg()
Base = declarative_base()


class TermCurationAssoc(Base):
    __tablename__ = 'term_curation_assoc'
    term_id = Column('term_id', Integer, ForeignKey('term.id'),
                     primary_key=True)
    curation_id = Column('curation_id', Integer, ForeignKey('curation.id'),
                         primary_key=True)
    # FIXME: allow for multiple assocs for a term curation pair if metadata
    #        type or actor is different (i.e. extend primary key)
    #        (currently no prob b/c only canvas metadata and language split
    #        between actors types)
    #        when changed has to be reflected in term_cur_assoc_list
    metadata_type = Column('metadata_type', String(255))
    actor = Column('actor', String(255))
    term = relationship('Term')
    curation = relationship('Curation')


class TermCanvasAssoc(Base):
    __tablename__ = 'term_canvas_assoc'
    term_id = Column('term_id', Integer, ForeignKey('term.id'),
                     primary_key=True)
    canvas_id = Column('canvas_id', Integer, ForeignKey('canvas.id'),
                       primary_key=True)
    # FIXME: allow for multiple assocs for a term canvas pair if metadata
    #        type or actor is different (i.e. extend primary key)
    #        (currently no prob b/c only canvas metadata and language split
    #        between actors types)
    #        when changed has to be reflected in term_can_assoc_list
    metadata_type = Column('metadata_type', String(255))
    actor = Column('actor', String(255))
    term = relationship('Term')
    canvas = relationship('Canvas')


class Term(Base):
    __tablename__ = 'term'
    id = Column(Integer, primary_key=True)
    term = Column(String(255))
    qualifier = Column(String(255))
    __table_args__ = (UniqueConstraint('term', 'qualifier'), )
    canvases = relationship('TermCanvasAssoc')
    curations = relationship('TermCurationAssoc')


class Canvas(Base):
    __tablename__ = 'canvas'
    id = Column(Integer, primary_key=True)
    canvas_uri = Column(String(2048), unique=True)  # ID + fragment
    json_string = Column(UnicodeText())
    terms = relationship('TermCanvasAssoc')


class Curation(Base):
    __tablename__ = 'curation'
    id = Column(Integer, primary_key=True)
    curation_uri = Column(String(2048), unique=True)  # ID + term + m.d.typ.[1]
    json_string = Column(UnicodeText())
    terms = relationship('TermCurationAssoc')

    # [1] the reason for storing each curation once per associated term is that
    #     depending on the search term their representation as a search result
    #     (e.g. thumbnail) is different
    #     furthermore the type of metadata (curation top level vs. canvas) is
    #     used to distinguish between those two kinds of search results


class CrawlLog(Base):
    __tablename__ = 'crawllog'
    log_id = Column(Integer(), autoincrement=True, primary_key=True)
    # datetime = Column(DateTime(timezone=True), server_default=func.now())
    # ↓ saved as isoformat string to ease integration with JSONkeeper AS
    datetime = Column(UnicodeText())
    new_canvases = Column(Integer())


class FacetList(Base):
    __tablename__ = 'facetlist'
    id = Column(Integer(), autoincrement=True, primary_key=True)
    json_string = Column(UnicodeText())


engine = create_engine(cfg.db_uri())
Base.metadata.create_all(engine)
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()


class Assoc():
    """ Class for describing a document (in relation to a metadata term it is
        being associated with) alongside the metatada's relative type (direct/
        context/content) and the actor (human or machine) that associated the
        document with the metadata.
    """

    def __init__(self, doc, typ, act):
        self.doc = doc
        self.typ = typ
        self.act = act


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

    terms = session.query(Term).join(TermCanvasAssoc)
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
        assocs = session.query(TermCanvasAssoc).join(Term)
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

            ['<a_label', 'c_label', 'b_label', ...]

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


def get_referenced(json_dict, attrib):
    """ Get a value (of an attribute in a dict) that is not included in its
        entirety but just just referenced by a URI or an object with a URI as
        its id.
    """

    url = None
    if type(json_dict[attrib]) == str:
        url = json_dict[attrib]
    elif type(json_dict[attrib]) == dict:
        if json_dict[attrib].get('id', False):
            url = json_dict[attrib]['id']
        elif json_dict[attrib].get('@id', False):
            url = json_dict[attrib]['@id']

    try:
        resp = requests_retry_session().get(url)
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
                except Exception as e:
                    log(('Could not get info.json at {}.'
                         ' Error {}.').format(
                        url,
                        e.__class__.__name__
                        )
                    )
                    resp =  '{}'
                info_dict = resp.json()
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

        If canvas_doc is given this is assumed to be a sarch result associated
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
    # TODO: once implemented in JSONkeeper, use the activity's endtime in case
    #       it's an Update Activity
    doc['crawledAt'] = datetime.datetime.now().isoformat()
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


def merge_iiif_doc_metadata(old_doc, new_doc):
    """ Given two IIIF documents (e.g. Canvas) as dictionaries, merge the
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
    with open(cfg.crawler_log_file(), 'a') as f:
        f.write('[{}]   {}\n'.format(timestamp, msg))

log('- - - - - - - - - - START - - - - - - - - - -')
log('building lookup dictionaries of existing recrods')
# build lookup dictionaries of existing recrods
term_tup_dict = {}
terms = session.query(Term).all()
if terms:
    for term in terms:
        term_tup_dict[(term.qualifier, term.term)] = term.id
canvas_uri_dict = {}
cans = session.query(Canvas).all()
if cans:
    for can in cans:
        canvas_uri_dict[can.canvas_uri] = can.id
curation_uri_dict = {}
curs = session.query(Curation).all()
if curs:
    for cur in curs:
        curation_uri_dict[cur.curation_uri] = cur.id
curation_uri_dict = {}
curs = session.query(Curation).all()
if curs:
    for cur in curs:
        curation_uri_dict[cur.curation_uri] = cur.id
log('building lookup lists of existing associations')
# build lookup lists of existing associations
term_can_assoc_list = []
tcaas = session.query(TermCanvasAssoc).all()
if tcaas:
    for tcaa in tcaas:
        term_can_assoc_list.append((tcaa.term_id, tcaa.canvas_id))
term_cur_assoc_list = []
tcuas = session.query(TermCurationAssoc).all()
if tcuas:
    for tcua in tcuas:
        term_cur_assoc_list.append((tcua.term_id, tcua.curation_id))

log('retrieving Activity Stream')
try:
    resp = requests.get(cfg.as_sources()[0])
    # ↑ TODO: support multiple sources
    #         need for one last_crawl
    #         date per source?
except requests.exceptions.RequestException as e:
    msg = 'Could not access Activity Stream. ({})'.format(e)
    log(msg)
    print(msg)
    sys.exit(1)
if resp.status_code != 200:
    msg = 'Could not access Activity Stream. (HTTP {})'.format(
                                                            resp.status_code
                                                              )
    log(msg)
    print(msg)
    sys.exit(1)
as_oc = resp.json()
log('start iterating over Activity Stream pages')
as_ocp = get_referenced(as_oc, 'last')
last_crawl = session.query(CrawlLog).order_by(desc(CrawlLog.log_id)).first()
new_canvases = 0
new_activity = False
# for all AS pages
while True:
    # for all AC items
    log('going through AS page {}'.format(as_ocp['id']))
    for activity in as_ocp['orderedItems']:
        log('going through {} item {}'.format(activity['type'],
                                              activity['id']))
        activity_end_time = dateutil.parser.parse(activity['endTime'])
        if last_crawl:
            last_crawl_time = dateutil.parser.parse(last_crawl.datetime)
        else:
            last_crawl_time = datetime.datetime.fromtimestamp(0).isoformat()
        # if we haven't seen it yet and it's a Curation create
        if (not last_crawl or activity_end_time > last_crawl_time) and \
                activity['type'] == 'Create' and \
                activity['object']['@type'] == 'cr:Curation':
            new_activity = True
            log('retrieving curation {}'.format(activity['object']['@id']))
            cur = get_referenced(activity, 'object')
            cur_top_doc = build_curation_doc(cur, activity)
            found_top_metadata = False
            log('going through top level metadata')
            # curation metadata
            for md in cur.get('metadata', []):
                top_term = build_qualifier_tuple(md)
                if not top_term[1]:
                    # don't allow empty values
                    continue
                # term
                if top_term not in term_tup_dict:
                    term = Term(term=top_term[1], qualifier=top_term[0])
                    session.add(term)
                    session.flush()
                    term_tup_dict[top_term] = term.id
                    top_term_id = term.id
                else:
                    top_term_id = term_tup_dict[top_term]
                # cur
                top_cur_uri = cur_top_doc['curationUrl']+top_term[1]+'curation'
                if top_cur_uri not in curation_uri_dict:
                    top_cur = Curation(curation_uri=top_cur_uri,
                                       json_string=json.dumps(cur_top_doc))
                    session.add(top_cur)
                    session.flush()
                    curation_uri_dict[top_cur_uri] = top_cur.id
                    top_cur_id = top_cur.id
                else:
                    top_cur = None
                    top_cur_id = curation_uri_dict[top_cur_uri]
                # cur assoc
                tcua_key = (term_tup_dict[top_term],
                            curation_uri_dict[top_cur_uri])
                top_actor = md.get('agent', 'unknown')
                if tcua_key not in term_cur_assoc_list:
                    assoc = TermCurationAssoc(term_id=top_term_id,
                                              curation_id=top_cur_id,
                                              metadata_type='curation',
                                              actor=top_actor)
                    session.add(assoc)
                    session.flush()
                    term_cur_assoc_list.append(tcua_key)
                found_top_metadata = True

            top_doc_has_thumbnail = False
            log('entering ranges')
            for ran in cur.get('selections', []):
                # Manifest is the same for all Canvases ahead, so get it now
                man = get_referenced(ran, 'within')
                todo = len(ran.get('members', []) + ran.get('canvases', []))
                log('processing {} canvases'.format(todo))
                for cur_can_idx, cur_can in enumerate(ran.get('members', []) +
                                                      ran.get('canvases', [])):
                    log('canvas #{}'.format(cur_can_idx))
                    # TODO: mby get read and include man[_can] metadata
                    can_doc = build_canvas_doc(man, cur_can)
                    can_uri = can_doc['canvasId']+can_doc['fragment']
                    cur_doc = build_curation_doc(cur, activity, can_doc,
                                                 cur_can_idx)
                    # canvas
                    if can_uri not in canvas_uri_dict:
                        new_canvases += 1
                        can = Canvas(canvas_uri=can_uri,
                                     json_string=json.dumps(can_doc))
                        session.add(can)
                        session.flush()
                        canvas_uri_dict[can_uri] = can.id
                        can_id = can.id
                    else:
                        can_id = canvas_uri_dict[can_uri]
                        # extend the Canvas' metadata
                        can = session.query(Canvas).filter(
                                        Canvas.canvas_uri == can_uri).first()
                        db_can = json.loads(can.json_string)
                        merged_doc = merge_iiif_doc_metadata(db_can, cur_can)
                        can.json_string = json.dumps(merged_doc)
                        session.add(can)
                        session.flush()
                    # still curation metadata
                    if found_top_metadata and top_cur and \
                            not top_doc_has_thumbnail:
                        # enhance (cur metadata-) cur
                        enhance_top_meta_curation_doc(cur_top_doc, can_doc)
                        top_cur.json_string = json.dumps(cur_top_doc)
                        top_doc_has_thumbnail = True
                        # can assoc
                        tcaa_key = (term_tup_dict[top_term],
                                    canvas_uri_dict[can_uri])
                        if tcaa_key not in term_can_assoc_list:
                            term_can_assoc_list.append(tcaa_key)
                            assoc = TermCanvasAssoc(term_id=top_term_id,
                                                    canvas_id=can_id,
                                                    metadata_type='curation',
                                                    actor=top_actor)
                            session.add(assoc)

                    # canvas metadata
                    for md in cur_can.get('metadata', []):
                        can_term = build_qualifier_tuple(md)
                        if not can_term[1]:
                            # don't allow empty values
                            continue
                        # term
                        if can_term not in term_tup_dict:
                            term = Term(term=can_term[1],
                                        qualifier=can_term[0])
                            session.add(term)
                            session.flush()
                            term_tup_dict[can_term] = term.id
                            can_term_id = term.id
                        else:
                            can_term_id = term_tup_dict[can_term]
                        # can assoc
                        tcaa_key = (term_tup_dict[can_term],
                                    canvas_uri_dict[can_uri])
                        can_actor = md.get('agent', 'unknown')
                        if tcaa_key not in term_can_assoc_list:
                            assoc = TermCanvasAssoc(term_id=can_term_id,
                                                    canvas_id=can_id,
                                                    metadata_type='canvas',
                                                    actor=can_actor)
                            session.add(assoc)
                            term_can_assoc_list.append(tcaa_key)
                        # cur
                        cur_uri = '{}{}{}'.format(cur_doc['curationUrl'],
                                                  can_term[1],
                                                  'canvas')
                        if cur_uri not in curation_uri_dict:
                            can_cur = Curation(curation_uri=cur_uri,
                                               json_string=json.dumps(cur_doc))
                            session.add(can_cur)
                            session.flush()
                            curation_uri_dict[cur_uri] = can_cur.id
                            cur_id = can_cur.id
                        else:
                            cur_id = curation_uri_dict[cur_uri]
                        # cur assoc
                        tcua_key = (term_tup_dict[can_term],
                                    curation_uri_dict[cur_uri])
                        can_actor = md.get('agent', 'unknown')
                        if tcua_key not in term_cur_assoc_list:
                            assoc = TermCurationAssoc(term_id=can_term_id,
                                                      curation_id=cur_id,
                                                      metadata_type='curation',
                                                      actor=can_actor)
                            session.add(assoc)
                            term_cur_assoc_list.append(tcua_key)
                log('done')
            session.commit()
        else:
            log('skipping')

    if not as_ocp.get('prev', False):
        break
    as_ocp = get_referenced(as_ocp, 'prev')

# persist crawl log
crawl_log = CrawlLog(new_canvases=new_canvases,
                     datetime=datetime.datetime.utcnow().isoformat())
session.add(crawl_log)
session.commit()
if new_activity:
    log('generating facet list')
    # build and persist facet list
    facet_list = build_facet_list()
    log('persisting facet list')
    db_entry = session.query(FacetList).first()
    if not db_entry:
        db_entry = FacetList(json_string=json.dumps(facet_list))
    else:
        db_entry.json_string = json.dumps(facet_list)
    session.add(db_entry)
    session.commit()
else:
    log('no changes. skipping generation of facet list')

log('- - - - - - - - - - END - - - - - - - - - -')
