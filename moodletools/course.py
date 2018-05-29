""" Representations of courses within a Moodle instance

"""

# Copyright (c) 2015-2018 Stuart Prescott

import collections
import io
import logging
import os
import os.path
import re
import time

import bs4
import numpy
import pandas

from moodletools import resources
from moodletools.utils import resid_factory


logger = logging.getLogger(__name__)


class Course:
    """ A Course within a Moodle installation

    This class represents an interface to the Course page and the objects
    within it, capable of downloading material, querying activity and for
    some resources even setting configuration

    Example:

    >>> mycourse = mymoodle.Course(12345)
    >>> mycourse.list_all()
    >>> mycourse.hide_all(types=['resource', 'forum'])

    """
    def __init__(self, course_id, moodle):
        """

        course: course id number

        """
        self.id = course_id
        self.moodle = moodle

        self.status_missing = "MISSING"
        self.status_submitted = "submitted"
        self.status_marked = "marked"

    def activity(self, activity_id):
        """ create an Activity object within this course

        activity_id: str or int
            the id of the generic activity
        """
        return resources.AbstractResource(activity_id, self)

    def assignment(self, assignment_id):
        """ create an Assignment object within this course

        assignment_id: str or int
            the id of the assignment activity
        """
        return resources.Assignment(assignment_id, self)

    def database(self, database_id):
        """ create an Database object within this course

        database_id: str or int
            the id of the database activity
        """
        return resources.Database(database_id, self)

    def page(self, page_id):
        """ create a Page object within this course

        page_id: str or int
            the id of the page activity
        """
        return resources.Page(page_id, self)

    def label(self, label_id):
        """ create a Label object within this course

        label_id: str or int
            the id of the label activity
        """
        return resources.Label(label_id, self)

    def workshep(self, workshep_id):
        """ create a Workshep (aka Workshop UNSW) object within this course

        workshep_id: str or int
            the id of the workshep activity
        """
        return resources.Workshep(workshep_id, self)

    def forum(self, forum_id):
        """ create a Forum object within this course

        forum_id: str or int
            the id of the forum activity
        """
        return resources.Forum(forum_id, self)

    def resource(self, resource_id):
        """ create a File Resource object within this course

        resource_id: str or int
            the id of the file resource
        """
        return resources.Resource(resource_id, self)

    def gradebook(self):
        """ create the Greadebook object within this course """
        return Gradebook(self)

    _course_page_url = "course/view.php?id=%s"

    def get_course_page(self, resid='auto'):
        """ return a requests.Response object for the course page

        :param resid: the resource id for caching the download. Note that
            since the login session key is extracted from this page,
            pulling from the cache is automatically disabled if the
            session key is not yet set.

        :returns: a requests response object with the data
        """
        resid = resid_factory(self, "course-page-{id}", resid)
        force = not self.moodle.has_sesskey

        page = self.moodle.fetch(
            self._course_page_url % self.id,
            resid=resid,
            force=force,
        )
        self.moodle.set_sesskey(page)
        return page

    _log_form_url = (
        "report/log/index.php?"
        "chooselog=1&"
        "showusers=0&"
        "showcourses=0&"
        "id=%s&"         # course id
        "user=&"
        "date=&"
        "modid=%s&"      # activity id
        "modaction=c&"
        "edulevel=-1&"
        "logreader=logstore_standard")

    _log_export_url = (
        "report/log/index.php?"
        "id=%s&"         # course id
        "modid=%s&"      # activity id
        "modaction=c&"
        "chooselog=1&"
        "logreader=logstore_standard")

    def get_logs(self, activity_id, resid='auto'):
        """ fetch the logs for a specified activity

        activity_id: int or str
            id number of the activity
        resid: str, optional
            resource id for on-disk cache
        """
        def _clean(payload):
            payload['download'] = "excel"
            return payload

        return self.moodle.fetch_from_form(
            self._log_form_url % (self.id, activity_id),
            self._log_export_url % (self.id, activity_id),
            _clean,
            resid_factory(self, "course-logs-{id}", resid),
            form_name=None
        )

    _completion_summary_url = 'report/progress/index.php?course=%d&format=csv'

    def get_activity_completion(self):
        """ fetch the activity completion report as CSV """
        page = self.moodle.fetch(
            self._completion_summary_url % self.id,
            None
        )
        return page.text

    _resource_quick_url = "course/mod.php?sesskey={sesskey}&sr=0&{action}={id}"

    def quick_action(self, resource_id, action):
        """ run a quick link for a resource """
        self.moodle.fetch(
            self._resource_quick_url.format(**{
                'sesskey': self.moodle.sesskey(),
                'id': resource_id,
                'action': action,
            }),
            None)

    def quick_action_all(self, types, action):
        """ run an action for all resources of a certain type

        Iterate through the course page, running a specified 'quick link'
        (such as "hide" or "show") for every resource on the course page
        that is in the given list of resource types.

        types: list, set, tuple
            list of str of the types to be changed. Known types include
            'resource', 'page', 'forum' etc; check the URL for a resource
            for its name.
        action: str
            the action name as specified in the quick link

        returns: list of CourseResource
            the entries that were processed
        """
        acts = self.list_all(types)

        for a in acts:
            self.quick_action(a.id, action)

        return acts

    def hide_all(self, types=None):
        """ hide all resources of a certain type on the course page

        types: list of str, optional
            list of Moodle resource type names that are to be hidden

        returns: list of CourseResource
            list of resource that were hidden
        """
        return self.quick_action_all(types, 'hide')

    def unhide_all(self, types=None):
        """ unhide all resources of a certain type on the course page

        types: list of str, optional
            list of Moodle resource type names that are to be unhidden

        returns: list of CourseResource
            list of resource that were unhidden
        """
        return self.quick_action_all(types, 'show')

    def list_all(self, types=None):
        """ list all resources that are shown on the course page

        The list of resources can be filtered down to those matching the
        specified resource types. The internal names for the types can be
        discovered by looking at the URLs to the resources and includes
        'resource' (a file), 'page', 'forum' etc.

        types: list of str, optional
            list of resources to include; if not specified or None, all
            resources are listed.

        returns: list of CourseResource
            each resource is placed in the list as a CourseResource object
        """

        # find all the A anchors in the content part of the course page
        # (excluding menus, side bars, theme etc); only links to resources
        # are wanted, which are of form /mod/{resource name}/...id=XYZ
        activity_link_re = re.compile(r'mod/([^/]+).*id=(\d+)')

        page = self.get_course_page()
        bs = bs4.BeautifulSoup(page.text, 'lxml')

        div = bs.find('div', class_='course-content')
        containers = div.find_all('li', class_='activity')
        activities = []

        for activity in containers:
            _, act_id = activity['id'].split('-')
            act_type = activity['class'][1]
            name = activity.find('span', class_="instancename")
            if name:
                text = name.text
            else:
                name = activity.find('div', class_="contentwithoutlink")
                if name:
                    text = name.text
                else:
                    text = activity.text
            url = activity.find('a', attrs={'href': activity_link_re})
            href = None
            if url:
                href = url['href']

            if types is None or act_type in types:
                activities.append(
                    CourseResource(
                        href,
                        int(act_id),
                        act_type,
                        text,
                    )
                )

        return activities

    def apply_release_dates(self, data, act=True):
        """

        :param data: list of dict with keys ['Id', 'Release ts']
        """
        for idx, row in enumerate(data):
            logger.info("Applying row %d %s", idx, str(row))

            if act:
                activity = self.activity(row['Id'])
                activity.set_release_date(row['Release ts'])


