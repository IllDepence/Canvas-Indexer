import requests

AS_URL = 'http://localhost/JSONkeeper/as/collection.json'

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
        if item['type'] == 'Create' and item['object']['@type'] == 'sc:Canvas':
            # build doc and store in index under 'term'
            doc = {}
            can = get_referenced(item, 'object')
            man = get_referenced(can, 'within')
            # term and Canvas URI
            term = ''
            can_uri = ''
            for md in can.get('metadata', []):
                if md['label'] == 'subject':
                    term = md['value']
                if md['label'] == 'origin':
                    can_uri = md['value']
            doc['can'] = can_uri
            # image URI
            for seq in man.get('sequences', []):
                for o_can in seq.get('canvases', []):
                    if o_can['@id'] in can_uri:
                        # ↓ not too hardcoded?
                        img = o_can['images'][0]['resource']['@id']
                        doc['img'] = img
            if term not in index.keys():
                index[term] = []
            index[term].append(doc)

    if not as_ocp.get('prev', False):
        break
    as_ocp = get_referenced(as_ocp, 'prev')

import pprint
pprint.pprint(index)
