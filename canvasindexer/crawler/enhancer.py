import json
import requests
from canvasindexer.models import Term, Canvas, TermCanvasAssoc, BotState
from canvasindexer.config import Cfg

cfg = Cfg()

def log(msg):
    """ Write a log message.
    """

    timestamp = str(datetime.datetime.now()).split('.')[0]
    with open(cfg.crawler_log_file(), 'a') as f:
        f.write('[{}]   <ENHANCER> {}\n'.format(timestamp, msg))

def post_job(bot_url):
    """ Given a bot URL, post job with all Canvases not yet posted.
    """

    # get bot state
    state_db = BotState.query.filter(BotState.bot_url == bot_url).first()
    all_canvases_db = Canvas.query.all()
    if all_canvases_db:
        all_canvases = [json.loads(c.json_string) for c in all_canvases_db]
    else:
        return
    if not state_db:
        finished_canvases=[]
        state_db = BotState(bot_url=bot_url,
                            waiting_job_id=-1,
                            finished_canvases=json.dumps(finished_canvases))
        new_canvases = all_canvases
    else:
        if state_db.waiting_job_id != -1:
            log(('Still waiting for resulst from bot. Aborting sending new job'
                 '.'))
            return
        finished_canvases = json.loads(state_db.finished_canvases)
        new_canvases = []
        for can in all_canvases:
            if can.canvas_uri not in finished_canvases:
                new_canvases.append(can)

    # prepare job
    job = []
    for can in new_canvases:
        img = {}
        img['manifest_uri'] = can['manifestUrl']
        img['canvas_uri'] = '{}#{}'.format(can['canvasId'], can['fragment'])
        img['image_url'] = can['canvasThumbnail']
        job.append(img)

    # send job and process response
    resp = requests.post(bot_url,
                         headers={'Accept': 'application/json',
                                  'Content-Type': 'application/json'},
                         data=json.dumps(job))
    if resp.status_code != 200:
        log(('Unexpected response from bot with URL "{}". Status code: {}'
            ).format(bot_url, resp.status_code))
        return
    try:
        j_resp = resp.json()
        job_id = j_resp['job_id']
    except json.decoder.JSONDecodeError as e:
        log('Non-JSON response from bot with URL "{}".')
        return
    except TypeError, KeyError:
        log('Unexpected JSON response format from bot with URL "{}".')
        return

    # update bot state
    state_db.finished_canvases = json.dumps(new_canvases)
    state_db.waiting_job_id = job_id
    db.session.add(state_db)
    db.session.commit()

    # TODO: if this function returns early, should there be some retry
    #       mechanism such that retrying is not dependent on the crawling
    #       process? (assuming a regular crawling interval this might not be
    #       necessary)

def enhance():
    """ Function to be called from an API endpoint to which bots return
        results.
    """

    # create terms if necessary
    # create assocs

    # update bot state
    # state_db.waiting_job_id = -1

    pass
