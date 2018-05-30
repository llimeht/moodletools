""" Code for the command line tools for the moodletools suite

"""

# Copyright (c) 2017-2018 Stuart Prescott

import logging
import os.path

import moodletools
import moodletools.config
import moodletools.course

logger = logging.getLogger(__name__)


def resource_id(args, config):
    if args.id:
        return args.id

    return config.get('resource', {}).get('id', None)


class AbstractCommand:
    def __init__(self, parser):
        parser = self.add_parser(parser)
        parser.set_defaults(subcommand=self.handler)

    def add_parser(self, subparsers):
        raise NotImplementedError

    def handler(self, args, config):
        raise NotImplementedError


class Gradebook(AbstractCommand):

    def add_parser(self, subparsers):
        """ Subcommand: gradebook """
        parser = subparsers.add_parser(
            'gradebook',
            description='The gradebook command provides tools for interacting '
                        'with the course gradebook, including downloading the '
                        'gradebook as a spreadsheet.',
            help="tools for interacting with the gradebook"
        )

        # Mutually exclusive options for gradebook
        group = parser.add_mutually_exclusive_group(required=True)

        group.add_argument(
            '--fetch', metavar="FILENAME", type=str,
            help='save the gradebook in FILENAME',
        )

        return parser

    def handler(self, args, config):
        """ Dispatcher for 'gradebook' commands

        :param args: argparse.Namespace object of command-line options
        :param config: moodletools.config.MtConfig collection of configuration
            options
        """
        logging.debug("Gradebook tools")
        print(args)
        _, c = moodletools.config.auto_start(config)

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


class CoursePage(AbstractCommand):

    def add_parser(self, subparsers):
        """ Subcommand: course-page """
        parser = subparsers.add_parser(
            'course-page',
            description='The course-page command provides tools for '
                        'customising the main course page of a course, '
                        'including changing the visibility of items '
                        'on the page.',
            help="tools for interacting with the course page"
        )

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

        return parser

    def handler(self, args, config):
        """ Dispatcher for 'course-page' commands

        :param args: argparse.Namespace object of command-line options
        :param config: moodletools.config.MtConfig collection of configuration
            options
        """
        logging.debug("Course page tools")
        print(args)
        _, c = moodletools.config.auto_start(config)

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


class Assignment(AbstractCommand):

    def add_parser(self, subparsers):
        """ Subcommand: assignment """
        parser = subparsers.add_parser(
            'assignment',
            description='The assignment command provides tools for '
                        'interacting with Assignment resources, '
                        'including downloading status and mark '
                        'information.',
            help="tools for interacting with assignment resources"
        )

        parser.add_argument(
            '--id', metavar="ID",
            help='download the resource with the specified Id',
            required=True,
        )

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
        return parser

    def handler(self, args, config):
        """ Dispatcher for 'assignment' commands

        :param args: argparse.Namespace object of command-line options
        :param config: moodletools.config.MtConfig collection of configuration
            options
        """
        logging.debug("Assignment tools")
        print(args)
        _, c = moodletools.config.auto_start(config)

        rid = resource_id(args, config)
        assgt = c.assignment(rid)

        # actions are mutually exclusive
        if args.status:
            logging.debug("Assignment status")
            df = assgt.get_submission_status(config.cache_force)
            filename = args.status
            logging.debug("Writing to file '%s'", filename)
            df.to_excel(filename)
        elif args.grades:
            logging.debug("Assignment grades")
            df = assgt.get_grades(config.cache_force)
            filename = args.grades
            logging.debug("Writing to file '%s'", filename)
            df.to_excel(filename)


class Database(AbstractCommand):

    def add_parser(self, subparsers):
        """ Subcommand: database """
        parser = subparsers.add_parser(
            'database',
            description='The database command provides tools for '
                        'interacting with Database resources.',
            help="tools for interacting with Database resources"
        )

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
        return parser

    def handler(self, args, config):
        """ Dispatcher for 'database' commands

        :param args: argparse.Namespace object of command-line options
        :param config: moodletools.config.MtConfig collection of configuration
            options
        """
        logging.debug("Database tools")
        print(args)
        _, c = moodletools.config.auto_start(config)

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


class Label(AbstractCommand):

    def add_parser(self, subparsers):
        """ Subcommand: label """
        parser = subparsers.add_parser(
            'label',
            description='The label command provides tools for interacting '
                        'with Label resources, including creating new '
                        'labels.',
            help="tools for interacting with label resources"
        )

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

        return parser

    def handler(self, args, config):
        """ Dispatcher for 'label' commands

        :param args: argparse.Namespace object of command-line options
        :param config: moodletools.config.MtConfig collection of configuration
            options
        """
        logging.debug("Page tools")
        print(args)
        _, c = moodletools.config.auto_start(config)

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


class Page(AbstractCommand):

    def add_parser(self, subparsers):
        """ Subcommand: page """
        parser = subparsers.add_parser(
            'page',
            description='The page command provides tools for interacting '
                        'with Page resources, including creating new page '
                        'resources.',
            help="tools for interacting with page resources"
        )

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

        return parser

    def handler(self, args, config):
        """ Dispatcher for 'page' commands

        :param args: argparse.Namespace object of command-line options
        :param config: moodletools.config.MtConfig collection of configuration
            options
        """
        logging.debug("Page tools")
        print(args)
        _, c = moodletools.config.auto_start(config)

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


class Resource(AbstractCommand):

    def add_parser(self, subparsers):
        """ Subcommand: resource """
        parser = subparsers.add_parser(
            'resource',
            description='The resource command provides tools for interacting '
                        'with Resource (file) resources.',
            help="tools for interacting with Resource (file) resources"
        )

        # Mutually exclusive options for page
        group = parser.add_mutually_exclusive_group(required=True)

        group.add_argument(
            '--fetch', metavar='FILENAME',
            help='download the file resource and save to the specified '
                 'filename',
        )

        parser.add_argument(
            '--id', metavar="ID",
            help='download the resource with the specified Id',
        )

        return parser

    def handler(self, args, config):
        """ Dispatcher for 'resource' commands

        :param args: argparse.Namespace object of command-line options
        :param config: moodletools.config.MtConfig collection of configuration
            options
        """
        logging.debug("Resource (file) tools")
        print(args)
        _, c = moodletools.config.auto_start(config)

        rid = resource_id(args, config)

        # actions are mutually exclusive
        if args.fetch:
            logging.debug("Fetch the resource")

            filename = args.fetch

            resource = c.resource(rid)
            resource.get(save=True, filename=filename)
            # FIXME: skip cache?
