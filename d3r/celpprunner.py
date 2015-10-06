#! /usr/bin/env python

import sys
import os
import argparse
import psutil
import logging
from datetime import date

import d3r
from d3r import util
from d3r.task import D3RParameters
from d3r.task import BlastNFilterTask
from d3r.task import PDBPrepTask
from d3r.task import CompInchiDownloadTask
from lockfile.pidlockfile import PIDLockFile

# create logger
logger = logging.getLogger('d3r.celpprunner')
LOG_FORMAT = "%(asctime)-15s %(levelname)s %(name)s %(message)s"


def _get_lock(theargs, stage):
    """Create lock file to prevent this process from running on same data.

       This uses ``PIDLockFile`` to create a pid lock file in celppdir
       directory named celprunner.<stage>.lockpid
       If pid exists it is assumed the lock is held otherwise lock
       is broken and recreated

       :param theargs: return value from argparse and should contain
                       theargs.celppdir should be set to path
       :param stage: set to stage that is being run
       :return: ``PIDLockFile`` upon success
       :raises: LockException: If there was a problem locking
       :raises: Exception: If valid pid lock file already exists
       """
    mylockfile = os.path.join(theargs.celppdir, "celpprunner." +
                              stage + ".lockpid")
    logger.debug("Looking for lock file: " + mylockfile)
    lock = PIDLockFile(mylockfile, timeout=10)

    if lock.i_am_locking():
        logger.debug("My process id" + str(lock.read_pid()) +
                     " had the lock so I am breaking")
        lock.break_lock()
        lock.acquire(timeout=10)
        return lock

    if lock.is_locked():
        logger.debug("Lock file exists checking pid")
        if psutil.pid_exists(lock.read_pid()):
            raise Exception("celpprunner with pid " +
                            str(lock.read_pid()) +
                            " is running")

    lock.break_lock()
    logger.info("Acquiring lock")
    lock.acquire(timeout=10)
    return lock


def _setup_logging(theargs):
    """Sets up the logging for application
       """
    theargs.logformat = LOG_FORMAT
    theargs.numericloglevel = logging.NOTSET
    if theargs.loglevel == 'DEBUG':
        theargs.numericloglevel = logging.DEBUG
    if theargs.loglevel == 'INFO':
        theargs.numericloglevel = logging.INFO
    if theargs.loglevel == 'WARNING':
        theargs.numericloglevel = logging.WARNING
    if theargs.loglevel == 'ERROR':
        theargs.numericloglevel = logging.ERROR
    if theargs.loglevel == 'CRITICAL':
        theargs.numericloglevel = logging.CRITICAL

    logger.setLevel(theargs.numericloglevel)
    logging.basicConfig(format=theargs.logformat)
    logging.getLogger('d3r.task').setLevel(theargs.numericloglevel)


def run_stages(theargs):
    """Runs all the stages set in theargs.stage parameter


       Examines theargs.stage and splits it by comma to get
       list of stages to run.  For each stage found a lock file
       is created and run_stage is invoked with theargs.latest_weekly set to
       the output of util.find_latest_weekly_dataset.  After run_stage the
       lockfile is released
       :param theargs: should contain theargs.celppdir and other parameters
                       set via commandline
    """
    try:
        if theargs.createweekdir:
            celp_week = util.get_celpp_week_of_year_from_date(date.today())
            logger.debug('Request to create new directory ' +
                         os.path.join(theargs.celppdir, str(celp_week[1]),
                                      'dataset.week.'+str(celp_week[0])))
            util.create_celpp_week_dir(celp_week, theargs.celppdir)
    except AttributeError:
        pass

    theargs.latest_weekly = util.find_latest_weekly_dataset(theargs.celppdir)

    if theargs.latest_weekly is None:
        logger.info("No weekly dataset found in path " +
                    theargs.celppdir)
        return 0

    for stage_name in theargs.stage.split(','):
        logger.info("Starting " + stage_name + " stage")
        try:
            lock = _get_lock(theargs, stage_name)

            task_list = get_task_list_for_stage(theargs, stage_name)

            # run the stage
            exit_code = run_tasks(task_list)
            if exit_code is not 0:
                logger.error('Non zero exit code from task ' + stage_name +
                             'exiting')
                return exit_code
        finally:
            # release lock
            logger.debug('Releasing lock')
            lock.release()

    return 0


