#!/usr/bin/python3

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import moodletools

config = {
    'description': 'Moodle utilities',
    'author': 'Stuart Prescott',
    'url': 'http://www.complexfluids.net/',
    'download_url': 'http://www.complexfluids.net/',
    'author_email': 's.prescott@unsw.edu.au',
    'version': moodletools.__version__,
    'install_requires': [],
    'packages': ['moodletools'],
    'name': 'moodletools',
}

setup(**config)
