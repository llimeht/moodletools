""" Configuration of the moodletools utilities

"""

# Copyright (c) 2017-2018 Stuart Prescott

import collections
import glob
import importlib
import logging
import os.path

import yaml


logger = logging.getLogger(__name__)


def auto_configure(start_directory=os.path.curdir, levels=2, home=True):
    filenames = find_config_filenames(start_directory, levels, home)
    return MtConfig.from_filenames(filenames)


def find_config_filenames(start_directory=os.path.curdir, levels=2, home=True):
    search = [start_directory]

    for _ in range(levels):
        search.append(os.path.join(search[-1], os.path.pardir))

    if home:
        search.append(os.path.expanduser("~/"))

    files = []

    for d in search:
        files.extend(glob.glob(os.path.join(d, '.moodletools.yaml')))

    logger.debug("Config files: %s", ", ".join(files))
    return files


def parse_login_callable(login_spec):
    logging.debug("Login configuration: '%s'", login_spec)
    module, _, func = login_spec.partition(':')
    if not module or not func:
        raise ValueError(
            "login function must be of form 'module.submodule:func'")

    logging.debug("Login module: '%s', function '%s'", module, func)

    try:
        mod = importlib.import_module(module)
    except ImportError:
        raise ValueError(
            "specified login module not loadable; not right path?")

    try:
        call = getattr(mod, func)
    except AttributeError:
        raise ValueError(
            "specified login function not found in module")

    if not callable(call):
        raise ValueError(
            "specified login function doesn't seem to be a function")

    return call


class MtConfig:

    def __init__(self, data=None):
        if data is None:
            data = {}
        self.data = data

    def load_default(self):
        filename = os.path.join(os.path.dirname(__file__),
                                'defaultconfig.yaml')
        with open(filename) as fh:
            conf = self._from_stream(fh)
        self.data = conf

    @classmethod
    def from_filenames(cls, filenames):
        conf = cls()
        conf.load_default()
        for filename in reversed(filenames):
            with open(filename) as fh:
                newconf = cls._from_stream(fh)
            conf.merge(newconf)
        return conf

    @classmethod
    def from_filename(cls, filename):
        with open(filename) as fh:
            return cls.from_stream(fh)

    @classmethod
    def from_stream(cls, stream):
        conf = cls()
        conf.load_default()
        conf.merge(cls._from_stream(stream))
        return conf

    @staticmethod
    def _from_stream(stream):
        return yaml.load(stream)

    def merge(self, additions):
        self._merge(self.data, additions)

    @staticmethod
    def _merge(current, additions):
        for k, v in additions.items():
            if (k in current and isinstance(current[k], dict)
                    and isinstance(v, collections.Mapping)):
                MtConfig._merge(current[k], v)
            else:
                current[k] = v

    def login_callable(self):
        return parse_login_callable(self.data['site']['login'])

    def cache_settings(self, force, disable):
        self.data['cache']['force'] = force
        if disable:
            self.data['cache']['location'] = None

    @property
    def cache_force(self):
        return self.data['cache']['force']

    @property
    def cache_location(self):
        return self.data['cache']['location']

    @property
    def course(self):
        return self.data['course']['id']

    @course.setter
    def course(self, course_id):
        self.data['course']['id'] = course_id
