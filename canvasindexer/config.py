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

    def facet_inner_sort_freqency(self):
        return self.cfg['facet_inner_sort_freqency']

    def facet_inner_sort_alphanum(self):
        return self.cfg['facet_inner_sort_alphanum']

    def _get_default_config(self):
        # later read from config file
        cfg = {}
        cfg['db_uri'] = 'sqlite:////tmp/ci_tmp.db'
        cfg['as_sources'] = []
        cfg['facet_sort_front'] = []
        cfg['facet_sort_back'] = []
        cfg['facet_inner_sort_freqency'] = []
        cfg['facet_inner_sort_alphanum'] = []
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
        if 'api' in cp.sections():
            sort_options = ['facet_sort_front',
                            'facet_sort_back',
                            'facet_inner_sort_freqency',
                            'facet_inner_sort_alphanum']
            for so in sort_options:
                if cp['api'].get(so):
                    val = cp['api'].get(so)
                    cfg[so] = [o.strip() for o in val.split(',') if len(o) > 0]

        if fails:
            fail = '\n'.join(fails)
        else:
            fail = False

        return fail, cfg
