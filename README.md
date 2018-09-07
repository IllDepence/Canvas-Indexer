![Canvas Indexer](logo_500px.png)

A flask web application that crawls Activity Streams for IIIF Canvases and offers a search API.

## Project state

Canvas Indexer is being developed as part of the [CODH's IIIF Curation Platform](codh.rois.ac.jp/iiif-curation-platform/), *but* meant to be a general IIIF tool. Integration into the IIIF Curation Platform means that in this very early stage there is a focus on cr:Curation<sup>[1]</sup> type documents.<sup>[2]</sup> Nevertheless all development is done with generality in mind.<sup>[3]</sup>

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
api | facet\_label\_sort\_top | [] | comma seperated list defining the beginning of the list returned for the `/facets` endpoint
&zwnj; | facet\_label\_sort\_bottom | [] | comma seperated list defining the end of the list returned for the `/facets` endpoint
&zwnj; | facet\_value\_sort\_frequency | [] | comma seperated list of facets to be sorted by frequency
&zwnj; | facet\_value\_sort\_alphanum | [] | comma seperated list of facets to be sorted alphanumerically
facet\_value\_sort\_<br>custom\_&lt;name&gt; | label | &zwnj; | facet label for which a custom order is defined
&zwnj; | sort\_top | &zwnj; | comma seperated list defining the beginning
&zwnj; | sort\_bottom | &zwnj; | comma seperated list defining the end

## Run
### Crawler

    $ source venv/bin/activate
    $ python3 run_crawler.py

#### Notes

* The crawler is designed to be run periodically. On its first run it will go through an Activity Stream in its entirety, subsequent runs will only regard Activities that occured *after* the previous run.
* In its current state the crawler indexes only the label value pairs given in a IIIF resource's [metadata](http://iiif.io/api/presentation/2.1/#metadata) property.

### Search API

    $ source venv/bin/activate
    $ python3 run.py [debug]

## API

**path: `{base_url}/api`**  
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

example: `{base_url}/api?select=canvas&from=canvas,curation&where=face`


**path: `{base_url}/facets`**  
returns a pre generated overview of the indexed metadata facets

- - -

## Logo
The Canvas Indexer logo uses image content from [絵本花葛蘿](http://codh.rois.ac.jp/pmjt/book/200015291/) in the [日本古典籍データセット（国文研所蔵）](http://codh.rois.ac.jp/pmjt/book/) provided by the [Center for Open Data in the Humanities](http://codh.rois.ac.jp/), used under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/).
The Canvas Indexer logo is licensed under [CC-BY-SA 4.0](http://creativecommons.org/licenses/by-sa/4.0/) by Tarek Saier. A high resolution version (4456×2326 px) can be downloaded [here](http://moc.sirtetris.com/canvas_indexer_logo_full.png).

## Support
Sponsored by the National Institute of Informatics.  
Supported by the Center for Open Data in the Humanities, Joint Support-Center for Data Science Research, Research Organization of Information and Systems.
