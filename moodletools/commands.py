""" Code for the command line tools for the moodletools suite

"""

# Copyright (c) 2017-2018 Stuart Prescott

import logging
import os.path

import moodletools
import moodletools.config
import moodletools.course

logger = logging.getLogger(__name__)


def _auto_start(config):
    """ Connect to Moodle and create the course using command-line/config"""
    logging.info("Logging into Moodle")
    call = config.login_callable()
    moodle = call()
    moodle.cache = config.cache_location
    course = moodle.course(config.course)
    return moodle, course


def resource_id(args, config):
    if args.id:
        return args.id

    return config.get('resource', {}).get('id', None)


# # Gradebook

def add_gradebook_parser(subparsers):
    """ Subcommand: gradebook """
    parser = subparsers.add_parser(
        'gradebook',
        description='The gradebook command provides tools for interacting '
                    'with the course gradebook, including downloading the '
                    'gradebook as a spreadsheet.',
        help="tools for interacting with the gradebook"
    )
    parser.set_defaults(subcommand=gradebook_handler)

    # Mutually exclusive options for gradebook
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        '--fetch', metavar="FILENAME", type=str,
        help='save the gradebook in FILENAME',
    )


def gradebook_handler(args, config):
    """ Dispatcher for 'gradebook' commands

    :param args: argparse.Namespace object of command-line options
    :param config: moodletools.config.MtConfig collection of configuration
        options
    """
    logging.debug("Gradebook tools")
    print(args)
    _, c = _auto_start(config)

    # actions are mutually exclusive
    if args.fetch:
        logging.debug("Fetching gradebook")
        g = c.gradebook()
        df = g.as_dataframe()
        filename = args.fetch
        logging.debug("Writing to file '%s'", filename)
        df.to_excel(filename)
    else:
        # shouldn't get here -- need argparse to require an option
        raise ValueError("Unknown action for subcommand")


# # Course page

def add_course_page_parser(subparsers):
    """ Subcommand: course-page """
    parser = subparsers.add_parser(
        'course-page',
        description='The course-page command provides tools for customising '
                    'the main course page of a course, including changing the'
                    'visibility of items on the page.',
        help="tools for interacting with the course page"
    )
    parser.set_defaults(subcommand=course_page_handler)

    # Mutually exclusive options for course-page
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        '--hide', metavar="ID", type=int, nargs='+',
        help='hide an activity',
    )
    group.add_argument(
        '--hide-all', action='store_true',
        help='hide all activities',
    )
    group.add_argument(
        '--show', metavar="ID", type=int, nargs='+',
        help='hide an activity',
    )
    group.add_argument(
        '--show-all', action='store_true',
        help='hide all activities',
    )
    group.add_argument(
        '--list-all', metavar='FILENAME.xlsx', nargs="?",
        const="-",      # option selected but no filename given
        default=False,  # option is not selected
        help='list all activities, optionally saving as a spreadsheet',
    )


def course_page_handler(args, config):
    """ Dispatcher for 'course-page' commands

    :param args: argparse.Namespace object of command-line options
    :param config: moodletools.config.MtConfig collection of configuration
        options
    """
    logging.debug("Course page tools")
    print(args)
    _, c = _auto_start(config)

    # actions are mutually exclusive
    if args.list_all:
        logging.debug("Listing all resources")
        activities = c.list_all()
        # determine the output destination
        filename = args.list_all

        if filename == '-':    # no filename specified, stdout
            logging.debug("Dumping to stdout")
            for activity in activities:
                print(activity)
        else:
            logging.debug("Saving to %s", filename)
            df = moodletools.course.to_dataframe(activities)
            df.to_excel(filename)


# # Assignment

def add_assignment_parser(subparsers):
    """ Subcommand: assignment """
    parser = subparsers.add_parser(
        'assignment',
        description='The assignment command provides tools for interacting '
                    'with Assignment resources, including downloading '
                    'status and mark information.',
        help="tools for interacting with assignment resources"
    )
    parser.set_defaults(subcommand=assignment_handler)

    # Mutually exclusive options for page
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        '--status', metavar="FILENAME.xlsx", type=str,
        help='save assignment status information into FILENAME',
    )

    group.add_argument(
        '--grades', metavar="FILENAME.xlsx", type=str,
        help='save assignment grade information into FILENAME (includes '
             'unreleased grades)',
    )


def assignment_handler(args, config):
    """ Dispatcher for 'assignment' commands

    :param args: argparse.Namespace object of command-line options
    :param config: moodletools.config.MtConfig collection of configuration
        options
    """
    logging.debug("Assignment tools")
    print(args)
    _, c = _auto_start(config)

    rid = resource_id(args, config)
    filename = args.status
    assgt = c.assignment(rid)

    # actions are mutually exclusive
    if args.status:
        logging.debug("Assignment status")
        df = assgt.get_submission_status(config.force)
        logging.debug("Writing to file '%s'", filename)
        df.to_excel(filename)
    elif args.status:
        logging.debug("Assignment grades")
        df = assgt.get_submission_grades(config.force)
        logging.debug("Writing to file '%s'", filename)
        df.to_excel(filename)


