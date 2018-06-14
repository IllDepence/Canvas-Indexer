import json
import requests
from canvasindexer.models import Term, Canvas, TermCanvasAssoc, BotState
from canvasindexer.config import Cfg

cfg = Cfg()

def post_job(bot_url):
    """ Given a bot URL, post job with all Canvases not yet posted.
    """

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
        finished_canvases = json.loads(state_db.finished_canvases)
        new_canvases = []
        for can in all_canvases:
            if can.canvas_uri not in finished_canvases:
                new_canvases.append(can)

    # state_db.finished_canvases = json.dumps(new_finished_canvases)
    # db.session.add(state_db)
    # db.session.commit()

def enhance():
    """
    """

    pass
