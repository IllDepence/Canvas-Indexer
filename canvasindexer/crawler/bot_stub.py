""" bot stub

    Minimal bot stub to serve as an example.
    Not really part of the Canvas Indexer code base.
"""

import json
import random
import requests
from flask import (abort, Flask, request, Response)
from flask_cors import CORS


app = Flask(__name__)
CORS(app)
random.seed()


def get_tags(img_url):
    return ['foo', 'bar']


@app.route('/job', methods=['POST'])
def job():
    """ Receive a job.
    """

    json_bytes = request.data
    try:
        json_string = json_bytes.decode('utf-8')
        job_obj = json.loads(json_string)
    except:
        return abort(400, 'No valid JSON provided.')
    if type(job_obj) != dict or \
            'imgs' not in job_obj or \
            'callback_url' not in job_obj:
        return abort(400, 'No valid job list provided.')

    job_id = random.randint(1, 999)

    # TODO: start to process and then call callback asynchronously
    #       callback(job_obj, job_id)

    resp = Response(json.dumps({'job_id': job_id}))
    return resp


def callback(job_obj, job_id):
    results = []
    for img in job_obj['imgs']:
        result = {}
        tags = get_tags(img['img_url'])
        result['tags'] = tags
        result['canvas_uri'] = img['canvas_uri']
        result['manifest_uri'] = img['manifest_uri']
        results.append(result)

    resp = requests.post(job_obj['callback_url'],
                         headers={'Accept': 'application/json',
                                  'Content-Type': 'application/json'},
                         data=json.dumps(results))

if __name__ == '__main__':
    app.run(host='0.0.0.0')
