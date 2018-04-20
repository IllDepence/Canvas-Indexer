![Canvas Indexer](logo_500px.png)

A flask web application that crawls Activity Streams for IIIF Canvases and offers a search API.

## Setup

* create virtual environment: `$ python3 -m venv venv`
* activate virtual environment: `$ source venv/bin/activate`
* install requirements: `$ pip install -r requirements.txt`

## Config

section | key | default | explanation
------- | --- | ------- | -----------
shared | db\_uri | sqlite:////tmp/ci\_tmp.db | a [SQLAlchemy database URI](http://docs.sqlalchemy.org/en/latest/core/engines.html#database-urls)
crawler | as\_sources | [] | comma seperated list of links to [Activity Streams](https://www.w3.org/TR/activitystreams-core/) in form of OrderedCollections

## Run

    $ source venv/bin/activate
    $ python3 run.py [debug]

## API

path: `{base_url}/api`  
arguments:

arg | required | explanation
--- | -------- | -----------
q | yes | query
start | no | 0 based index from which to start listing results from the list of all results<br>defaults to `0`
limit | no | limit the number of results being returned<br>defaults to `null` meaning no limit
source | no | set the type of metadata the search results should be based on to `canvas`, `curation` or `canvas\|curation`<br>detaults to `canvas`
granularity | no | set the type of search results to be returned to either `canvas` or `curation`<br>detaults to the value of source or `curation` in case source is `canvas\|curation`

example: `{base_url}/api?q=face&start=5&limit=10`

- - -

## Logo
The Canvas Indexer logo uses image content from [絵本花葛蘿](http://codh.rois.ac.jp/pmjt/book/200015291/) in the [日本古典籍データセット（国文研所蔵）](http://codh.rois.ac.jp/pmjt/book/) provided by the [Center for Open Data in the Humanities](http://codh.rois.ac.jp/), used under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/).
The Canvas Indexer logo is licensed under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/) by Tarek Saier.
