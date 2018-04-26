""" Representations of resources within a course on Moodle

"""

# Copyright (c) 2015-2018 Stuart Prescott

import logging
import json
import re

import bs4
import numpy
import pandas
import pandas.io.parsers


logger = logging.getLogger(__name__)


class AbstractResource:
    """ Base class for File, Page, Forum etc resources within a course

    Subclasses of this class would be instantiated by factory methods
    within the Course class, for example:

    >>> course = mymoodle.course(12345)
    >>> assgt1 = course.assignment(2468)
    """
    _mod_name = None

    _add_get_form_url = (
        "course/modedit.php?add={type}&"
        "type=&course={id}&section={section}&return=0&sr=0"
    )
    _add_set_form_url = "course/modedit.php"

    _settings_get_form_url = "course/modedit.php?update={id}&return=0&sr=0"
    _settings_set_form_url = "course/modedit.php"

    def __init__(self, resource_id, course):
        """ Create an object to work with activities in Moodle

        resource_id: str or int
            id of the resource
        """
        self.id = resource_id
        self.course = course

    def hide(self):
        """ hide this resource from the course page """
        self.course.quick_action(self.id, 'hide')

    def unhide(self):
        """ unhide (aka show) this resource from the course page """
        self.course.quick_action(self.id, 'show')

    def _create(self, section, data):

        def _clean(payload):
            payload.update(data)

            # Cleanse keys from the form that cause trouble
            badkeys = ['cancel', 'submitbutton2']
            for k in badkeys:
                payload.pop(k, None)

            return payload

        response = self.course.moodle.fetch_from_form(
            self._add_get_form_url.format(
                type=self._mod_name,
                section=section,
                id=self.course.id
            ),
            self._add_set_form_url,
            _clean,
        )
        bsresp = bs4.BeautifulSoup(response.text, 'lxml')
        links = bsresp.find_all("a", attrs={'href': re.compile('forceview')})
        if links:
            href = links[0]['href']
            new_id = re.search(r'id=(\d+)', href).group(1)
        elif self._mod_name in ['label']:
            last = self.course.list_all(types=[self._mod_name])[-1]
            new_id = last.id
        else:
            logger.warning("Could not determine id for new resource")
            new_id = -2

        self.id = int(new_id)
        return self.id

    def set_release_date(self, release_date):
        """ set the release date for the resource

        :param release_date: datetime object or timestamp as integer.
            When the resource should be released
        """
        if not isinstance(release_date, int):
            timestamp = int(release_date.timestamp())
        else:
            timestamp = release_date

        # restrictions are a JSON object; this is the default one to use:
        restriction = {
            'c': [
                {
                    'd': '>=',
                    't': timestamp,
                    'type': 'date'
                }
            ],
            'op': '&',
            'showc': [False]
        }

        verbose = False

        # payload from form is run through cleaning function to substitute
        # in the values that are wanted
        def _clean(payload):
            if verbose:
                print("Incoming")
                for k in sorted(payload.keys()):
                    print(k, payload[k])
            if 'availabilityconditionsjson' not in payload or \
                    not payload['availabilityconditionsjson']:
                restr = restriction
                logger.debug("No existing restriction")
            else:
                restr = json.loads(payload['availabilityconditionsjson'])
                print("Loaded", restr)
                logger.debug("Loaded existing restriction: %s",
                             payload['availabilityconditionsjson'])

                date_restrs = [r for r in restr['c'] if r['type'] == 'date']
                if len(date_restrs) > 1:
                    logger.error("Can't handle multiple date restrictions")
                    return

                # Look for an existing date restriction and update it
                for term in restr['c']:
                    if term['type'] == 'date':
                        term['t'] = timestamp
                        break
                else:
                    # Finally adding one in if it's not there
                    restr['c'].append(restriction['c'][0])
                    restr['showc'].append(False)

            logger.debug("Final restriction: %s", json.dumps(restr))
            payload['availabilityconditionsjson'] = json.dumps(restr)

            # Cleanse keys from the form that cause trouble
            badkeys = ['cancel', 'submitbutton']
            for k in badkeys:
                payload.pop(k, None)

            if verbose:
                print("Outgoing")
                for k in sorted(payload.keys()):
                    print(k, payload[k])

            return payload

        response = self.course.moodle.fetch_from_form(
            self._settings_get_form_url.format(id=self.id),
            self._settings_set_form_url,
            _clean,
        )
        logger.debug("Sent data, status code: %s", response.status_code)


