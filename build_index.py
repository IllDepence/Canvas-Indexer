import datetime
import dateutil.parser
import json
import re
import requests
import sys
from collections import OrderedDict
from sqlalchemy import (Column, Table, Integer, ForeignKey, UniqueConstraint,
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
    metadata_type = Column('metadata_type', String(255))
    actor = Column('actor', String(255))
    term = relationship('Term', back_populates='curations')
    curation = relationship('Curation', back_populates='terms')


class TermCanvasAssoc(Base):
    __tablename__ = 'term_canvas_assoc'
    term_id = Column('term_id', Integer, ForeignKey('term.id'),
                     primary_key=True)
    canvas_id = Column('canvas_id', Integer, ForeignKey('canvas.id'),
                       primary_key=True)
    metadata_type = Column('metadata_type', String(255))
    actor = Column('actor', String(255))
    term = relationship('Term', back_populates='canvases')
    canvas = relationship('Canvas', back_populates='terms')


class Term(Base):
    __tablename__ = 'term'
    id = Column(Integer, primary_key=True)
    term = Column(String(255))
    qualifier = Column(String(255))
    __table_args__ = (UniqueConstraint('term', 'qualifier'), )
    canvases = relationship('TermCanvasAssoc', back_populates='term')
    curations = relationship('TermCurationAssoc', back_populates='term')


class Canvas(Base):
    __tablename__ = 'canvas'
    id = Column(Integer, primary_key=True)
    canvas_uri = Column(String(2048), unique=True)  # ID + fragment
    json_string = Column(UnicodeText())
    terms = relationship('TermCanvasAssoc', back_populates='canvas')


class Curation(Base):
    __tablename__ = 'curation'
    id = Column(Integer, primary_key=True)
    curation_uri = Column(String(2048), unique=True)  # ID + term + m.d.typ.[1]
    json_string = Column(UnicodeText())
    terms = relationship('TermCurationAssoc', back_populates='curation')

    # [1] the reason for storing each curation once per associated term is that
    #     depending on the search term their representation as a search result
    #     (e.g. thumbnail) is different
    #     furthermore the type of metadata (curation top level vs. canvas) is
    #     used to distinguish between those two kinds of search results


class CrawlLog(Base):
    __tablename__ = 'crawllog'
    log_id = Column(Integer(), autoincrement=True, primary_key=True)
    datetime = Column(DateTime(timezone=True), server_default=func.now())
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
        context/content) and the actor (human or software) that associated the
        document with the metadata.
    """

    def __init__(self, doc, typ, act):
        self.doc = doc
        self.typ = typ
        self.act = act

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

    ret = OrderedDict()
    ret['facets'] = []
    for label, vals in facet_map.items():
        assocs = session.query(TermCanvasAssoc).join(Term)
        assocs = assocs.filter(TermCanvasAssoc.metadata_type == 'canvas',
                               TermCanvasAssoc.term_id == Term.id,
                               Term.qualifier == label).all()
        facet = OrderedDict()
        facet['label'] = label
        facet['value'] = []
        for val in vals:
            unkown_count = 0
            human_count = 0
            software_count = 0
            for a in assocs:
                if a.term.term == val:
                    if a.actor == 'human':
                        human_count += 1
                    elif a.actor == 'software':
                        software_count += 1
                    else:
                        unkown_count += 1
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
                facet['value'].append(entry)
                entry['agent'] = 'human'
            # software actor
            if software_count > 0:
                entry = OrderedDict()
                entry['label'] = val
                entry['value'] = software_count
                facet['value'].append(entry)
                entry['agent'] = 'software'
        ret['facets'].append(facet)

    return ret

def get_referenced(json_dict, attrib):
    """ Get a value (of an attribute in a dict) that is not included in its
        entirety but just just referenced by a URI or an object with a URI as
        its id.
    """

    if type(json_dict[attrib]) == str:
        resp = requests.get(json_dict[attrib])
    elif type(json_dict[attrib]) == dict:
        if json_dict[attrib].get('id', False):
            resp = requests.get(json_dict[attrib]['id'])
        elif json_dict[attrib].get('@id', False):
            resp = requests.get(json_dict[attrib]['@id'])
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
        print('Could not find compliance level in info.json.')
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
            # http://dcollections.lib.keio.ac.jp/ [...] /NRE/110X-444-2-2/page1
            # http://dcollections.lib.keio.ac.jp/ [...] /NRE/110X-444-2-2/page10

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
                resp = requests.get(info_url)
                info_dict = resp.json()
                profile = info_dict.get('profile')
                img_url = '{}{}'.format(info_dict.get('@id'),
                                        '/full/full/0/default.jpg')

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
    """

    if type(something) == str:
        # 'foo' → ('', 'foo')
        return ('', something)
    elif type(something) in [tuple, list]:
        # ['foo', 'bar', ...] / ('foo', 'bar', ...) → ('foo', 'bar')
        return (something[0], something[1])
    elif type(something) == dict:
        label = something.get('label')
        value = something.get('value')
        if (label == '' or label) and (value == '' or value):
            # {'label': 'foo', 'value': 'bar', ...} → ('foo', bar')
            if type(value) == str:
                return (label, value)
            elif type(value) in [tuple, list]:
                return (label, ', '.join([x.__repr__() for x in value]))
            else:
                return (label, value.__repr__())
        else:
            # {'foo': 'bar', ...} → ('foo', bar')
            return (list(something.keys())[0], list(something.values())[0])
    # <?> → ('', <?>.__repr__())
    return ('', '{}'.format(something))

