""" Class to comfortably get config values.
"""

import configparser
import os
import re
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

    def _get_default_config(self):
        # later read from config file
        cfg = {}
        cfg['db_uri'] = 'sqlite:///index.db'
        return cfg

    def set_debug_config(self, id_rewrite, as_serve):
        cfg = {}
        cfg['db_uri'] = 'sqlite://'
        self.cfg = cfg

    def _parse_config(self, cp):
        """ Prase a configparser.ConfigParser instance and return
                - a fail message in case of an invalid config (False otherwise)
                - a config dict
        """

        cfg = self._get_default_config()
        fails = []

        # Environment
        if 'environment' in cp.sections():
            if cp['environment'].get('db_uri'):
                cfg['db_uri'] = cp['environment'].get('db_uri')

        if fails:
            fail = '\n'.join(fails)
        else:
            fail = False

        return fail, cfg
