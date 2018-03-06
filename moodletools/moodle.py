import collections
import logging
import re

import bs4

import numpy
import pandas
import pandas.io.parsers

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

    def sesskey(self):
        """ return the sesskey for the session """
        if not self._sesskey:
            self.get_dashboard_page()
        return self._sesskey

    def _set_sesskey(self, page):
        """ opportunistically harvest the sesskey from the page """
        if self._sesskey:
            return
        bs = bs4.BeautifulSoup(page.text, 'lxml')
        self._sesskey = bs.find('input', {'name': 'sesskey'})['value']

    _dashboard_page_url = "my/"

    def get_dashboard_page(self, filename=None):
        """ return a requests.Response object for the site dashboard page

        filename: str, optional
            save the dashboard html to the filename
        """
        page = self.fetch(
            self._dashboard_page_url,
            filename
        )
        self._set_sesskey(page)
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
                        payload_filter, filename=None, files=None,
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
        filename: str, optional
            filename into which the returned data should be saved
        files: list
            TODO: list of file objects to be uploaded as part of the form
            submission
        form_name: str, optional
            the form 'name' (or 'id') tag to find the correct form within the
            HTML
        """
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
        inputs = form.find_all('input')

        payload = {}
        for i in inputs:
            n = i.get('name')
            v = i.get('value')
            if v is not None and v != '':
                payload[n] = v

        payload = payload_filter(payload)

        response_resource = self.session.post(
            resource_url, data=payload, files=files)

        if filename is not None:
            with open(filename, 'wb') as fh:
                fh.write(response_resource.content)

        return response_resource

    def fetch(self, resource_path, filename=None):
        """ return a requests.Response object for the requested URL

        resource_path: str
            the URL path on the current host or the absolute url to be fetch
        filename: str, optional
            the filename to use saving the download to disk
            (`None` disables caching)
        """
        resource_url = self.url(resource_path)
        logger.debug("Fetching resource url: %s", resource_url)

        response_resource = self.session.get(resource_url)

        if filename is not None:
            logger.debug("Caching resource to %s", filename)
            with open(filename, 'wb') as fh:
                fh.write(response_resource.content)

        return response_resource


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
        self.course_id = course_id
        self.moodle = moodle

        self.status_missing = "MISSING"
        self.status_submitted = "submitted"
        self.status_marked = "marked"

    _gradebook_form_url = "grade/export/xls/index.php?id=%s"
    _gradebook_export_url = 'grade/export/xls/export.php'

    def get_gradebook(self, filename=None):
        """ return a requests object with the course gradebook

        filename: (optional) filename to save the gradebook spreadsheet

        returns: requests.Response object

        Example:
        gbdata = m.get_gradebook(12345)
        gb = pandas.read_excel(gbdata.content)
        """
        def _clean(payload):
            payload.pop("nosubmit_checkbox_controller1", None)
            return payload

        return self.moodle.fetch_from_form(
            self._gradebook_form_url % self.course_id,
            self._gradebook_export_url,
            _clean,
            filename
        )

    _course_page_url = "course/view.php?id=%s"

    def get_course_page(self, filename=None):
        """ return a requests.Response object for the course page """
        page = self.moodle.fetch(
            self._course_page_url % self.course_id,
            filename
        )
        self.moodle._set_sesskey(page)
        return page

    _assigment_form_url = "mod/assign/view.php?id=%s&action=grading" \
                          "&thide=plugin1&tifirst&tilast"
    _assigment_status_url = "mod/assign/view.php"
    _assignment_next = 'Next'

    def assignment_status_dataframes(self, activity, filename=None):
        """ fetch assignment status information and clean it """
        def _clean(payload):
            payload['perpage'] = "50"    # FIXME THIS IS ICKY
            payload['filter'] = ""
            return payload

        def _filename():
            if filename:
                return filename + str(pagenum) + ".html"

        pagenum = 0

        response = self.moodle.fetch_from_form(
            self._assigment_form_url % activity,
            self._assigment_status_url,
            _clean,
            _filename()
        )

        # process the table on each page in turn
        while True:
            soup = bs4.BeautifulSoup(response.text, "html.parser")
            region = soup.find(id='region-main')
            table = region.find('table')

            # (prev) 1 2 3 (next) with prev/next only shown if there are any
            paging = soup.find_all("div", class_='paging')

            nexturl = None
            if paging:
                nextlink = paging[0].find('a', href=True,
                                          text=self._assignment_next)
                if nextlink:
                    nexturl = nextlink['href']

            yield self._parse_html_status(table)

            if nexturl is None:
                raise StopIteration

            pagenum += 1
            response = self.moodle.fetch(
                nexturl,
                _filename()
            )

    @staticmethod
    def _parse_html_status(table):
        """ read an html table of assignment data and extract information """
        dfs = pandas.read_html(str(table))
        df = dfs[0]

        cols = list(df.columns)

        mapping = {
            'First name.*Surname.*': 'Name',
            'Username.*': 'Username',
            'Status.*': 'Status',
        }

        for oldname, newname in mapping.items():
            for i, colname in enumerate(cols):
                cols[i] = re.sub(oldname, newname, colname)

        df.columns = cols
        df = df[['Name', 'Username', 'Status']]
        df = df.set_index('Username')

        return df

    def get_assignment_status(self, activity, filename=None):
        """ obtain information about the status of an assignment activity """
        df = pandas.concat(
            self.assignment_status_dataframes(activity, filename))

        df.loc[df['Status'].isnull(), 'Status'] = self.status_missing
        df['Status'].replace(
            [r"^No submission.*", r"^Submitted.*"],
            [self.status_missing, self.status_submitted],
            inplace=True, regex=True
        )

        if filename is not None:
            df.to_pickle(filename)
        return df

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

    def fetch_logs(self, activity_id, filename=None):
        """ fetch the logs for a specified activity

        activity_id: int or str
            id number of the activity
        filename: str, optional
            filename to which the download should be saved
        """
        def _clean(payload):
            payload['download'] = "excel"
            return payload

        return self.moodle.fetch_from_form(
            self._log_form_url % (self.course_id, activity_id),
            self._log_export_url % (self.course_id, activity_id),
            _clean,
            filename,
            form_name=None
        )

    _workshop_submitted_log_entry = r"A submission has been uploaded"
    _workshop_assessed_log_entry = r"Submission assessed"
    _workshop_url_log_entry = r"The user with id '(?P<userid>\d+)' .+ " \
                              r"'(?P<subid>\d+)' .+ '(?P<cmid>\d+)'"
    _workshop_submission_url = "{base}mod/workshep/submission.php?" \
                               "cmid={cmid}&id={subid}"

    def get_workshop_status(self, activity,
                            filename_submissions, filename_assessments):
        """ obtain status data on a Workshop (UNSW) aka workshep activity """
        # FIXME: replace horrendous log parsing with a proper data export
        rawlogfilename = filename_submissions + ".xlsx"
        self.fetch_logs(activity, rawlogfilename)

        # moodle can return a weird HTML error rather than an empty
        # spreadsheet so detect that and bail out early
        bad_data = False
        with open(rawlogfilename, 'rb') as fh:
            dat = fh.read()
            if b"The actual number of sheets is 0." in dat or \
                    b"<title>Error</title>" in dat:
                bad_data = True

        if not bad_data:
            rawdf = pandas.read_excel(rawlogfilename)
            if not len(rawdf):
                bad_data = True

        if bad_data:
            df_submissions = pandas.DataFrame(columns=('Status', 'URL'))
            df_assessments = pandas.DataFrame(columns=('Marked', 'Assessor'))

        else:
            submitted = rawdf[
                rawdf['Event name'].str.startswith(
                    self._workshop_submitted_log_entry)]
            submitted_users = submitted['User full name'].unique()

            urls = submitted['Description'].str.extract(
                self._workshop_url_log_entry, expand=True)

            # There has to be a better way of applying a format in pandas
            def make_urls(row):
                """ make the URL to the submission based on known data """
                mapping = {
                    'base': self.moodle.base_url,
                    'cmid': row['cmid'],
                    'subid': row['subid'],
                    }
                url = self._workshop_submission_url.format(**mapping)
                return url

            urls['URL'] = urls.apply(make_urls, axis=1, raw=False)
            urls['Name'] = submitted['User full name']
            urls = urls[['Name', 'URL']]
            # resubmissions into the workshep will make duplicate entries;
            # logs are in reverse chronological order so only keep the first
            urls.drop_duplicates(subset='Name', keep='first', inplace=True)
            urls.set_index('Name', inplace=True)

            assessed = rawdf[
                rawdf['Event name'] == self._workshop_assessed_log_entry]
            assessed = assessed.rename(columns={
                'User full name': 'Assessor',
                'Affected user': 'Name',
            })
            assessed.set_index('Name', inplace=True)
            assessed_users = assessed.index.unique()

            users = set(numpy.concatenate((submitted_users, assessed_users)))

            df_submissions = pandas.DataFrame(columns=('Status', ),
                                              index=users)
            df_submissions['Status'] = self.status_missing
            df_submissions.loc[submitted_users, 'Status'] = \
                self.status_submitted
            df_submissions = df_submissions.join(urls)

            df_assessments = pandas.DataFrame(assessed['Assessor'],
                                              columns=('Assessor',))
            df_assessments['Marked'] = self.status_marked

        if filename_submissions:
            df_submissions.to_pickle(filename_submissions)
        if filename_assessments:
            df_assessments.to_pickle(filename_assessments)

        return df_submissions, df_assessments

    _forum_view_url = "mod/forum/view.php?id=%s"

    def get_forum_threads(self, forum_id):
        """ obtain the threads in the current forum """
        page = self.moodle.fetch(
            self._forum_view_url % forum_id,
            None
        )
        bs = bs4.BeautifulSoup(page.text, 'lxml')

        table = bs.find('table', class_='forumheaderlist')
        posts = table.find_all('tr', class_='discussion')

        data = []
        for p in posts:
            topiccell = p.find('td', class_='topic starter')
            topic = topiccell.find('a').text
            url = topiccell.find('a')['href']
            groupcell = p.find('td', class_="picture group")
            if groupcell.text:
                groupname = groupcell.find('a').text
            else:
                groupname = None

            data.append((topic, url, groupname))

        return data

    _forum_form_url = 'mod/forum/post.php?forum=%s'
    _forum_post_url = 'mod/forum/post.php'

    def post_to_forum(self, forum_id, subject, text, group=-1):
        """ post a message to a forum

        The message can be targeted to a specific group within a "Separate
        Groups" forum if desired.

        forum_id: str or int
            id of the forum resource
        subject: str
            subject field for the forum post
        text: str
            plain text to be posted
            TODO: figure out how to do multiparagraph or HTML formatted text
        group: int, optional
            the group id in the forum to post to; if -1, post to all groups
            TODO: figure out how to easily obtain the group ids
        """
        def _clean(payload):
            for field in ['cancel', 'discussionsubscribe', 'mailnow',
                          'mform_isexpanded_id_general', 'pinned',
                          'posttomygroups']:
                payload.pop(field, None)

            # and also add the post to the payload
            payload.update({
                'subject': subject,
                'message[text]': text,
                'groupinfo': group,
                'submitbutton': 'Post to forum',
            })
            return payload

        return self.moodle.fetch_from_form(
            self._forum_form_url % forum_id,
            self._forum_post_url,
            _clean,
            None,
            form_name='mformforum'
        )

    _completion_summary_url = 'report/progress/index.php?course=%d&format=csv'

    def get_activity_completion(self):
        """ fetch the activity completion report as CSV """
        page = self.moodle.fetch(
            self._completion_summary_url % self.course_id,
            None
        )
        return page.text

    _resource_quick_url = "course/mod.php?sesskey={sesskey}&sr=0&{action}={id}"

    def _do_quick(self, resource_id, action):
        """ run a quick link for a resource """
        self.moodle.fetch(
            self._resource_quick_url.format(**{
                'sesskey': self.moodle.sesskey(),
                'id': resource_id,
                'action': action,
            }),
            None)

    def _do_all_quick(self, types, action):
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

        #if types:
            #acts = [a for a in acts if a['type'] in types]

        for a in acts:
            self._do_quick(a.id, action)

        return acts

    def hide_all(self, types=None):
        """ hide all resources of a certain type on the course page

        types: list of str, optional
            list of Moodle resource type names that are to be hidden

        returns: list of CourseResource
            list of resource that were hidden
        """
        return self._do_all_quick(types, 'hide')

    def unhide_all(self, types=None):
        """ unhide all resources of a certain type on the course page

        types: list of str, optional
            list of Moodle resource type names that are to be unhidden

        returns: list of CourseResource
            list of resource that were unhidden
        """
        return self._do_all_quick(types, 'show')

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
        page = self.get_course_page()
        bs = bs4.BeautifulSoup(page.text, 'lxml')

        # find all the A anchors in the content part of the course page
        # (excluding menus, side bars, theme etc)
        div = bs.find('div', class_='course-content')
        urls = div.find_all('a')

        # links to resources are /mod/{resource name}/...id=XYZ
        activity_link_re = re.compile(r'mod/([^/]+).*id=(\d+)')

        activities = []
        for u in urls:
            url = u['href']
            m = activity_link_re.search(url)
            act_type = m.group(1)
            if types is None or act_type in types:
                act_id = m.group(2)
                activities.append(
                    CourseResource(
                        url,
                        act_id,
                        act_type,
                        u.text,
                    )
                )

        return activities

    _file_download_url = "mod/resource/view.php?id=%s"

    def _get_file_helper(self, resource_id):
        """ try various ways of extracting a resource

        The resource may be a direct link, a referring link or embedded
        within frames.

        resource_id: str or int
        """
        page = self.moodle.fetch(
            self._file_download_url % resource_id,
            None
        )
        # The resource URL should magically 303 across to the actual file
        if page.history and page.history[0].status_code == 303:
            return page, page.content

        # If it doesn't 303 to the actual file then there might be a download
        # link to try
        bs = bs4.BeautifulSoup(page.text, 'lxml')

        div = bs.find('div', class_='resourceworkaround')

        if div:   # it's a link to the resource
            link = div.find('a').href

            page = self.moodle.fetch(
                link,
                None
            )
            return page, page.content

        # Perhaps it's an embedded object
        obj = bs.find('object', id='resourceobject')
        if obj:
            link = obj['data']

            page = self.moodle.fetch(
                link,
                None
            )
            return page, page.content

        raise ValueError("No idea how to get that resource")

    def get_file(self, resource_id, save=False, filename=None):
        """ fetch a file by its resource id

        resource_id: str or int
            identifier of the file resource to download
        save: bool
            save the file once downloaded
        filename: str
            filename into which the downloaded resource should be saved. If
            the filename not specified but `save` is `True` then the server
            specified filename will be used in the current directory. Be
            very careful not to overwrite resources with this!

        returns:
            file contents (binary), filename
        """
        page, content = self._get_file_helper(resource_id)

        # Generate the filename if it is require but has not been specified.
        if save and not filename:
            filename = re.findall("filename=(.+)",
                                  page.headers['content-disposition'])[0]
            if filename[0] == filename[-1] == '"':
                filename = filename[1:-1]
            logger.info("Server specified filename in use: %s", filename)

        if save and filename:
            with open(filename, 'wb') as fh:
                fh.write(content)

        return content, filename


CourseResource = collections.namedtuple(
    'CourseResource',
    [
        'url',
        'id',
        'type',
        'name',
    ]
)
