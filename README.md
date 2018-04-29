# Python modules for automating Moodle tasks

This module offers a rather ad hoc collection of tools for automating various
tasks within the Moodle LMS. If you're not an instructor or educational
developer who spends a lot of time working in Moodle then there is probably
little of interest for you here.

If your installation of Moodle uses a simple username/password authentication
form then this module can help with that. Otherwise, you can create your
own authentication object that performs the login and creates the necessary
`requests.Session` object. For testing purposes, a factory method that creates
a login session on the demo.moodle.net server is provided.

See the `examples` directory for tools that are able to:

  * list all activities in a course, optionally filtering by type
  * hide or unhide all activities in a course, optionally filtering by type
  * download the file that is in a resource activity

## Availability

Usage of these tools is governed by the terms of service of the web services
you may connect to and institutional policies.

The code itself is available under the MIT licence.

## Installation

The code is written for Python 3.

The following Python modules are required (Debian/Ubuntu packages):

 * bs4 (python3-bs4)
 * numpy (python3-numpy)
 * pandas (python3-pandas)
 * requests (python3-requests)
 * xlrd (python3-xlrd)