class Assignment(AbstractResource):
    """ Class representing a single Assignment activity within a course """
    _form_url = "mod/assign/view.php?id=%s&action=grading" \
                "&thide=plugin1&tifirst&tilast"
    _status_url = "mod/assign/view.php"
    _next_page = 'Next'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.status = None
        self._html_status_cache = "assignment-{id}-{page}"
        self._status_cache = "assignment-{id}-{page}"

    def _get_status_dataframes(self):
        """ fetch a page of assignment status information and clean it """
        def _clean(payload):
            payload['perpage'] = "50"    # FIXME THIS IS ICKY
            payload['filter'] = ""
            payload['workflowfilter'] = ""
            return payload

        def _resid():
            if self._html_status_cache:
                return self._html_status_cache.format_map({
                    'id': self.id,
                    'page': pagenum,
                })

        pagenum = 0

        response = self.course.moodle.fetch_from_form(
            self._form_url % self.id,
            self._status_url,
            _clean,
            _resid()
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
                nextlink = paging[0].find('a', href=True, text=self._next_page)
                if nextlink:
                    nexturl = nextlink['href']

            yield self._parse_html_status(table)

            if nexturl is None:
                raise StopIteration

            pagenum += 1
            response = self.course.moodle.fetch(
                nexturl,
                _resid()
            )

    @staticmethod
    def _parse_html_status(table):
        """ read an html table of assignment data and extract information """
        dfs = pandas.read_html(str(table))
        df = dfs[0]

        cols = list(df.columns)

        mapping = {
            '.*First name.*Surname.*': 'Name',
            'Username.*': 'Username',
            'Status.*': 'Status',
            'Grade.*': 'Grade',
        }

        for oldname, newname in mapping.items():
            for i, colname in enumerate(cols):
                cols[i] = re.sub(oldname, newname, colname)

        df.columns = cols
        df = df.set_index('Username')

        return df

    def _fetch_status_data(self):
        if self.status is None:
            df = pandas.concat(self._get_status_dataframes())
            self.status = df
        return self.status

    def get_submission_status(self):
        """ obtain information about the status of an assignment activity """
        df = self._fetch_status_data()
        df = df[['Name', 'Status']].copy()

        df.loc[df['Status'].isnull(), 'Status'] = self.course.status_missing
        df['Status'].replace(
            [r"^No submission.*", r"^Submitted.*"],
            [self.course.status_missing, self.course.status_submitted],
            inplace=True, regex=True
        )

        return df

    def get_grades(self):
        """ obtain information about grades in an assignment activity

        Note that the grade in the assignment might be different to
        the grade in the gradebook due to the marking workflow (grades not
        yet released) or due to moderation by a Team Evaluation plugin.
        """
        df = self._fetch_status_data()
        df = df[['Name', 'Grade', 'Final grade']].copy()

        gradere = re.compile(r'Grade(\d+(.\d+)?).*')

        # raw grade column is "GradeXX / YY"
        df['Grade'] = pandas.to_numeric(
            df.Grade.str.replace(gradere, lambda m: m.group(1)))

        return df


class Label(AbstractResource):
    """ Class representing a single Page resource within a course """
    _mod_name = 'label'

    def create(self, section, text):
        """ Create a few label with the course """
        payload = {}
        payload['introeditor[text]'] = text
        return self._create(section, payload)


class Page(AbstractResource):
    """ Class representing a single Page resource within a course """
    _mod_name = 'page'

    def create(self, section, title, content):
        """ Create a new page within the course """
        payload = {}
        payload['name'] = title
        payload['page[text]'] = content
        return self._create(section, payload)


class Workshep(AbstractResource):
    """ class representing a Workshep (aka Workshop UNSW) activity

    Note: Workshep is not a misspelling; that's what it is called inside the
    Moodle code to distinguish it from the pre-existing "Workshop" activity.
    """
    _submitted_log_entry = r"A submission has been uploaded"
    _assessed_log_entry = r"Submission assessed"
    _url_log_entry = r"The user with id '(?P<userid>\d+)' .+ " \
        r"'(?P<subid>\d+)' .+ '(?P<cmid>\d+)'"
    _submission_url = "{base}mod/workshep/submission.php?" \
        "cmid={cmid}&id={subid}"

    def get_status(self, filename_submissions, filename_assessments):
        """ obtain status data on a Workshop (UNSW) aka workshep activity """
        # FIXME: replace horrendous log parsing with a proper data export
        rawlogfilename = filename_submissions + ".xlsx"
        self.course.get_logs(self.id, rawlogfilename)

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
                    self._submitted_log_entry)]
            submitted_users = submitted['User full name'].unique()

            urls = submitted['Description'].str.extract(
                self._url_log_entry, expand=True)

            # There has to be a better way of applying a format in pandas
            def make_urls(row):
                """ make the URL to the submission based on known data """
                mapping = {
                    'base': self.course.moodle.base_url,
                    'cmid': row['cmid'],
                    'subid': row['subid'],
                    }
                url = self._submission_url.format(**mapping)
                return url

            urls['URL'] = urls.apply(make_urls, axis=1, raw=False)
            urls['Name'] = submitted['User full name']
            urls = urls[['Name', 'URL']]
            # resubmissions into the workshep will make duplicate entries;
            # logs are in reverse chronological order so only keep the first
            urls.drop_duplicates(subset='Name', keep='first', inplace=True)
            urls.set_index('Name', inplace=True)

            assessed = rawdf[
                rawdf['Event name'] == self._assessed_log_entry]
            assessed = assessed.rename(columns={
                'User full name': 'Assessor',
                'Affected user': 'Name',
            })
            assessed.set_index('Name', inplace=True)
            assessed_users = assessed.index.unique()

            users = set(numpy.concatenate((submitted_users, assessed_users)))

            df_submissions = pandas.DataFrame(columns=('Status', ),
                                              index=users)
            df_submissions['Status'] = self.course.status_missing
            df_submissions.loc[submitted_users, 'Status'] = \
                self.course.status_submitted
            df_submissions = df_submissions.join(urls)

            df_assessments = pandas.DataFrame(assessed['Assessor'],
                                              columns=('Assessor',))
            df_assessments['Marked'] = self.course.status_marked

        if filename_submissions:
            df_submissions.to_pickle(filename_submissions)
        if filename_assessments:
            df_assessments.to_pickle(filename_assessments)

        return df_submissions, df_assessments


