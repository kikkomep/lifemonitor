# Copyright (c) 2020-2024 CRS4
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import datetime
import logging
import time

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from lifemonitor.api.models.testsuites.testbuild import TestBuild
from lifemonitor.api.models.testsuites.testinstance import TestInstance
from lifemonitor.cache import Timeout
from lifemonitor.tasks.scheduler import TASK_EXPIRATION_TIME, schedule
from lifemonitor.utils import notify_workflow_version_updates

# set module level logger
logger = logging.getLogger(__name__)


logger.info("Importing task definitions")


@schedule(trigger=IntervalTrigger(seconds=Timeout.WORKFLOW * 3 / 4),
          queue_name='builds', options={'max_retries': 3, 'max_age': TASK_EXPIRATION_TIME})
def check_workflows():
    """
    """
    from flask import current_app

    from lifemonitor.api.controllers import workflows_rocrate_download
    from lifemonitor.api.models import Workflow
    from lifemonitor.auth.services import login_user, logout_user
    from lifemonitor.cache import cache

    logger.info("Starting 'check_workflows' task....")
    with cache.transaction(name=f"check_workflows@{datetime.datetime.now()}", force_update=True):
        for w in Workflow.all():
            try:
                for v in w.versions.values():
                    u = v.submitter
                    with current_app.test_request_context():
                        try:
                            if u is not None:
                                login_user(u)
                            logger.info(f"Updating RO-Crate of the workflow version {v}...")
                            workflows_rocrate_download(w.uuid, v.version)
                            logger.info(f"Updating RO-Crate of the workflow version {v}... DONE")
                        except Exception as e:
                            logger.error(f"Error when updating the RO-Crate of the workflow version {v}: {str(e)}")
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.exception(e)
                        finally:
                            try:
                                logout_user()
                            except Exception as e:
                                logger.debug(e)
            except Exception as e:
                logger.error("Error when executing task 'check_workflows' against the workflow %s: %s", str(w), str(e))
                if logger.isEnabledFor(logging.DEBUG):
                    logger.exception(e)
    logger.info("Starting 'check_workflows' task.... DONE!")


@schedule(trigger=IntervalTrigger(seconds=Timeout.BUILD * 3 / 4),
          queue_name='builds', options={'max_retries': 3, 'max_age': TASK_EXPIRATION_TIME})
def check_last_build():
    from lifemonitor.api.models import Workflow, TestingService
    from lifemonitor.cache import cache

    all_start = time.time()
    logger.info("Starting 'check_last_build' task...")

    logger.info("Updating test instances managed by the Github Service...")
    gh_service = next((s for s in TestingService.all() if s.type.lower() == 'github'), None)
    if gh_service:
        start_time = time.time()
        logger.info("Starting update of all test instances...")
        updated_instances = set()
        try:
            updated_instances = gh_service.batch_update_workflows(
                TestInstance.find_by_testing_service(gh_service))
            logger.warning(f"Updated {len(updated_instances)} test instances managed by the Github Service.")
        finally:
            elapsed_time = time.time() - start_time
            logger.info(f"Update of all test instances completed in {elapsed_time:.2f} seconds.")

    logger.info("Checking last builds for all non Github test instances...")
    start_time = time.time()
    try:
        with cache.transaction(name=f"check_last_builds@{datetime.datetime.now()}", force_update=True):
            for w in Workflow.all():
                try:
                    logger.debug(f"Starting builds refresh of workflow {w.id} ({w.name})")
                    for workflow_version in w.versions.values():
                        if workflow_version and len(workflow_version.github_versions) > 0:
                            logger.warning(f"Version {workflow_version} of the workflow {w} is "
                                           "skipped because updated via github app")
                            continue
                        for s in workflow_version.test_suites:
                            logger.debug("Updating workflow: %r", w)
                            for i in s.test_instances:
                                if i.testing_service == gh_service:
                                    logger.debug("Skipping test instance %s (managed by Github Service)", i)
                                    continue
                                logger.debug("Updating test instance %s", i)
                                builds = i.get_test_builds(limit=10)
                                logger.debug("Updating latest builds: %r", builds)
                                for b in builds:
                                    logger.debug("Updating build: %r", i.get_test_build(b.id))
                                i.save(commit=False, flush=False)
                                workflow_version.save()
                                notify_workflow_version_updates([workflow_version], type='sync')
                                last_build = i.last_test_build
                                logger.debug("Latest build: %r", last_build)

                    # save workflow version and notify updates
                    workflow_version.save()
                    notify_workflow_version_updates([workflow_version], type='sync')
                except Exception as e:
                    logger.error("Error when executing task 'check_last_build': %s", str(e))
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.exception(e)
    finally:
        elapsed_time = time.time() - start_time
        logger.info(f"Update of all non Github test instances completed in {elapsed_time:.2f} seconds.")

    all_elapsed_time = time.time() - all_start
    logger.info(f"Task 'check_last_build' completed in {all_elapsed_time:.2f} seconds.")
    logger.info("Github GraphQL Rate limit status after check_last_build: %s",
                gh_service._gh_graphql_service.get_rate_limit() if gh_service else "N/A")
    logger.info("Github REST Rate limit status after check_last_build: %s",
                gh_service._gh_rest_service.get_rate_limit() if gh_service else "N/A")
    logger.info("Task 'check_last_build' completed!")


@schedule(trigger=CronTrigger(minute=0, hour=2),
          queue_name='builds', options={'max_retries': 3, 'max_age': TASK_EXPIRATION_TIME})
def periodic_builds():
    from lifemonitor.api.models import Workflow

    logger.info("Running 'periodic builds' task...")
    for w in Workflow.all():

        for workflow_version in w.versions.values():
            for s in workflow_version.test_suites:
                for i in s.test_instances:
                    try:
                        last_build: TestBuild = i.last_test_build
                        if datetime.datetime.fromtimestamp(last_build.timestamp) \
                                + datetime.timedelta(minutes=1) < datetime.datetime.now():
                            logger.info("Triggering build of test suite %s on test instance %s for workflow version %s", s, i, workflow_version)
                            i.start_test_build()
                            time.sleep(10)
                        else:
                            logger.warning("Skipping %s (last build: %s)",
                                           i, datetime.datetime.fromtimestamp(last_build.timestamp))
                    except Exception as e:
                        logger.error("Error when starting periodic build on test instance %s: %s", i, str(e))
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.exception(e)
    logger.info("Running 'periodic builds': DONE!")