def log(msg):
    """ Write a log message.
    """

    timestamp = str(datetime.datetime.now()).split('.')[0]
    print('[{}]   {}'.format(timestamp, msg))


log('starting')
try:
    resp = requests.get(cfg.as_sources()[0])
    # ↑ TODO: support multiple sources
    #         need for one last_crawl
    #         date per source?
except requests.exceptions.RequestException as e:
    print('Could not access Activity Stream. ({})'.format(e))
    sys.exit(1)
if resp.status_code != 200:
    print('Could not access Activity Stream. (HTTP {})'.format(resp.status_code))
    sys.exit(1)
as_oc = resp.json()
as_ocp = get_referenced(as_oc, 'last')
term_tup_to_canvas_index = {}
term_tup_to_curation_index = {}
last_crawl = session.query(CrawlLog).order_by(desc(CrawlLog.log_id)).first()
log('going through AS')
# for all AS pages
while True:
    # for all AC items
    log('going through AS page {}'.format(as_ocp['id']))
    for activity in as_ocp['orderedItems']:
        log('going through {} item {}'.format(activity['type'],
                                              activity['id']))
        activity_end_time = dateutil.parser.parse(activity['endTime'])
        # if we haven't seen it yet and it's a Curation create
        if (not last_crawl or activity_end_time > last_crawl.datetime) and \
                activity['type'] == 'Create' and \
                activity['object']['@type'] == 'cr:Curation':
            log('retrieving curation {}'.format(activity['object']['@id']))
            cur = get_referenced(activity, 'object')
            # doc (top)
            cur_top_doc = build_curation_doc(cur, activity)
            # terms (top)
            found_top_metadata = False
            log('going through top level metadata')
            for md in cur.get('metadata', []):
                top_term = build_qualifier_tuple(md)
                # Curation index
                if top_term not in term_tup_to_curation_index.keys():
                    term_tup_to_curation_index[top_term] = []
                top_actor = md.get('agent', 'unknown')
                cur_top_assoc = Assoc(cur_top_doc, 'curation', top_actor)
                term_tup_to_curation_index[top_term].append(cur_top_assoc)
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
                    # doc (can)
                    # TODO: mby get read and include man[_can] metadata
                    canvas_doc = build_canvas_doc(man, cur_can)
                    cur_doc = build_curation_doc(cur, activity, canvas_doc,
                                                 cur_can_idx)
                    if found_top_metadata and not top_doc_has_thumbnail:
                        # enhance doc (top)
                        enhance_top_meta_curation_doc(cur_top_doc, canvas_doc)
                        top_doc_has_thumbnail = True
                        # Canvas index
                        if top_term not in term_tup_to_canvas_index.keys():
                            term_tup_to_canvas_index[top_term] = []
                        can_assoc = Assoc(canvas_doc, 'curation', top_actor)
                        term_tup_to_canvas_index[top_term].append(can_assoc)
                    # terms (can)
                    for md in cur_can.get('metadata', []):
                        can_term = build_qualifier_tuple(md)
                        # Canvas index
                        if can_term not in term_tup_to_canvas_index.keys():
                            term_tup_to_canvas_index[can_term] = []
                        can_actor = md.get('agent', 'unknown')
                        can_assoc = Assoc(canvas_doc, 'canvas', can_actor)
                        term_tup_to_canvas_index[can_term].append(can_assoc)

                        # Curation index
                        if can_term not in term_tup_to_curation_index.keys():
                            term_tup_to_curation_index[can_term] = []
                        cur_assoc = Assoc(cur_doc, 'canvas', can_actor)
                        term_tup_to_curation_index[can_term].append(cur_assoc)
                log('done')
        else:
            log('skipping')

    if not as_ocp.get('prev', False):
        break
    as_ocp = get_referenced(as_ocp, 'prev')
    sys.stdout.flush()

