""" bot example

    Minimal bot implementation to serve as an example.
    Not really a part of the Canvas Indexer code base.
"""

import json
import random
import requests
from celery import Celery
from flask import (abort, Flask, request, Response)
from flask_cors import CORS


def get_tags(img_url):
    return ['foo', 'bar']


def make_celery(app):
    celery = Celery(
        'bot_example',
        backend=app.config['CELERY_RESULT_BACKEND'],
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery


app = Flask(__name__)
app.config.update(
    CELERY_BROKER_URL='redis://localhost:6379',
    CELERY_RESULT_BACKEND='redis://localhost:6379'
)
celery = make_celery(app)
CORS(app)
random.seed()


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

    job_id = random.randint(1, 999999)

    # call callback task asynchronously
    result = callback.delay(job_obj, job_id)

    resp = Response(json.dumps({'job_id': job_id}))
    return resp


@celery.task()
def callback(job_obj, job_id):
    results = []
    for img in job_obj['imgs']:
        result = {}
        tags = get_tags(img['img_url'])
        result['tags'] = tags
        result['canvas_uri'] = img['canvas_uri']
        result['manifest_uri'] = img['manifest_uri']
        results.append(result)

    ret = {}
    ret['job_id'] = job_id
    ret['results'] = results
    print('sending callback request for job #{}'.format(job_id))
    resp = requests.post(job_obj['callback_url'],
                         headers={'Accept': 'application/json',
                                  'Content-Type': 'application/json'},
                         data=json.dumps(ret),
                         timeout=60)
    print(resp.status_code)


if __name__ == '__main__':
    app.run(host='0.0.0.0')
