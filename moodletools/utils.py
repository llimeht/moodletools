""" Utilities for dealing with data from Moodle

"""

# Copyright (c) 2017-2018 Stuart Prescott

import logging
import os
import pickle
import time

logger = logging.getLogger(__name__)


class Cacher:
    """ On-disk caching for resources

    Downloading resources from the web site can be expensive in bandwidth
    and time so an on-disk cache can be greatly beneficial to the rest of the
    code, particularly during development or during repeated operations.

    This class is designed to accept requests.Response objects and save
    both the pickled Response object and also the data that was in the
    response payload. Only the Response object is rehydrated from the
    cache.

    :param name: str, the resource id in the cache; will be used as the
        filename for the pickled object.
    :param payload: bool, optional, default `True`.
        Separately save the payload from the Response object
    :param cache: str, optional, default `cache`.
        The directory into which the cache will be written.
    :param max_age: int, optional, default 3600.
        The maximum age in seconds for items within the cache. Older
        items will not be returned but instead a CacheMissError will
        be raised.
    :param force: bool, optional, default `False`.
        Redownload will be forced.
    """
    def __init__(self, name, payload=True,
                 cache='cache', max_age=3600, force=False):
        self.name = name
        self.payload = payload
        self.cache = cache
        self.cache_max_age = max_age
        self.force = force

        if self.enabled and not os.path.exists(self.cache):
            os.mkdir(self.cache)

    @property
    def enabled(self):
        """ The cache is enabled for both read and write """
        return self.name and self.cache is not None

    def _cache_filename(self):
        """ the file path for the Response object """
        return os.path.join(self.cache, self.name + ".response")

    def _cache_payload_filename(self):
        """ the file path for the payload object """
        return os.path.join(self.cache, self.name)

    def _cache_ok(self):
        """ the cache object exists and is usable """
        if not self.enabled:
            return False

        try:
            mtime = os.path.getmtime(self._cache_filename())
        except FileNotFoundError:
            return False
        return time.time() < mtime + self.cache_max_age

    def load(self):
        """ attempt to load the cached resource

        If the cache is disabled, re-download had been forced, the cached
        resource does not exist or the cached resource is too old,
        a CacheMissError is raised to permit the controlling code to
        otherwise download the resource.
        """
        if not self.force and self._cache_ok():
            with open(self._cache_filename(), 'rb') as fh:
                return pickle.load(fh)
        raise CacheMissError

    def save(self, response):
        """ save the response data into the cache

        If the cache is disabled, the response is not saved. Both
        response any payload can be saved into separate files.
        """
        if not self.enabled:
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
    """ Raised when the cache is unable to return the requested resource

    The calling code should instead download the resource and save it into
    the cache. A CacheMissError can be raised:

     * if cache is disabled
     * if re-download had been forced
     * if the cached resource does not exist
     * if the cached resource is too old
    """
    pass


def resid_factory(source, name='generic-%s', resid='auto'):
    """ create a cache resource identifier on demand

    :param source: the producer of the data, can be any type as long as it
        has a `id` member
    :param name: str, format string for the resource Id string if it is to be
        generated
    :param resid: str, optional. If 'auto' (the default), generate a resource
        id from the `source` and the `name` parameters. Otherwise, the value of
        `resid` itself is returned. If `None` caching will be disabled.

    :returns string: a (hopefully) unique id to save the resource in the cache
    """
    if resid == 'auto':
        return name.format(id=source.id)

    return resid
