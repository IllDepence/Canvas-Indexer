import json
import requests
from sqlalchemy import Column, String, UnicodeText, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
AS_URL = 'http://localhost/JSONkeeper/as/collection.json'

class TermEntry(Base):
    __tablename__ = 'termentry'
    term = Column(String(255), primary_key=True)
    json_string = Column(UnicodeText())

engine = create_engine('sqlite:///index.db')
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
# for all AC pages
while True:
    # for all AC items
    # TODO: compare endTime to last crawl time
    for item in as_ocp['orderedItems']:
        # if it's a Canvas create
        if item['type'] == 'Create' and \
                item['object']['@type'] == 'cr:Curation':
            cur = get_referenced(item, 'object')
            for ran in cur.get('selections', []):
                # Manifest is the same for all Canvases ahead, so get it now
                man = get_referenced(ran, 'within')
                for can in ran.get('members'):
                    # build doc and store in index under 'term'
                    doc = {}
                    doc['can'] = can['@id']
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

for term, doc in index.items():
    entry = session.query(TermEntry).filter(TermEntry.term == term).first()
    if entry:
        json_arr = json.loads(entry.json_string)
        skip = [c['can'] for c in json_arr]
        for can in doc:
            if not can['can'] in skip:
                json_arr.append(doc)
        entry.json_string = json.dumps(json_arr)
        session.commit()
    else:
        entry = TermEntry(term=term, json_string=json.dumps(doc))
        session.add(entry)
        session.commit()