class Gradebook:

    _gradebook_form_url = "grade/export/xls/index.php?id=%s"
    _gradebook_export_url = 'grade/export/xls/export.php'

    def __init__(self, course):
        self.course = course
        self.resid = 'auto'
        self.dataframe = None
        self.summary_fields = [
            'First name',
            'Surname',
            'Email address',
        ]

    def fetch(self, force=False):
        """ return a requests object with the course gradebook

        force: bool, optional, default `False`
            forces redownload of the resource

        returns: requests.Response object

        Example:
        gb = mycourse.gradebook()
        gbdata = pandas.read_excel(gb.fetch().content)
        """
        def _clean(payload):
            payload.pop("nosubmit_checkbox_controller1", None)
            return payload

        return self.course.moodle.fetch_from_form(
            self._gradebook_form_url % self.course.id,
            self._gradebook_export_url,
            _clean,
            resid_factory(self.course, "course-gradebook-{id}", self.resid),
            force=force,
        )

    def as_dataframe(self, fillna=True, force=False):
        if self.dataframe is not None and not force:
            return self.dataframe

        resp = self.fetch()

        gb = pandas.read_excel(
            io.BytesIO(resp.content),
            engine='xlrd',
            na_values=['-'],
            keep_default_na=True,
        )
        gb.set_index('Username', inplace=True)

        # cache the dataframe for potential future use
        self.dataframe = gb

        if fillna:
            grade_columns = self.columns(real=True, percentage=True)
            gb[grade_columns] = gb[grade_columns].fillna(0)

        return gb

    def as_dataframe_summary(self, real=True, percentage=False, letter=False):
        gb = self.as_dataframe()

        cols = self.summary_fields.copy()
        cols.extend(self.columns(real, percentage, letter))
        return gb.loc[:, cols]

    def columns(self, real=True, percentage=False, letter=False):
        gb = self.as_dataframe(fillna=False, force=False)

        cols = []
        if real:
            cols.append('Real')
        if percentage:
            cols.append('Percentage')
        if letter:
            cols.append('Letter')

        colre = re.compile(r'\((%s)\)$' % '|'.join(cols))

        cols = [c for c in gb.columns if colre.search(c)]
        return cols


