""" Class to comfortably get config values.
"""

import configparser
import os
import sys


class Cfg():

    def __init__(self, path='config.ini'):
        cp = configparser.ConfigParser()
        if not os.path.exists(path):
            print('Config file "{}" not found.\nExiting.'.format(path))
            sys.exit(1)
        cp.read(path)
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

    def facet_sort_front(self):
        return self.cfg['facet_sort_front']

    def facet_sort_back(self):
        return self.cfg['facet_sort_back']

    def facet_inner_sort_frequency(self):
        return self.cfg['facet_inner_sort_frequency']

    def facet_inner_sort_alphanum(self):
        return self.cfg['facet_inner_sort_alphanum']

    def custom_inner_sorts(self):
        return self.cfg['custom_inner_sorts']

    def _get_default_config(self):
        # later read from config file
        cfg = {}
        cfg['db_uri'] = 'sqlite:////tmp/ci_tmp.db'
        cfg['as_sources'] = []
        cfg['facet_sort_front'] = []
        cfg['facet_sort_back'] = []
        cfg['facet_inner_sort_frequency'] = []
        cfg['facet_inner_sort_alphanum'] = []
        cfg['custom_inner_sorts'] = {}
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
        # Sorting of API responses
        if 'api' in cp.sections():
            sort_options = ['facet_sort_front',
                            'facet_sort_back',
                            'facet_inner_sort_frequency',
                            'facet_inner_sort_alphanum']
            for so in sort_options:
                if cp['api'].get(so):
                    val = cp['api'].get(so)
                    cfg[so] = [o.strip() for o in val.split(',') if len(o) > 0]
        for sec_name in cp.sections():
            if 'custom_inner_sort_' in sec_name:
                custom_sort = {}
                label = cp[sec_name].get('label')
                sort_front = cp[sec_name].get('sort_front', '')
                sort_front = [o.strip() for o in sort_front.split(',')
                                                                if len(o) > 0]
                sort_back = cp[sec_name].get('sort_back', '')
                sort_back = [o.strip() for o in sort_back.split(',')
                                                                if len(o) > 0]
                if label and len(sort_front + sort_back) > 0:
                    custom_sort['sort_front'] = sort_front
                    custom_sort['sort_back'] = sort_back
                    cfg['custom_inner_sorts'][label] = custom_sort

        if fails:
            fail = '\n'.join(fails)
        else:
            fail = False

        return fail, cfg