def run_tasks(task_list):
    """Runs a specific stage

       Runs the tasks in task_list
       :param task_list: list of tasks to run
    """
    if task_list is None:
        logger.error('Task list is None')
        return 3

    if len(task_list) == 0:
        logger.error('Task list is empty')
        return 2

    for task in task_list:
        logger.info("Running task " + task.get_name())
        try:
            task.run()
        except Exception as e:
            logger.exception("Error caught exception")
            if task.get_error() is None:
                task.set_error('Caught Exception running task: ' + e.message)

        logger.debug("Task " + task.get_name() + " has finished running " +
                     " with status " + task.get_status())
        if task.get_error() is not None:
            logger.error('Error running task ' + task.get_name() +
                         ' ' + task.get_error())
            return 1

    return 0


def get_task_list_for_stage(theargs, stage_name):
    """Factory method that generates a list of tasks for given stage

       Using stage_name get the list of tasks that need to
       be run.
       :param theargs: parameters set via commandline along with
                       ``theargs.latest_weekly`` which should be set to
                       to base directory where stages will be run
       :param stage_name:  Name of stage to run
    """
    if stage_name is None:
        raise NotImplementedError('stage_name is None')

    task_list = []

    logger.debug('Getting task list for ' + stage_name)

    if stage_name == 'import':
        # TODO replace external stage.1.dataimport with task in celpprunner
        task_list.append(CompInchiDownloadTask(theargs.latest_weekly, theargs))

    if stage_name == 'blast':
        task_list.append(BlastNFilterTask(theargs.latest_weekly, theargs))

    if stage_name == 'pdbprep':
        task_list.append(PDBPrepTask(theargs.latest_weekly, theargs))

    if len(task_list) is 0:
        raise NotImplementedError(
            'uh oh no tasks for ' + stage_name + ' stage')

    return task_list


