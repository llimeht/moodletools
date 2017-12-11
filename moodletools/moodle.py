import re
import bs4
import numpy
import pandas
import pandas.io.parsers


class Moodle:
    def __init__(self, base_url, session):
        self.base_url = base_url
        self.session = session

        self.status_missing = "MISSING"
        self.status_submitted = "submitted"
        self.status_marked = "marked"

    def _get_resource_preparation(self, form_url, resource_url,
                                  payload_filter, filename,
                                  form_name='mform1'):
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

        response_resource = self.session.post(resource_url, data=payload)

        if filename is not None:
            with open(filename, 'wb') as fh:
                fh.write(response_resource.content)

        return response_resource

    def _get_resource(self, resource_url, filename):

        response_resource = self.session.get(resource_url)

        if filename is not None:
            with open(filename, 'wb') as fh:
                fh.write(response_resource.content)

        return response_resource

    _gradebook_form_url = "grade/export/xls/index.php?id=%s"
    _gradebook_export_url = 'grade/export/xls/export.php'

    def get_gradebook(self, course, filename=None):
        """ return a requests object with the course gradebook

        course: course id number

        filename: (optional) filename to save the gradebook spreadsheet

        returns: requests object

        Example:
        gbdata = m.get_gradebook(12345)
        gb = pandas.read_excel(gbdata.content)
        """
        def _clean(payload):
            payload.pop("nosubmit_checkbox_controller1", None)
            return payload

        return self._get_resource_preparation(
            self.base_url + self._gradebook_form_url % course,
            self.base_url + self._gradebook_export_url,
            _clean,
            filename
        )

    _course_page_url = "course/view.php?id=%s"

    def get_course_page(self, course, filename=None):
        return self._get_resource(
            self.base_url + self._course_page_url % course,
            filename
        )

    _assigment_form_url = "mod/assign/view.php?id=%s&action=grading" \
                          "&thide=plugin1&tifirst&tilast"
    _assigment_status_url = "mod/assign/view.php"
    _assignment_next = 'Next'

    def assignment_status_dataframes(self, activity, filename=None):

        def _clean(payload):
            payload['perpage'] = "50"    # FIXME THIS IS ICKY
            payload['filter'] = ""
            return payload

        def _filename():
            if filename:
                return filename + str(pagenum) + ".html"

        pagenum = 0

        response = self._get_resource_preparation(
            self.base_url + self._assigment_form_url % activity,
            self.base_url + self._assigment_status_url,
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
            response = self._get_resource(
                nexturl,
                _filename()
            )

    @staticmethod
    def _parse_html_status(table):
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

    def fetch_logs(self, course, activity, filename=None):
        def _clean(payload):
            payload['download'] = "excel"
            return payload

        return self._get_resource_preparation(
            self.base_url + self._log_form_url % (course, activity),
            self.base_url + self._log_export_url % (course, activity),
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

    def get_workshop_status(self, course, activity,
                            filename_submissions, filename_assessments):
        # FIXME: replace horrendous log parsing with a proper data export
        rawlogfilename = filename_submissions + ".xlsx"
        self.fetch_logs(course, activity, rawlogfilename)

        # moodle can return a weird HTML error rather than an empty
        # spreadsheet so detect that and bail out early
        bad_data = False
        with open(rawlogfilename, 'rb') as fh:
            dat = fh.read()
            if b"The actual number of sheets is 0." in dat or \
                    b"<title>Error</title>" in dat:
                bad_data = True

        if bad_data:
            df_submissions = pandas.DataFrame(columns=('Status', 'URL'))
            df_assessments = pandas.DataFrame(columns=('Marked', 'Assessor'))

        else:
            rawdf = pandas.read_excel(rawlogfilename)

            submitted = rawdf[
                rawdf['Event name'].str.startswith(
                    self._workshop_submitted_log_entry)]
            submitted_users = submitted['User full name'].unique()

            urls = submitted['Description'].str.extract(
                self._workshop_url_log_entry, expand=True)

            # There has to be a better way of applying a format in pandas
            def make_urls(row):
                mapping = {
                    'base': self.base_url,
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

    def get_forum_threads(self, forum):
        page = self._get_resource(
            self.base_url + self._forum_view_url % forum,
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

    def post_to_forum(self, forum, subject, text, group=-1):

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

        return self._get_resource_preparation(
            self.base_url + self._forum_form_url % forum,
            self.base_url + self._forum_post_url,
            _clean,
            None,
            form_name='mformforum'
        )
