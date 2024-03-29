""" Class to comfortably get config values.
"""

import configparser
import os
import sys


class Cfg():

    def __init__(self, path='config.ini'):
        cp = configparser.ConfigParser()
        if os.path.exists(path):
            cp.read(path)
        else:
            print('No config file "{}". Using defaults.'.format(path))
        fail, cfg = self._parse_config(cp)
        if fail:
            print(fail)
            print('Exiting.')
            sys.exit(1)
        self.cfg = cfg

    def db_uri(self):
        return self.cfg['db_uri']

    def as_sources(self):
        return self.cfg['as_sources']

    def crawler_interval(self):
        return self.cfg['crawler_interval']

    def crawler_log_file(self):
        return self.cfg['crawler_log_file']

    def allow_orphan_canvases(self):
        return self.cfg['allow_orphan_canvases']

    def facet_label_sort_top(self):
        return self.cfg['facet_label_sort_top']

    def facet_label_sort_bottom(self):
        return self.cfg['facet_label_sort_bottom']

    def facet_label_hide(self):
        return self.cfg['facet_label_hide']

    def facet_value_sort_frequency(self):
        return self.cfg['facet_value_sort_frequency']

    def facet_value_sort_alphanum(self):
        return self.cfg['facet_value_sort_alphanum']

    def custom_value_sorts(self):
        return self.cfg['custom_value_sorts']

    def serv_url(self):
        return self.cfg['server_url']

    def api_path(self):
        return self.cfg['api_path']

    def bot_urls(self):
        return self.cfg['bot_urls']

    def e_term(self):
        """ Return a placeholder term that will be associated with all
            documents to ensure documents w/o any metadata (yet) will also be
            indexed. (In the current implementation indexing is dependent on
            metadata because we directly store search results in the index,
            which can differ depending on the associated metadata.)
        """

        return '<e‌m‌p‌t‌y>'

    def _get_default_config(self):
        # later read from config file
        cfg = {}
        cfg['db_uri'] = 'sqlite:////tmp/ci_tmp.db'
        cfg['as_sources'] = []
        cfg['crawler_interval'] = 3600
        cfg['crawler_log_file'] = '/tmp/ci_crawl_log.txt'
        cfg['allow_orphan_canvases'] = False
        cfg['server_url'] = 'http://localhost:5005'
        cfg['api_path'] = 'api'
        cfg['bot_urls'] = []
        cfg['facet_label_sort_top'] = []
        cfg['facet_label_sort_bottom'] = []
        cfg['facet_label_hide'] = []
        cfg['facet_value_sort_frequency'] = []
        cfg['facet_value_sort_alphanum'] = []
        cfg['custom_value_sorts'] = {}
        return cfg

    def _parse_config(self, cp):
        """ Prase a configparser.ConfigParser instance and return
                - a fail message in case of an invalid config (False otherwise)
                - a config dict
        """

        cfg = self._get_default_config()
        fails = []

        # Environment
        if 'shared' in cp.sections():
            if cp['shared'].get('db_uri'):
                cfg['db_uri'] = cp['shared'].get('db_uri')
        if 'crawler' in cp.sections():
            if cp['crawler'].get('as_sources'):
                as_sources = cp['crawler'].get('as_sources')
                cfg['as_sources'] = [s.strip() for s in as_sources.split(',')
                                     if len(s) > 0]
            if cp['crawler'].get('interval'):
                try:
                    str_val = cp['crawler'].get('interval')
                    cfg['crawler_interval'] = int(str_val)
                except ValueError:
                    fails.append(('interval in crawler section must be an inte'
                                  'ger'))
            crawler_log_file = cp['crawler'].get('log_file', False)
            if crawler_log_file and len(crawler_log_file) > 0:
                cfg['crawler_log_file'] = crawler_log_file
            if cp['crawler'].get('allow_orphan_canvases'):
                cfg['allow_orphan_canvases'] = cp['crawler'].getboolean(
                                                    'allow_orphan_canvases')
        # Sorting of API responses
        if 'api' in cp.sections():
            if cp['api'].get('server_url'):
                cfg['server_url'] = cp['api'].get('server_url')
            if cp['api'].get('api_path'):
                cfg['api_path'] = cp['api'].get('api_path')
            if cp['api'].get('bot_urls'):
                val = cp['api'].get('bot_urls')
                cfg['bot_urls'] = [u.strip() for u in val.split(',') if len(u) > 0]
            sort_options = ['facet_label_sort_top',
                            'facet_label_sort_bottom',
                            'facet_label_sort_bottom',
                            'facet_value_sort_frequency',
                            'facet_value_sort_alphanum']
            for so in sort_options:
                if cp['api'].get(so):
                    val = cp['api'].get(so)
                    cfg[so] = [o.strip() for o in val.split(',') if len(o) > 0]
            if cp['api'].get('facet_label_hide'):
                val = cp['api'].get('facet_label_hide')
                cfg['facet_label_hide'] = [h.strip() for h in val.split(',') if len(h) > 0]
        for sec_name in cp.sections():
            if 'facet_value_sort_custom_' in sec_name:
                custom_sort = {}
                label = cp[sec_name].get('label')
                sort_top = cp[sec_name].get('sort_top', '')
                sort_top = [o.strip() for o in sort_top.split(',')
                                                                if len(o) > 0]
                sort_bottom = cp[sec_name].get('sort_bottom', '')
                sort_bottom = [o.strip() for o in sort_bottom.split(',')
                                                                if len(o) > 0]
                if label and len(sort_top + sort_bottom) > 0:
                    custom_sort['sort_top'] = sort_top
                    custom_sort['sort_bottom'] = sort_bottom
                    cfg['custom_value_sorts'][label] = custom_sort

        if fails:
            fail = '\n'.join(fails)
        else:
            fail = False

        return fail, cfg
