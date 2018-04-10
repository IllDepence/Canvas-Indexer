import dateutil.parser
import json
import re
import requests
from sqlalchemy import (Column, Integer, String, UnicodeText, DateTime,
                        create_engine, desc)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
AS_URL = 'http://localhost/JSONkeeper/as/collection.json'
DB_URI = 'sqlite:///pastedesk/index.db'


class TermEntry(Base):
    __tablename__ = 'termentry'
    term = Column(String(255), primary_key=True)
    json_string = Column(UnicodeText())


class CrawlLog(Base):
    __tablename__ = 'crawllog'
    log_id = Column(Integer(), autoincrement=True, primary_key=True)
    datetime = Column(DateTime(timezone=True), server_default=func.now())
    new_entries = Column(Integer())

engine = create_engine(DB_URI)
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


def thumbnail_url(img_uri, canvas_uri, width, height, compliance_lvl):
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
        size = 'full'
    else:
        size = '!{},{}'.format(width, height)  # compliance level unknown
    thumb_url = img_uri.replace('full/full', '{}/{}'.format(fragment, size))
    return thumb_url


resp = requests.get(AS_URL)
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
                for can in ran.get('members'):
                    # build doc and store in index under 'term'
                    doc = {}
                    doc['manifestUrl'] = man['@id']
                    doc['manifestLabel'] = man['label']
                    # image URI
                    for seq in man.get('sequences', []):
                        page_local = 1
                        for o_can in seq.get('canvases', []):
                            if o_can['@id'] in can['@id']:
                                doc['canvasIndex'] = None  # TODO
                                doc['canvasLabel'] = o_can['label']
                                doc['pageLocal'] = page_local
                                url_parts = can['@id'].split('#')
                                if len(url_parts) == 2:
                                    doc['canvasId'] = url_parts[0]
                                    doc['fragment'] = url_parts[1]
                                else:
                                    doc['canvasId'] = can['@id']
                                    doc['fragment'] = ''
                                # ↓ not too hardcoded?
                                img_url = o_can['images'][0]['resource']['@id']
                                # ↓ guarateed to be in format:
                                #   {scheme}://{server}{/prefix}/{identifier}/
                                #   {region}/{size}/{rotation}/{quality}.
                                #   {format}
                                #   so [0:-4] cuts off /{size}/...{format}
                                url_base = '/'.join(img_url.split('/')[0:-4])
                                info_url = '{}/info.json'.format(url_base)
                                doc['canvas'] = info_url
                                resp = requests.get(info_url)
                                info_dict = resp.json()
                                profile = info_dict.get('profile')
                                comp_lvl = get_img_compliance_level(profile)
                                doc['canvasThumbnail'] = thumbnail_url(
                                    img_url, can['@id'], 200, 200, comp_lvl)
                            page_local += 1
                    # terms
                    for md in can.get('metadata', []):
                        term = md['value']
                        if term not in index.keys():
                            index[term] = []
                        index[term].append(doc)

    if not as_ocp.get('prev', False):
        break
    as_ocp = get_referenced(as_ocp, 'prev')

# offline testing
# index = {'siberia':[
#         {'can':'http://www.foo.com/canvas1',
#          'img':'http://127.0.0.1:8000/lwl12_ava.jpg',
#          'man':'http://www.foo.com/manifest1'},
#         {'can':'http://www.foo.com/canvas1',
#          'img':'http://127.0.0.1:8000/lwl12_ava.jpg',
#          'man':'http://www.foo.com/manifest1'},
#         {'can':'http://www.foo.com/canvas1',
#          'img':'http://127.0.0.1:8000/lwl12_ava.jpg',
#          'man':'http://www.foo.com/manifest1'}
#         ]}

# persist index entries
new_entries = 0
for term, doc in index.items():
    entry = session.query(TermEntry).filter(TermEntry.term == term).first()
    if entry:
        json_arr = json.loads(entry.json_string)
        skip = [c['can'] for c in json_arr]
        for can in doc:
            if not can['can'] in skip:
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
