import datetime
import dateutil.parser
import json
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
    if type(json_dict[attrib]) == str:
        resp = requests.get(json_dict[attrib])
    elif type(json_dict[attrib]) == dict:
        if json_dict[attrib].get('id', False):
            resp = requests.get(json_dict[attrib]['id'])
        elif json_dict[attrib].get('@id', False):
            resp = requests.get(json_dict[attrib]['@id'])
    return resp.json()

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
                    doc['can'] = can['@id']
                    doc['man'] = man['@id']
                    # image URI
                    for seq in man.get('sequences', []):
                        for o_can in seq.get('canvases', []):
                            if o_can['@id'] in can['@id']:
                                # ↓ not too hardcoded?
                                img = o_can['images'][0]['resource']['@id']
                                doc['img'] = img
                    # terms
                    for md in can.get('metadata', []):
                        term = md['value']
                        if term not in index.keys():
                            index[term] = []
                        index[term].append(doc)

    if not as_ocp.get('prev', False):
        break
    as_ocp = get_referenced(as_ocp, 'prev')

# persist index entries

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
