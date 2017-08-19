import os
import os.path
import pandas
import time


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