# # Database

def add_database_parser(subparsers):
    """ Subcommand: database """
    parser = subparsers.add_parser(
        'database',
        description='The database command provides tools for interacting with '
                    'Database resources.',
        help="tools for interacting with Database resources"
    )
    parser.set_defaults(subcommand=database_handler)

    # Mutually exclusive options for page
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        '--fetch', metavar='FILENAME',
        help='download the database and save to the specified filename',
    )

    parser.add_argument(
        '--id', metavar="ID",
        help='download the resource with the specified Id',
    )


def database_handler(args, config):
    """ Dispatcher for 'database' commands

    :param args: argparse.Namespace object of command-line options
    :param config: moodletools.config.MtConfig collection of configuration
        options
    """
    logging.debug("Database tools")
    print(args)
    _, c = _auto_start(config)

    rid = resource_id(args, config)

    # actions are mutually exclusive
    if args.fetch:
        logging.debug("Fetch the database")

        filename = args.fetch
        _, fmt = os.path.splitext(filename)
        if fmt:
            fmt = fmt[1:]

        database = c.database(rid)
        database.export(save=True, filename=filename, fmt=fmt,
                        force=config.cache_force)


# # Label

def add_label_parser(subparsers):
    """ Subcommand: label """
    parser = subparsers.add_parser(
        'label',
        description='The label command provides tools for interacting with '
                    'Label resources, including creating new labels.',
        help="tools for interacting with label resources"
    )
    parser.set_defaults(subcommand=label_handler)

    # Mutually exclusive options for page
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        '--create', metavar='FILENAME.html', nargs='?', type=str,
        const="-",      # option selected but no filename given
        default=False,  # option is not selected
        help='create a new Label reading either from stdin or from a file',
    )

    parser.add_argument(
        '--section', metavar='SECTION', type=int,
        help='section number in which the page should be created'
    )


def label_handler(args, config):
    """ Dispatcher for 'label' commands

    :param args: argparse.Namespace object of command-line options
    :param config: moodletools.config.MtConfig collection of configuration
        options
    """
    logging.debug("Page tools")
    print(args)
    _, c = _auto_start(config)

    # actions are mutually exclusive
    if args.create:
        logging.debug("Create new label")
        section = args.section

        filename = args.create

        if filename == '-':    # no filename specified, stdin
            logging.debug("Reading from stdin")
            content = input()
        else:
            logging.debug("Reading from %s", filename)
            with open(filename) as fh:
                content = fh.read()
        label = c.label(0)
        label.create(section, content)


# # Page

def add_page_parser(subparsers):
    """ Subcommand: page """
    parser = subparsers.add_parser(
        'page',
        description='The page command provides tools for interacting with '
                    'Page resources, including creating new page resources.',
        help="tools for interacting with page resources"
    )
    parser.set_defaults(subcommand=page_handler)

    # Mutually exclusive options for page
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        '--create', metavar='FILENAME.html', nargs='?', type=str,
        const="-",      # option selected but no filename given
        default=False,  # option is not selected
        help='create a new Page reading either from stdin or from a file',
    )

    parser.add_argument(
        '--title', metavar='TITLE',
        help='title of the new page'
    )

    parser.add_argument(
        '--section', metavar='SECTION', type=int,
        help='section number in which the page should be created'
    )


def page_handler(args, config):
    """ Dispatcher for 'page' commands

    :param args: argparse.Namespace object of command-line options
    :param config: moodletools.config.MtConfig collection of configuration
        options
    """
    logging.debug("Page tools")
    print(args)
    _, c = _auto_start(config)

    # actions are mutually exclusive
    if args.create:
        logging.debug("Create new page")
        title = args.title
        section = args.section

        filename = args.create

        if filename == '-':    # no filename specified, stdin
            logging.debug("Reading from stdin")
            content = input()
        else:
            logging.debug("Reading from %s", filename)
            with open(filename) as fh:
                content = fh.read()
        page = c.page(0)
        page.create(section, title, content)


# # Resource (file)

def add_resource_parser(subparsers):
    """ Subcommand: resource """
    parser = subparsers.add_parser(
        'resource',
        description='The resource command provides tools for interacting with '
                    'Resource (file) resources.',
        help="tools for interacting with Resource (file) resources"
    )
    parser.set_defaults(subcommand=resource_handler)

    # Mutually exclusive options for page
    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        '--fetch', metavar='FILENAME',
        help='download the file resource and save to the specified filename',
    )

    parser.add_argument(
        '--id', metavar="ID",
        help='download the resource with the specified Id',
    )


def resource_handler(args, config):
    """ Dispatcher for 'resource' commands

    :param args: argparse.Namespace object of command-line options
    :param config: moodletools.config.MtConfig collection of configuration
        options
    """
    logging.debug("Resource (file) tools")
    print(args)
    _, c = _auto_start(config)

    rid = resource_id(args, config)

    # actions are mutually exclusive
    if args.fetch:
        logging.debug("Fetch the resource")

        filename = args.fetch

        resource = c.resource(rid)
        resource.get(save=True, filename=filename)
        # FIXME: skip cache?
