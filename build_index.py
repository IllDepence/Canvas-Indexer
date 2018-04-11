import dateutil.parser
import json
import re
import requests
from collections import OrderedDict
from sqlalchemy import (Column, Integer, String, UnicodeText, DateTime,
                        create_engine, desc)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from pastedesk.config import Cfg

cfg = Cfg()
Base = declarative_base()


class TermEntry(Base):
    __tablename__ = 'termentry'
    term = Column(String(255), primary_key=True)
    json_string = Column(UnicodeText())


class CrawlLog(Base):
    __tablename__ = 'crawllog'
    log_id = Column(Integer(), autoincrement=True, primary_key=True)
    datetime = Column(DateTime(timezone=True), server_default=func.now())
    new_entries = Column(Integer())

engine = create_engine(cfg.db_uri())
Base.metadata.create_all(engine)
Base.metadata.bind = engine
DBSession = sessionmaker(bind=engine)
session = DBSession()


def get_referenced(json_dict, attrib):
    """ Get the value of an attribute in a dict that is just referenced by a
        URI or an object with a URI as its id.
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
    """ Try to figure out the IIIF Image Api compliance level given the
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
            if man_can['@id'] in cur_can['@id']:
                # > canvas
                img_url = man_can['images'][0]['resource']['@id']
                # ↑ not too hardcoded?
                url_base = '/'.join(img_url.split('/')[0:-4])
                # ↑ guarateed to be in format:
                #   {scheme}://{server}{/prefix}/{identifier}/
                #   {region}/{size}/{rotation}/{quality}.
                #   {format}
                #   so [0:-4] cuts off /{size}/...{format}
                info_url = '{}/info.json'.format(url_base)
                doc['canvas'] = info_url
                # > canvasId
                doc['canvasId'] = man_can['@id']
                # > canvasIndex (CODH Cursor API specific)
                doc['canvasCursorIndex'] = man_can.get('cursorIndex', None)
                # > canvasLabel
                doc['canvasLabel'] = man_can['label']
                # > canvasThumbnail
                resp = requests.get(info_url)
                info_dict = resp.json()
                profile = info_dict.get('profile')
                comp_lvl = get_img_compliance_level(profile)
                doc['canvasThumbnail'] = thumbnail_url(img_url, cur_can['@id'],
                                                       200, 200, comp_lvl,
                                                       man_can)
                # > pageLocal
                doc['canvasIndex'] = canvas_index
                # > fragment
                url_parts = cur_can['@id'].split('#')
                if len(url_parts) == 2:
                    doc['fragment'] = url_parts[1]
                else:
                    doc['fragment'] = ''
            canvas_index += 1

    return doc

resp = requests.get(cfg.as_sources()[0])
# ↑ TODO: support multiple sources
#         need for one last_crawl
#         date per source?
as_oc = resp.json()
as_ocp = get_referenced(as_oc, 'last')
index = {}
last_crawl = session.query(CrawlLog).order_by(desc(CrawlLog.log_id)).first()
# for all AC pages
while True:
    # for all AC items
    for item in as_ocp['orderedItems']:
        end_time = dateutil.parser.parse(item['endTime'])
        # if we haven't seen it yet and it's a Curation create
        if (not last_crawl or end_time > last_crawl.datetime) and \
                item['type'] == 'Create' and \
                item['object']['@type'] == 'cr:Curation':
            cur = get_referenced(item, 'object')
            for ran in cur.get('selections', []):
                # Manifest is the same for all Canvases ahead, so get it now
                man = get_referenced(ran, 'within')
                for cur_can in ran.get('members'):
                    # doc
                    # TODO: mby get read and include man[_can] metadata
                    doc = build_canvas_doc(man, cur_can)
                    # terms
                    # for md in cur_can.get('metadata', [{'value': 'face'}]):
                    for md in cur_can.get('metadata', []):
                        term = md['value']
                        if term not in index.keys():
                            index[term] = []
                        index[term].append(doc)

    if not as_ocp.get('prev', False):
        break
    as_ocp = get_referenced(as_ocp, 'prev')

# persist index entries
new_entries = 0
for term, doc in index.items():
    entry = session.query(TermEntry).filter(TermEntry.term == term).first()
    if entry:
        json_arr = json.loads(entry.json_string, object_pairs_hook=OrderedDict)
        skip = [c['canvasId']+c['fragment'] for c in json_arr]
        for can in doc:
            if not can['canvasId']+can['fragment'] in skip:
                json_arr.extend(doc)
                new_entries += 1
        entry.json_string = json.dumps(json_arr)
        session.commit()
    else:
        entry = TermEntry(term=term, json_string=json.dumps(doc))
        session.add(entry)
        session.commit()
        new_entries += len(doc)
# persist crawl log
log = CrawlLog(new_entries=new_entries)
session.add(log)
session.commit()
