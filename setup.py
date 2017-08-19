#!/usr/bin/python3

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

config = {
    'description': 'Moodle utilities',
    'author': 'Stuart Prescott',
    'url': 'http://www.complexfluids.net/',
    'download_url': 'http://www.complexfluids.net/',
    'author_email': 's.prescott@unsw.edu.au',
    'version': '0.1',
    'install_requires': [],
    'packages': ['moodletools'],
    'name': 'moodletools',
}

setup(**config)
