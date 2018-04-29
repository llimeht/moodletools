""" Classes for interrogating and configuring Moodle

These classes represent the view of a Moodle course as seen by an individual
instructor or student. They expose limited functionality to alter Moodle
courses or activities within a Moodle course with intention of making it
easier to automate common tasks.

Moodle exposes little by way of meaningful, stable or documented API, with
no REST or AJAX API being documented. Consequently, these tools have been
created by reverse engineering the HTML forms and the URLs used by Moodle
to perform various actions. This necessarily makes these tools fragile
in the face of upgrades to Moodle. That said, little breakage has been
experienced from Moodle 2.6 through to 3.3.

Example usage
=============

The following logs into the demo.moodle.net example instance of Moodle,
adds some labels to course with id 2 and then hides them all::

    >>> from moodletools.auth import demo_moodle_net
    >>> demomoodle = demo_moodle_net.login_as_teacher()
    >>> course = demomoodle.course(2)
    >>> for i in range(4):
    ...     label = course.label(-1)
    ...     label.create(1, 'New label text %d' % i)
    >>> course.hide_all()
"""

# Copyright (c) 2015-2018 Stuart Prescott

import logging
import re

import bs4

from moodletools.course import Course
from moodletools.utils import (Cacher, CacheMissError, resid_factory)


logger = logging.getLogger(__name__)


class Moodle:
    """ Moodle connection instance

    Instances of this class represent a logged in Moodle session and it
    is able to fetch resources from the remote Moodle. It is not intended
    that Moodle instances be used for much other than to spawn Course
    objects that can then work with each course.

    Example:
    >>> session = requests.Session()
    >>> session.post(url, login_details)
    >>> mymoodle = Moodle(url, session)
    >>> mycourse = mymoodle.course(12345)

    """
    def __init__(self, base_url, session):
        """ Create a Moodle class

        base_url: str
            the base URL of the Moodle instance
        session:
            a requests.Session object that has done the relevant authentication
            dance and so subsequent requests are automatically authenticated
            using cookies.
        """
        # ensure that the base URL ends in / for later concatenation
        if not base_url.endswith('/'):
            base_url += '/'

        self.base_url = base_url
        self.session = session
        self._sesskey = None
        self.cache_max_age = 1800
        self.cache = 'cache'
        self.payload = True

    def sesskey(self):
        """ return the sesskey for the session """
        if not self._sesskey:
            self.get_dashboard_page()
        return self._sesskey

    @property
    def has_sesskey(self):
        return self._sesskey is not None

    def set_sesskey(self, page):
        """ opportunistically harvest the sesskey from the page """
        if self._sesskey:
            return

        bs = bs4.BeautifulSoup(page.text, 'lxml')

        explicit = bs.find('input', {'name': 'sesskey'})
        if explicit:
            self._sesskey = explicit['value']
            return

        sesskey_re = re.compile("^https?://.*/.*sesskey=([^&]+)")
        implicit = bs.find('a', {'href': sesskey_re})
        if implicit:
            match = sesskey_re.match(implicit['href'])
            self._sesskey = match.group(1)
            return

    _dashboard_page_url = "my/"

    def get_dashboard_page(self, resid='auto'):
        """ return a requests.Response object for the site dashboard page

        :param resid: str, optional, default `auto`
            The resource id in the cache; if set to `auto`, the
            value `course-dashboard-{id}` will be used. `None`
            disables caching.
        :param force: bool, optional, default `False`.
            Forces redownload of the resource.
            Note that if the login session key has not yet been extracted
            from the session, requesting redownload will be forced in
            any case.
        """
        resid = resid_factory(self, "course-dashboard-{id}", resid)
        force = not self.has_sesskey

        page = self.fetch(
            self._dashboard_page_url,
            resid=resid,
            force=force,
        )
        self.set_sesskey(page)
        return page

    def course(self, course_id):
        """ create a Course object for access to the specified course id

        course_id: course id number
        """
        return Course(course_id, self)

    def url(self, path):
        """ create a URL for a resource within this Moodle installation """
        if path.startswith('http'):
            # assume it's a full URL already and don't prefix it
            return path

        # base_url already ends with / so simply concatenate
        return self.base_url + path

    def fetch_from_form(self, form_path, resource_path,
                        payload_filter, resid=None, force=False, files=None,
                        form_name='mform1'):
        """ return a requests.Response object for a form submission

        The form is prefetched to get extra magic input keys out of the
        provided form data before submitting it back to the Moodle instance.

        form_path: str
            absolute HTTP path of the form on the server
        resource_path: str
            absolute HTTP path of the target of the form
        payload_filter: callable
            function to filter the dict of form data from the initial form
            prior to the submission
        resid: str, optional
            resource id for on-disk caching (default, None, disables
            the cache)
        force: bool, optional
            force re-download of the resource rather than loading from cache
        files: list
            dict of file objects to be uploaded as part of the form
            submission
        form_name: str, optional
            the form 'name' (or 'id') tag to find the correct form within the
            HTML
        """
        cache = self.cache_factory(resid, force)
        try:
            return cache.load()

        except CacheMissError:

            form_url = self.url(form_path)
            resource_url = self.url(resource_path)

            logger.debug("Fetching resource form: %s", form_url)
            response_form = self.session.get(form_url)

            # find all of the fields in the form to send back
            soup = bs4.BeautifulSoup(response_form.text, "html.parser")
            if form_name is not None:
                form = soup.find(id=form_name)
            else:
                form = soup.find("form")

            payload = {}

            inputs = form.find_all('input')
            for i in inputs:
                n = i.get('name')
                v = i.get('value')
                if v is not None and v != '':
                    payload[n] = v

            textareas = form.find_all('textarea')
            for t in textareas:
                n = t.get('name')
                v = t.contents
                payload[n] = v[0] if len(v) else ""

            payload = payload_filter(payload)

            response_resource = self.session.post(
                resource_url, data=payload, files=files)

            cache.save(response_resource)
            return response_resource

    def fetch(self, resource_path, resid=None, force=False):
        """ return a requests.Response object for the requested URL

        resource_path: str
            the URL path on the current host or the absolute url to be fetch
        resid: str, optional
            resource id for caching to disk (`None` disables caching)
        force: bool, optional
            if `True`, forces redownload of the resource, bypassing the cache.
        """
        cache = self.cache_factory(resid, force)
        try:
            return cache.load()

        except CacheMissError:
            resource_url = self.url(resource_path)
            logger.debug("Fetching resource url: %s", resource_url)

            response_resource = self.session.get(resource_url)
            cache.save(response_resource)
            return response_resource

    def cache_factory(self, resid, force):
        return Cacher(resid, self.payload,
                      self.cache, self.cache_max_age,
                      force)
