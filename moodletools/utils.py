""" Utilities for dealing with data from Moodle

"""

# Copyright (c) 2017-2018 Stuart Prescott

import logging
import os
import pickle
import time

logger = logging.getLogger(__name__)


class Cacher:
    """

    """
    def __init__(self, name, payload=True, cache='cache', max_age=3600):
        self.name = name
        self.payload = payload
        self.cache = cache
        self.cache_max_age = max_age

        if not os.path.exists(self.cache):
            os.mkdir(self.cache)

    def _cache_filename(self):
        return os.path.join(self.cache, self.name + ".response")

    def _cache_payload_filename(self):
        return os.path.join(self.cache, self.name)

    def _cache_ok(self):
        if not self.name:
            return False

        try:
            mtime = os.path.getmtime(self._cache_filename())
        except FileNotFoundError:
            return False
        return time.time() < mtime + self.cache_max_age

    def load(self):
        if self._cache_ok():
            with open(self._cache_filename(), 'rb') as fh:
                return pickle.load(fh)
        raise CacheMissError

    def save(self, response):
        if not self.name:
            return

        filename = self._cache_payload_filename()
        with open(filename, 'wb') as fh:
            logger.debug("Caching payload to %s", filename)
            fh.write(response.content)

        filename = self._cache_filename()
        with open(filename, 'wb') as fh:
            logger.debug("Caching response to %s", filename)
            pickle.dump(response, fh)


class CacheMissError(Exception):
    pass


def resid_factory(source, resid, name):
    if resid == 'auto':
        return name.format(id=source.id)

    return resid
