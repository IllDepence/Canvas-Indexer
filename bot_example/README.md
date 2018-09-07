### SETUP

* `$ python3 -m venv venv`
* `$ source venv/bin/activate`
* `$ pip3 install -r requirements.txt`

### USAGE

* start celery worker
    * `$ source venv/bin/activate`
    * `celery -A bot_example.celery worker`
* start web app
    * `$ source venv/bin/activate`
    * `FLASK_APP=bot_example.py flask run --host=0.0.0.0` (not to be used in production)
