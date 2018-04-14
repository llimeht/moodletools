"""
Generic authentication methods for connecting to Moodle

Most sites will need to write their own customised `authenticate` method
which can then be used against with the login method to create a logged
in session.
"""

import requests

import moodletools.moodle


class Generic:
    """ Generic authentication to a Moodle installation

    Will require customisation either at run time or by subclassing.
    """
    def __init__(self):
        self.login_url = None
        self.url = None

    def authenticate(self, username, password):
        """ create an authenticated session against a simple login form """

        # initialise the session that will pick up the login cookie
        session = requests.Session()

        payload = {
            'submit': 'submit',
            'username': username,
            'password': password
        }

        session.post(self.login_url, data=payload)
        return session

    def connect(self, username, password):
        """ create the login session and the Moodle object """
        session = self.authenticate(username, password)
        return moodletools.moodle.Moodle(self.url, session)


def login_factory(auther, **kwargs):
    """ create a simple login function to connect to a moodle instance """
    def _login(*args):
        return auther.connect(*args, **kwargs)

    return _login


login = login_factory(Generic())