sys.stdout.flush()

log('persisting term_tup_to_canvas_index')
# persist term_tup_to_canvas_index entries
new_canvases = 0
for term_tup, assocs in term_tup_to_canvas_index.items():
    qual_str = term_tup[0]
    term_str = term_tup[1]
    # check if the term already exists, if not create it
    log('check for existing term')
    term = session.query(Term).filter(Term.term == term_str,
                                      Term.qualifier == qual_str).first()
    log('done')
    if not term:
        log('creating new term')
        term = Term(term=term_str, qualifier=qual_str)
        session.add(term)
        session.commit()
    # check if the canvas already exists (Canvas URI = ID + fragment)
    # if so, add term relations if not present. maybe also check for
    #     inconsistencies, new metadata, etc.?
    # if not add it + term relations
    log('going through {} associations'.format(len(assocs)))
    for assoc in assocs:
        can_dict = assoc.doc
        canvas_uri = can_dict['canvasId']+can_dict['fragment']
        log('checking for existing curation')
        can = session.query(Canvas).filter(
                                    Canvas.canvas_uri == canvas_uri).first()
        log('done')
        if not can:
            log('creating new curation')
            can = Canvas(canvas_uri=canvas_uri,
                         json_string=json.dumps(can_dict))
            new_canvases += 1
            session.add(can)
            session.commit()
        log('checking for existing association')
        already_associated = session.query(TermCanvasAssoc).filter(
                                        TermCanvasAssoc.canvas_id == can.id,
                                        TermCanvasAssoc.term_id == term.id
                                                                  ).first()
        log('done')
        if not already_associated:
            log('creating new association')
            db_assoc = TermCanvasAssoc(term=term, canvas=can,
                                       metadata_type=assoc.typ,
                                       actor=assoc.act)
            session.add(db_assoc)
        session.commit()
    sys.stdout.flush()
log('persisting term_tup_to_curation_index')
# persist term_tup_to_curation_index entries
for term_tup, assocs in term_tup_to_curation_index.items():
    qual_str = term_tup[0]
    term_str = term_tup[1]
    # check if the term already exists, if not create it
    term = session.query(Term).filter(Term.term == term_str,
                                      Term.qualifier == qual_str).first()
    if not term:
        term = Term(term=term_str, qualifier=qual_str)
        session.add(term)
        session.commit()
    # check if the curation already exists
    # if so, add term relations if not present.
    # if not add it + term relations
    for assoc in assocs:
        cur_dict = assoc.doc
        cur_uri = cur_dict['curationUrl']+term.term+assoc.typ
        cur = session.query(Curation).filter(
                    Curation.curation_uri == cur_uri).first()
        if not cur:
            cur = Curation(curation_uri=cur_uri,
                           json_string=json.dumps(cur_dict))
            session.add(cur)
            session.commit()
        already_associated = session.query(TermCurationAssoc).filter(
                                    TermCurationAssoc.curation_id == cur.id,
                                    TermCurationAssoc.term_id == term.id
                                                                  ).first()
        if not already_associated:
            db_assoc = TermCurationAssoc(term=term, curation=cur,
                                         metadata_type=assoc.typ,
                                         actor=assoc.act)
            session.add(cur)
        session.commit()
log('persisting crawl log')
# persist crawl log
log = CrawlLog(new_canvases=new_canvases)
session.add(log)
session.commit()
log('generating facet list')
# build and persist facet list
facet_list = build_facet_list()
log('persisting facet list')
db_entry = session.query(FacetList).first()
if not db_entry:
    db_entry = FacetList(json_string = json.dumps(facet_list))
else:
    db_entry.json_string = json.dumps(facet_list)
session.add(db_entry)
session.commit()