CourseResource = collections.namedtuple(
    'CourseResource',
    [
        'url',
        'id',
        'type',
        'name',
    ]
)


def to_dataframe(data):
    """ create a pandas DataFrame of a list of CourseResource objects

    :param data: list of CourseResource items to serialse into the
        DataFrame
    """
    r = data[0]
    df = pandas.DataFrame(data, columns=r._fields).set_index('id')
    return df


def load_activity_spreadsheet(filename, sheet=0):
    """ Load a spreadsheet of activity information in predefined format

    :param filename: str, filename of the spreadsheet to load (.xls or .xlsx
        format, see example sheet for spreadsheet structure)
    :param sheet: int or str, sheet number or name to use

    Currently, only availability restrictions are supported.

    """
    # FIXME how do we deal with user edited sheets better?
    # FIXME can we deal with release vs due dates nicely?
    control = pandas.read_excel(filename, sheet=sheet,
                                skiprows=23, dtype={'Id': str})

    # Make a new dataframe with just the configured rows
    mask = control['Date'].notnull() & control['Time'].notnull()
    c = control[mask].copy()

    # Combine the separate date and time columns
    c['Release'] = pandas.to_datetime(
        c['Date'].astype(str) + ' ' + c['Time'].astype(str),
        errors='coerce')

    c['Release ts'] = c['Release'].values.astype(numpy.int64) // 10 ** 9

    # Filter down to only the fields required
    data = c[['Id', 'Release', 'Type', 'Release ts', 'Description']]

    return data.to_dict(orient='records')


def apply_activity_spreadsheet(filename, course, act=True):
    """ Load a spreadsheet of activity configuration and apply it

    :param filename: str, filename of the spreadsheet, see
        :func:`load_activity_spreadsheet` for requirements
    :param course: Course, the course the config should be applied to
    :param act: bool, optional, default True, actually apply the configuration

    """
    data = load_activity_spreadsheet(filename)

    course.apply_release_dates(data, act)

# =========================================================================

# FIXME: these legacy classes will (probably) receive substantial refactoring


class CourseMixin:

    def __init__(self, moodle, config, *args, **kwargs):
        # print("course")
        self.moodle = moodle
        self.config = config
        self.course_name = config["name"]
        self.course_id = config["id"]

        self.cache = 'cache'
        self.cache_max_age = 3600   # seconds

        super().__init__(*args, **kwargs)

    def load(self):
        pass

    def _cache(self, filename):
        if not os.path.exists(self.cache):
            os.mkdir(self.cache)
        return os.path.join(self.cache, filename)

    def _cache_ok(self, resource):
        try:
            mtime = os.path.getmtime(self._cache(resource))
        except FileNotFoundError:
            return False
        return time.time() < mtime + self.cache_max_age


class GradebookMixin:

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.gradebook_filename = "%s-gradebook.pickle" % self.course_name
        self.gradebook_download_filename = "%s-gradebook.xlsx" % \
            self.course_name

    def get_gradebook(self):
        self.moodle.get_gradebook(
            self.course_id,
            self._cache(self.gradebook_download_filename))
        gb = pandas.read_excel(self._cache(self.gradebook_download_filename))

        self.gradebook = gb.set_index('Username')
        self.gradebook['Course'] = self.course_name
        self.gradebook.to_pickle(self._cache(self.gradebook_filename))
        return self.gradebook

    def load(self):
        if self._cache_ok(self.gradebook_filename):
            self.gradebook = pandas.read_pickle(
                self._cache(self.gradebook_filename))
            return True
        return False

    def apply_grades(self, table, raw_column, mark_status_column):
        marked = table.apply(
            lambda row: (self.moodle.status_marked
                         if (row[raw_column] != '-' and
                             row[raw_column] != '0.00 %')
                         else self.moodle.status_missing),
            axis=1)
        table[mark_status_column] = marked

    def hide_missing_missing(self, table, assessment, missing='-'):
        ''' don't nag about missing marks when the submission is missing '''
        if 'submission' in assessment and 'marking' in assessment and \
                pandas.notnull(assessment['submission']) and \
                pandas.notnull(assessment['marking']):
            mark = assessment['marking']
            sub = assessment['submission']
            table.loc[(table[mark] == self.moodle.status_missing) &
                      (table[sub] == self.moodle.status_missing),
                      mark] = missing
