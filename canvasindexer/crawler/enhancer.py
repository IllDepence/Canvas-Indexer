import datetime
import json
import requests
from flask import abort
from canvasindexer.models import db, Term, Canvas, TermCanvasAssoc, BotState
from canvasindexer.config import Cfg
from sqlalchemy import and_

cfg = Cfg()


def log(msg):
    """ Write a log message.
    """

    timestamp = str(datetime.datetime.now()).split('.')[0]
    with open(cfg.crawler_log_file(), 'a') as f:
        f.write('[{}]   <ENHANCER> {}\n'.format(timestamp, msg))


def post_job(bot_url, callback_url):
    """ Given a bot URL, post job with all Canvases not yet posted.
    """

    # get bot state
    state_db = BotState.query.filter(BotState.bot_url == bot_url).first()
    all_canvases_db = Canvas.query.all()
    if all_canvases_db:
        all_canvases = [json.loads(c.json_string) for c in all_canvases_db]
    else:
        return 0
    if not state_db:
        finished_canvases = []
        state_db = BotState(bot_url=bot_url,
                            waiting_job_id=-1,
                            finished_canvases=json.dumps(finished_canvases))
        new_canvases = all_canvases
    else:
        if state_db.waiting_job_id != -1:
            log(('Still waiting for results from bot. Aborting sending new job'
                 '.'))
            return -1
        finished_canvases = json.loads(state_db.finished_canvases)
        new_canvases = []
        for can in all_canvases:
            if can.canvas_uri not in finished_canvases:
                new_canvases.append(can)

    # prepare job
    job = {}
    job['imgs'] = []
    job['callback_url'] = callback_url
    for can in new_canvases:
        img = {}
        img['manifest_uri'] = can['manifestUrl']
        img['canvas_uri'] = '{}#{}'.format(can['canvasId'], can['fragment'])
        img['image_url'] = can['canvasThumbnail']
        job['imgs'].append(img)

    # send job and process response
    resp = requests.post(bot_url,
                         headers={'Accept': 'application/json',
                                  'Content-Type': 'application/json'},
                         data=json.dumps(job))
    if resp.status_code != 200:
        log(('Unexpected response from bot with URL "{}". Status code: {}'
             ).format(bot_url, resp.status_code))
        return -2
    try:
        j_resp = resp.json()
        job_id = j_resp['job_id']
    except json.decoder.JSONDecodeError:
        log('Non-JSON response from bot with URL "{}".'.format(bot_url))
        return -2
    except (TypeError, KeyError):
        log('Unexpected JSON response format from bot with URL "{}".')
        return -2

    # update bot state
    state_db.finished_canvases = json.dumps(finished_canvases + new_canvases)
    state_db.waiting_job_id = job_id
    db.session.add(state_db)
    db.session.commit()

    # TODO: if this function returns early, should there be some retry
    #       mechanism such that retrying is not dependent on the crawling
    #       process? (assuming a regular crawling interval this might not be
    #       necessary)
    return 1


def enhance(request):
    """ Function to be called from an API endpoint to which bots return
        results.
    """

    json_bytes = request.data
    try:
        json_string = json_bytes.decode('utf-8')
        job_result = json.loads(json_string)
    except:
        return abort(400, 'No valid JSON provided.')
    if type(job_result) != dict or \
            'job_jd' not in job_result or \
            'results' not in job_result:
        return abort(400, 'No valid job results provided.')

    job_id = job_result['job_id']
    results = job_result['results']

    # TODO: ideally check HTTP referrer against bot url
    #       or make Canvas Indexer dictate job id in request
    state_db = BotState.query.filter(BotState.waiting_job_id == job_id).first()
    state_db.waiting_job_id = -1
    db.session.add(state_db)
    db.session.commit()

    for result in results:
        for tag in result['tags']:
            term = Term.query.filter(and_(Term.term == tag,
                                          Term.qualifier == 'tag')
                                     ).first()
            if not term:
                term = Term(term=tag, qualifier='tag')
                db.session.add(term)
                db.session.flush()

            canvas = Canvas.query.filter(
                            Canvas.canvas_uri == result['canvas_uri']).first()
            if not canvas:
                return abort(400, 'Result for inexistent canvas.')

            assoc = TermCanvasAssoc(term_id=term.id,
                                    canvas_id=canvas.id,
                                    metadata_type='canvas',
                                    actor='bot')
            db.session.add(assoc)
    db.session.commit()