class Forum(AbstractResource):
    """ Class to represent a Forum within a course

    No distinction is made (at this stage!) between the different types of
    forum that are available in Moodle.
    """
    _view_url = "mod/forum/view.php?id=%s"
    _form_url = 'mod/forum/post.php?forum=%s'
    _post_url = 'mod/forum/post.php'

    def get_threads(self):
        """ obtain the threads in the current forum """
        page = self.course.moodle.fetch(
            self._view_url % self.id,
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

    def post(self, subject, text, group=-1):
        """ post a message to a forum

        The message can be targeted to a specific group within a "Separate
        Groups" forum if desired.

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

        return self.course.moodle.fetch_from_form(
            self._form_url % self.id,
            self._post_url,
            _clean,
            None,
            form_name='mformforum'
        )


class Resource(AbstractResource):
    """ Class representing a File (aka Resource) within a course """

    _download_url = "mod/resource/view.php?id=%s"

    def _get_file_helper(self):
        """ try various ways of extracting a resource

        The resource may be a direct link, a referring link or embedded
        within frames.
        """
        page = self.course.moodle.fetch(
            self._download_url % self.id,
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

            page = self.course.moodle.fetch(
                link,
                None
            )
            return page, page.content

        # Perhaps it's an embedded object
        obj = bs.find('object', id='resourceobject')
        if obj:
            link = obj['data']

            page = self.course.moodle.fetch(
                link,
                None
            )
            return page, page.content

        raise ValueError("No idea how to get that resource")

    def get(self, save=False, filename=None):
        """ fetch a file from the resource

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
        page, content = self._get_file_helper()

        # Record the server specified filename
        if not filename:
            filename = re.findall("filename=(.+)",
                                  page.headers['content-disposition'])[0]
            if filename[0] == filename[-1] == '"':
                filename = filename[1:-1]
            if save:
                logger.info("Server specified filename in use: %s", filename)

        if save and filename:
            with open(filename, 'wb') as fh:
                fh.write(content)

        return content, filename

    _upload_url = "course/modedit.php?update=%s"

    def put(self, filename):
        """ put an updated copy of a file into the specified resource """
        def _clean(payload):
            payload.pop("nosubmit_checkbox_controller1", None)
            return payload

        # load up the files to be sent
        files = {
            'name': open(filename, 'rb'),
            'futz': self.id
        }

        files[self.id] = self.id
        # FIXME
        raise NotImplementedError()
