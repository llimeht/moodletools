"""
Login methods for connecting to demo.moodle.net

Example:

from moodletools.auth.demo_moodle_net import login_as_teacher
mymoodle = login_as_teacher()
"""
from moodletools.auth.generic import Generic, login_factory


class DemoMoodleNetAuth(Generic):
    """ Authentication and login class for demo.moodle.net """
    def __init__(self):
        super().__init__()

        self.url = "https://demo.moodle.net/"
        self.login_url = self.url + "login/index.php"

    def connect(self, *args, mode='teacher'):
        """ login to the sandbox with the defined mode """
        roles = {
            'admin': 'sandbox',
            'manager': 'sandbox',
            'teacher': 'sandbox',
            'student': 'sandbox',
        }
        if mode not in roles:
            raise ValueError("Unknown login mode '%s'" % mode)

        return super().connect(mode, roles[mode])


login_as_admin = login_factory(DemoMoodleNetAuth(), mode='admin')

login_as_manager = login_factory(DemoMoodleNetAuth(), mode='manager')

login_as_teacher = login_factory(DemoMoodleNetAuth(), mode='teacher')

login_as_student = login_factory(DemoMoodleNetAuth(), mode='student')
