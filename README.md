![Canvas Indexer](logo_500px.png)

A flask web application that crawls Activity Streams for IIIF Canvases and offers a search API.

## Project state

Canvas Indexer is being developed as part of the [CODH's IIIF Curation Platform](http://codh.rois.ac.jp/iiif-curation-platform/), but can also be used as a general IIIF tool. Integration into the IIIF Curation Platform means that there is a focus on cr:Curation<sup>[1]</sup> type documents.<sup>[2]</sup> Nevertheless all development is done with generality in mind.<sup>[3]</sup>

[1] `http://codh.rois.ac.jp/iiif/curation/1#Curation`  
[2] The crawler currently only looks for canvases within them (and not, for example, sc:Manifests) and the search API offers dedicated parameters.  
[3] The crawling process implements the [IIIF Change Discovery API 0.1](http://preview.iiif.io/api/discovery/api/discovery/0.1/) and extending the indexing mechanism and search API to support IIIF documents within Activity Streams *in general* (or at least sc:Manifests for a first step) should be straightforward.

## Setup

* create virtual environment: `$ python3 -m venv venv`
* activate virtual environment: `$ source venv/bin/activate`
* install requirements: `$ pip install -r requirements.txt`

## Config

section | key | default | explanation
------- | --- | ------- | -----------
shared | db\_uri | sqlite:////tmp/ci\_tmp.db | a [SQLAlchemy database URI](http://docs.sqlalchemy.org/en/latest/core/engines.html#database-urls) (file system paths have to be absolute)
crawler | as\_sources | [] | comma seperated list of links to [Activity Streams](https://www.w3.org/TR/activitystreams-core/) in form of OrderedCollections
&zwnj; | interval | 3600 | crawl interval in seconds (value <=0 deactivates automatic crawling)
&zwnj; | log\_file | /tmp/ci\_crawl\_log.txt | file system path to where the crawling details should be logged
&zwnj; | allow\_orphan\_canvases | false | set whether or not Canvases, that are not associated with any parent elements in the index anymore, should still appear in search results
api | server\_url | http://localhost:5005 | URL under which Canvas Indexer can be accessed (used to set the `@id` attribute of curation format search results ([see API section](#api)) and when using tagging bots ([see bot intergration section](#bot-integration)))
&zwnj; | api\_path | api | specifies the endpoint for API access<br>(e.g. `search` →  `http://indexcanvases.com/search` or `http://sirtetris.com/canvasindexer/search`)
&zwnj; | bot\_urls | [] | comma seperated list of URLs to bots (only needed when using bots ([details below](#bot-integration)))
&zwnj; | facet\_label\_sort\_top | [] | comma seperated list defining the beginning of the list returned for the `/facets` endpoint
&zwnj; | facet\_label\_sort\_bottom | [] | comma seperated list defining the end of the list returned for the `/facets` endpoint
&zwnj; | facet\_value\_sort\_frequency | [] | comma seperated list of facets to be sorted by frequency
&zwnj; | facet\_value\_sort\_alphanum | [] | comma seperated list of facets to be sorted alphanumerically
&zwnj; | facet\_label\_hide | [] | comma seperated list of facets labels to hide from API output
facet\_value\_sort\_<br>custom\_&lt;name&gt; | label | &zwnj; | facet label for which a custom order is defined
&zwnj; | sort\_top | &zwnj; | comma seperated list defining the beginning
&zwnj; | sort\_bottom | &zwnj; | comma seperated list defining the end

## Run

### Directly through Flask

    $ source venv/bin/activate
    $ python3 run.py [debug]

### Using gunicorn

    $ source venv/bin/activate
    $ pip install gunicorn
    $ ./venv/bin/gunicorn 'canvasindexer:create_app()'

**Note** that gunicorn per default times out requests [after 30 seconds](https://docs.gunicorn.org/en/stable/settings.html#timeout), which can interfere with long crawling procedures (e.g. the first crawl of a large Activity Stream). The timeout can be changed by creating a file `gunicorn_config.py` and inserting a line like `timeout = 3600` (for a timeout of one hour) or `timeout = 0` to deactivate timeouts alltogether. To start Canvas Indexer using this config run

    $ ./venv/bin/gunicorn -c gunicorn_config.py 'canvasindexer:create_app()'

## API

**path: `{base_url}/api` / `{base_url}/{api_path}`**  
arguments:

arg | default | explanation
--- | -------- | -----------
select | `curation` | set the type of search results to be returned to either `canvas` or `curation`
from | `curation,canvas` | set the type of metadata the search results should be based on to `canvas`, `curation` or a comma seperated list of aforementioned
where |  | search keyword
where\_metadata\_label |  | used to search by a property+value pair. requires where\_metadata\_value
where\_metadata\_value |  | used to search by a property+value pair. requires where\_metadata\_label
where\_agent | `human,machine` | set the type of metadata creator to `human`, `machine` or a comma seperated list of aforementioned
start | `0` | 0 based index from which to start listing results from the list of all results
limit | `null` meaning no limit | limit the number of results being returned
output | | if set to `curation` and `select=cavnas` search results will be returned as a curation

example: `{base_url}/api?select=canvas&from=canvas,curation&where=face`


**path: `{base_url}/parents`**  
returns the list of curations that contain a given canvas or canvas area

arguments:

arg | default | explanation
--- | -------- | -----------
canvas | `null` | URL encoded canvas ID
xywh | `null` | optional xywh fragment (needs to match exactly)


**path: `{base_url}/facets`**  
returns a pre generated overview of the indexed metadata facets

## Crawler

* The crawler can be configured to run periodically (see [Config](#config)) or triggered manually by accessing `{base_url}/crawl`.
* On its first run the crawler will go through an Activity Stream in its entirety, subsequent runs will only regard Activities that occured *after* the previous run.
* In its current state the crawler indexes only the label value pairs given in a IIIF resource's [metadata](http://iiif.io/api/presentation/2.1/#metadata) property.

## Bot integration

Canvas Indexer can be set up to send image URLs of the canvases it indexes to bots that return tags. These tags are then integrated in the index. Example code of a bot can be found in the folder [bot\_example](bot_example).

- - -

## Logo
The Canvas Indexer logo uses image content from [絵本花葛蘿](http://codh.rois.ac.jp/pmjt/book/200015291/) in the [日本古典籍データセット（国文研所蔵）](http://codh.rois.ac.jp/pmjt/book/) provided by the [Center for Open Data in the Humanities](http://codh.rois.ac.jp/), used under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/).
The Canvas Indexer logo is licensed under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/) by Tarek Saier. A high resolution version (4456×2326 px) can be downloaded [here](http://moc.sirtetris.com/canvas_indexer_logo_full.png).

## Support
Sponsored by the National Institute of Informatics.  
Supported by the Center for Open Data in the Humanities, Joint Support-Center for Data Science Research, Research Organization of Information and Systems.