def _parse_arguments(desc, args):
    """Parses command line arguments using argparse.
    """
    parsed_arguments = D3RParameters()

    help_formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=desc,
                                     formatter_class=help_formatter)
    parser.add_argument("celppdir", help='Base celpp directory')
    parser.add_argument("--blastdir", help='Parent directory of ' +
                        ' blastdb.  There should exist a "current" ' +
                        ' symlink or directory that contains the db.' +
                        ' NOTE: Required parameter for blast stage')
    parser.add_argument("--email", dest="email",
                        help='Comma delimited list of email addresses')
    parser.add_argument("--createweekdir",
                        help='Create new celpp week directory before ' +
                             'running stages',
                        action="store_true")
    parser.add_argument("--stage", required=True, help='Comma delimited list' +
                        ' of stages to run.  Valid STAGES = ' +
                        '{import, blast, pdbprep} '
                        )
    parser.add_argument("--blastnfilter", default='blastnfilter.py',
                        help='Path to BlastnFilter script')
    parser.add_argument("--pdbprep", default='pdbprep.py',
                        help='Path to pdbprep script')
    parser.add_argument("--compinchi",
                        default='http://ligand-expo.rcsb.org/' +
                        'dictionaries/Components-inchi.ich',
                        help='URL to download Components-inchi.ich' +
                             ' file for' +
                             'task stage.1.compinchi')
    parser.add_argument("--log", dest="loglevel", choices=['DEBUG',
                        'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help="Set the logging level",
                        default='WARNING')
    parser.add_argument('--smtp', dest='smtp', help='Sets smtpserver to use',
                        default='localhost')
    parser.add_argument('--smtpport', dest='smtpport',
                        help='Sets smtp server port', default='25')
    parser.add_argument('--version', action='version',
                        version=('%(prog)s ' + d3r.__version__))
    return parser.parse_args(args, namespace=parsed_arguments)


def main():
    desc = """
              Runs the 5 stages (import, blast, pdbprep, dock, & score) of
              CELPP processing pipeline (http://www.drugdesigndata.org)

              CELPP processing pipeline relies on a set of directories
              with specific structure. The pipeline runs a set of stages
              Each stage has a numerical value and a name. The numerical
              value denotes order and the stage name identifies separate
              tasks to run in the stage.

              The filesystem structure of the stage is:

              stage.<stage number>.<task name>

              The stage(s) run are defined via the required --stage flag.

              To run multiple stages serially just pass a comma delimited
              list to the --stage flag. Example: --stage blast,pdbprep

              NOTE:  When running multiple stages serially the program will
                     exit as soon as a task in a stage fails and subsequent
                     stages will NOT be run.

              This program drops a pid lockfile
              (celpprunner.<stage>.lockpid) in celppdir to prevent duplicate
              invocation.

              When run, this program will examine the stage and see
              if work can be done.  If stage is complete or previous
              steps have not completed, the program will exit silently.
              If previous steps have failed or current stage already
              exists in an error or uncomplete state then program will
              report the error via email using addresses set in --email
              flag. Errors will also be reported via stderr/stdout.
              The program will also exit with nonzero exit code.

              This program utilizes simple token files to denote stage
              completion.  If within the stage directory there is a:

              'complete' file - then stage is done and no other
                                checking is done.

              'error' file - then stage failed.

              'start' file - then stage is running.

              Notification of stage start and end will be sent to
              addresses set via --email flag.

              Regardless of the stage specified, this program will
              examine the 'celppdir' (last argument passed on
              commandline) to find the latest directory with this path:
              <year>/dataset.week.#
              The program will find the latest <year> and within
              that year the dataset.week.# with highest #.  The output
              directories created will be put within this directory.

              If specified --createweekdir flag will instruct this
              program to create a new directory for the current
              celpp week/year before invoking running any stage
              processing.

              NOTE: CELPP weeks start on Friday and end on Thursday
                    and week # follows ISO8601 rules so week numbers
                    at the end and start of the year are a bit
                    wonky.

              Breakdown of behavior of program is defined by
              value passed with --stage flag:

              If --stage 'import'

              The first stage which downloads Components-inchi.ich into
              stage.1.compinchi.  The stage.1.dataimport is currently run
              by an external script, but really should be done by this tool
              at some point.

              If --stage 'blast'

              Verifies stage.1.dataimport exists and has 'complete'
              file.  Also the --blastdir path must exist and within a
              'current' symlink/directory must exist and within that a
              'complete' file must also reside. If both conditions
              are met then the 'blast' stage is run and output stored
              in stage.2.blastnfilter

              If --stage 'pdbprep'

              Verifies stage.2.blastnfilter exists and has 'complete'
              file.  If complete, this stage runs which invokes program
              set in --pdbprep flag to prepare pdb and inchi files storing
              output in stage.3.pdbprep

              If --stage 'dock'

              Verifies stage3.pdbprep exists and has a 'complete'
              file within it.  If complete, this program will run fred
              docking and store output in stage.4.fred.  As new
              algorithms are incorporated additional stage.4.<algo> will
              be created and run.

              If --stage 'score'

              Finds all stage.4.<algo> directories with 'complete' files
              in them and invokes appropriate scoring algorithm storing
              results in stage.5.<algo>.scoring.
              """

    theargs = _parse_arguments(desc, sys.argv[1:])
    theargs.program = sys.argv[0]
    theargs.version = d3r.__version__
    try:
        if os.path.basename(theargs.blastdir) is 'current':
            theargs.blastdir = os.path.dirname(theargs.blastdir)
    except AttributeError:
        pass

    _setup_logging(theargs)

    try:
        run_stages(theargs)
    except Exception:
        logger.exception("Error caught exception")
        sys.exit(2)


if __name__ == '__main__':
    main()
