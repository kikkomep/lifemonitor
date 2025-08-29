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

from __future__ import annotations

import logging
import time
from typing import Optional

import github
from github import GithubException
from github import \
    RateLimitExceededException as GithubRateLimitExceededException
from github.WorkflowRun import WorkflowRun

import lifemonitor.api.models as models
import lifemonitor.exceptions as lm_exceptions
from lifemonitor.api.models.services.github.graphql.service import \
    GithubGraphQLService
from lifemonitor.api.models.services.github.rest import GithubRestService
from lifemonitor.api.models.services.github.testinstance_cache import \
    TestInstanceCache
from lifemonitor.cache import Timeout

from ..service import TestingService
from .test_build import GithubTestBuild
from .utils import match_test_instance_params, parse_workflow_url

# set module level logger
logger = logging.getLogger(__name__)


class GithubTestingService(TestingService):

    _gh_obj = None
    _gh_graphql = None
    _test_instance_cache = None
    __mapper_args__ = {
        'polymorphic_identity': 'github_testing_service'
    }

    def __init__(self, url: str = None, token: models.TestingServiceToken = None) -> None:
        logger.debug("GithubTestingService constructor instantiating client")
        if not url:
            url = github.MainClass.DEFAULT_BASE_URL
        super().__init__(url, token)

    def __repr__(self):
        return "<GithubTestingService url=%s token=***>" % self.url

    def __str__(self):
        return "GithubTestingService(url=%s, token=***)" % self.url

    def initialize(self):
        try:
            logger.debug("Instantiating with: url %s; token: %r\n",
                         self.url, self.token is not None)
            # Init the REST service
            self._gh_obj = GithubRestService(
                url=self.url,
                token=self.token,
                # Uncomment to override the default retry policy
                # retry=self._configuration_['retry'],
                # Uncomment to override the default timeout and per_page
                # timeout=self._configuration_['timeout'],
                # Uncomment to override the default per_page
                # per_page=self._configuration_['per_page']
            )
            # Init the GraphQL service
            self._gh_graphql = GithubGraphQLService(
                token=self.token.value if self.token else None)

            logger.debug("Github client created.")
        except Exception as e:
            raise lm_exceptions.TestingServiceException(e)

    @property
    def base_url(self):
        return 'https://github.com'

    @property
    def _gh_rest_service(self) -> GithubRestService:
        logger.debug("Github client requested.")
        if not self._gh_obj:
            self.initialize()
        return self._gh_obj

    @property
    def _gh_graphql_service(self) -> GithubGraphQLService:
        logger.debug("Github GraphQL client requested.")
        if not self._gh_graphql:
            self.initialize()
        return self._gh_graphql

    # @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _get_workflow_info(self, resource):
        server, owner, repo, workflow_id = parse_workflow_url(resource)
        return server, f"{owner}/{repo}", workflow_id

    # @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _get_fine_grained_workflow_info(self, resource):
        return parse_workflow_url(resource)

    def check_connection(self):
        return self._gh_rest_service.check_connection()

    @property
    def test_instance_cache(self) -> TestInstanceCache:
        if self._test_instance_cache is None:
            self._test_instance_cache = TestInstanceCache()
        return self._test_instance_cache

    @staticmethod
    def _convert_github_exception_to_lm(github_exc: GithubException) -> lm_exceptions.LifeMonitorException:
        return lm_exceptions.LifeMonitorException(
            title=github_exc.__class__.__name__,
            status=github_exc.status,
            detail=str(github_exc),
            data=github_exc.data,
            headers=github_exc.headers)

    def get_last_test_build(self, test_instance: models.TestInstance) -> Optional[GithubTestBuild]:
        try:
            logger.debug("Getting latest build...")
            builds = self.get_test_builds(test_instance, limit=1)
            last_test_build = builds[0] if builds else None
            logger.debug("Latest build found: %s", last_test_build)
            return last_test_build
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    def get_last_passed_test_build(self, test_instance: models.TestInstance) -> Optional[GithubTestBuild]:
        try:
            logger.debug("Getting last passed build...")
            builds = self.get_test_builds(test_instance, limit=100)
            for build in builds:
                if build.status == models.BuildStatus.PASSED:
                    logger.debug("Last passed build found: %s", build)
                    return build
            logger.debug("No passed builds found for test instance %s", test_instance.uuid)
            return None
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    def get_last_failed_test_build(self, test_instance: models.TestInstance) -> Optional[GithubTestBuild]:
        try:
            logger.debug("Getting last failed build...")
            builds = self.get_test_builds(test_instance, limit=100)
            for build in builds:
                if build.status == models.BuildStatus.FAILED:
                    logger.debug("Last failed build found: %s", build)
                    return build
            logger.debug("No failed builds found for test instance %s", test_instance.uuid)
            return None
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    def refresh_timeout_expired(self, test_instance: models.TestInstance,
                                timeout: int = None) -> bool:

        # Check if the update interval is set
        if timeout is None:
            timeout = Timeout.BUILD

        logger.debug("Configured build expiration timeout is set to %d seconds", timeout)

        # Retrieve the last refresh timestamp from the test_instance cache
        # and check if it is recent (less than 10 minutes ago)
        last_update = self.test_instance_cache.get_update_timestamp(test_instance.uuid)
        if last_update:
            delta = (time.time() - last_update)
            logger.debug("Test instance %s last cache update was %.2f seconds ago",
                         test_instance.uuid, delta)
            logger.debug("Configured update interval is %d seconds", timeout)
            logger.debug("Elapsed time since last update is %.2f seconds", delta)
            if delta < timeout:
                logger.debug("Test instance %s cache is recent (%.2f seconds ago), skipping fetch",
                             test_instance.uuid, delta)
                return False

        return True

    def __update_test_builds_cache__(self, test_instance: models.TestInstance,
                                     update_interval: int = None) -> bool:
        """
        Fetch the test builds for a given test instance from GitHub
        only if the test instance builds_refreshed_at is None or older than 10 minutes.

        :param test_instance: The test instance to update.
        :param update_interval: The minimum interval (in seconds) between updates.
        :return: True if the test builds were updated, False otherwise.
        """
        # assert isinstance(test_instance, models.TestInstance), \
        #     "test_instance must be an instance of TestInstance"
        # assert test_instance.testing_service_id == self.uuid, \
        #     "test_instance must be associated with this testing service"

        # Check if the refresh timeout is expired
        if not self.refresh_timeout_expired(test_instance, update_interval):
            logger.debug("Refresh timeout has not expired for test instance %s, skipping fetch",
                         test_instance.uuid)
            return False

        logger.debug("Fetching workflow runs for test instance %s from GitHub", test_instance.uuid)
        try:

            workflow_runs = self._gh_rest_service.fetch_workflow_runs_by_test_instance(test_instance)
            logger.debug("Fetched %d workflow runs for test instance %s", len(workflow_runs), test_instance.uuid)
            # self.test_instance_cache.batch_update(test_instance.id, workflow_runs)
            self.test_instance_cache.batch_associate_and_insert_runs(
                test_instance.uuid,
                self.get_instance_external_link(test_instance),
                [{"run_id": _.id,
                  "ref": _.head_branch,
                  "metadata": _._rawData} for _ in workflow_runs],
                use_lock=True,
                max_retry=3
            )
            return True
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)
        except GithubException as e:
            raise self._convert_github_exception_to_lm(e)
        except Exception as e:
            raise lm_exceptions.TestingServiceException(e)

    def get_test_builds(self, test_instance: models.TestInstance, limit=100) -> list:
        """
        Get the test builds for a given test instance.
        :param test_instance: The test instance to get the builds for.
        :param limit: The maximum number of builds to return.
        :return: A list of GithubTestBuild objects.
        """

        # assert isinstance(test_instance, models.TestInstance), \
        #     "test_instance must be an instance of TestInstance"
        # assert test_instance.testing_service_id == self.uuid, \
        #     "test_instance must be associated with this testing service"

        # total time
        total_start_time = time.time()

        # Start timing for cache update
        start_time = time.time()
        # Update the test builds cache if needed
        self.__update_test_builds_cache__(test_instance)
        elapsed_time = time.time() - start_time
        if elapsed_time > 0.100:
            logger.info("Cache of test builds for test instance %s updated in %.2f seconds", test_instance.uuid, elapsed_time)

        # Start timing for fetching runs from cache
        start_time = time.time()
        # Return the builds from the cache
        runs = self.test_instance_cache.get_latest_runs(
            test_instance.uuid, self.get_instance_external_link(test_instance), limit=limit
        )
        elapsed_time = time.time() - start_time
        logger.debug("Fetching runs from cache took %.2f seconds for test instance %s", elapsed_time, test_instance.uuid)

        logger.debug("Found %d cached runs for test instance %s", len(runs), test_instance.uuid)
        builds = []
        if runs:
            # Start timing for building GithubTestBuild objects
            start_time = time.time()
            for run in runs:
                builds.append(GithubTestBuild(
                    testing_service=test_instance.testing_service,
                    test_instance=test_instance,
                    metadata=WorkflowRun(
                        requester=None,
                        headers=None,
                        attributes=run,
                        completed=True
                    )
                ))
            elapsed_time = time.time() - start_time
            logger.debug("Building GithubTestBuild objects took %.2f seconds for test instance %s", elapsed_time, test_instance.uuid)

        total_elapsed_time = time.time() - total_start_time
        logger.debug("Total time for getting test builds for test instance %s is %.2f seconds", test_instance.uuid, total_elapsed_time)
        return builds

    def get_test_build(self, test_instance: models.TestInstance, build_number: str) -> GithubTestBuild:
        """
        Get a specific test build by its build number.
        :param test_instance: The test instance to get the build for.
        :param build_number: The build number to get.
        :return: A GithubTestBuild object.
        """
        try:

            # total time
            total_start_time = time.time()

            # Start timing for cache update
            start_time = time.time()
            # Update the test builds cache if needed
            self.__update_test_builds_cache__(test_instance)
            elapsed_time = time.time() - start_time
            logger.debug("Cache update took %.2f seconds for test instance %s", elapsed_time, test_instance.uuid)

            # Retrieve the run from the cache
            run = self.test_instance_cache.get_run_by_id(self.get_instance_external_link(test_instance), build_number)
            logger.debug("Fetched run %s from cache for test instance %s", build_number, test_instance.uuid)
            build = None
            if run:
                build = GithubTestBuild(
                    testing_service=test_instance.testing_service,
                    test_instance=test_instance,
                    metadata=WorkflowRun(
                        requester=None,
                        headers=None,
                        attributes=run,
                        completed=True
                    )
                )

            total_elapsed_time = time.time() - total_start_time
            logger.debug("Total time for getting test build for test instance %s is %.2f seconds", test_instance.uuid, total_elapsed_time)
            return build

        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    def get_instance_external_link(self, test_instance: models.TestInstance) -> str:
        _, repo_full_name, workflow_id = self._get_workflow_info(test_instance.resource)
        return f'https://github.com/{repo_full_name}/actions/workflows/{workflow_id}'

    def get_test_build_external_link(self, test_build: models.TestBuild) -> str:
        _, repo_full_name, _ = self._get_workflow_info(test_build.test_instance.resource)
        if test_build.attempt_number:
            return f'https://github.com/{repo_full_name}/actions/runs/{test_build.build_number}/attempts/{test_build.attempt_number}'
        return f'https://github.com/{repo_full_name}/actions/runs/{test_build.build_number}'

    def get_test_build_output(self, test_instance: models.TestInstance, build_number, offset_bytes=0, limit_bytes=131072):
        raise lm_exceptions.NotImplementedException(detail="not supported for GitHub test builds")

    def batch_update_workflows(self, test_instances: list[models.TestInstance]) -> list[models.TestInstance]:
        """
        Batch update the given test instances with the latest data from the remote service.
        This method is used to refresh the test instances data from the remote service.
        """
        logger.info("Starting update of test %d instances ...", len(test_instances))
        # Set reference to the cache manager
        cache_manager = self.test_instance_cache

        # Keep track of updated instances
        updated_instances: set[models.TestInstance] = set()

        # Set of instance not initialized yet
        uninitialized_instances: set[models.TestInstance] = set()

        # Keep total execution time
        total_start_time = time.time()

        # extract the set of workflow urls from test instances
        urls_map = {}
        for instance in test_instances:
            url = instance.external_link
            if url not in urls_map:
                urls_map[url] = []
            urls_map[url].append(instance)
            # check if the instance is in cache
            if not cache_manager.get_update_timestamp(instance.uuid):
                uninitialized_instances.add(instance)
        logger.info("Collected %d URLs of workflows to update...", len(urls_map))
        for url, instances in urls_map.items():
            logger.debug("Updating workflow %s with instances: %r", url, instances)

        # Add uninitialized instances to updated instances
        updated_instances.update(uninitialized_instances)

        # Process uninitialized instances
        if len(uninitialized_instances) == 0:
            logger.info("No uninitialized test instances found.")
        else:
            logger.info("Processing uninitialized test instances...")
            start_time = time.time()
            for instance in uninitialized_instances:
                self.get_test_builds(instance)
            elapsed_time = time.time() - start_time
            logger.info("Processed %d uninitialized test instances in %.2f seconds",
                        len(uninitialized_instances), elapsed_time)

        # Fetch the workflows from the remote service
        logger.info("Fetching workflow (runs) updates from Github in batches of 20...")
        workflows = {}
        start_time = time.time()
        url_keys = list(urls_map.keys())
        for i in range(0, len(url_keys), 20):
            batch = url_keys[i:i + 20]
            logger.debug("Fetching batch %d-%d of workflows...", i + 1, min(i + 20, len(url_keys)))
            workflows.update(self._gh_graphql_service.fetch_workflows_runs_by_urls(batch))
        elapsed_time = time.time() - start_time
        logger.info("Fetched %d workflows in %.2f seconds", len(workflows), elapsed_time)

        # Map runs to test instances and update test_instance cache
        logger.info("Mapping fetched workflows to test instances...")
        start_time = time.time()
        for w, wdata in workflows.items():
            logger.info("- Processing workflow %s...", w)
            logger.info("- Processing test instances related to the workflow %s", w)
            logger.info("Searching for matching test instances for workflow %s ...", w)
            for instance in urls_map[w]:
                logger.info("Processing test instance %r ...", instance.uuid)
                instance_runs = cache_manager.get_latest_run_ids(instance.uuid)
                workflow_runs = wdata.get("workflow_runs", [])
                logger.info("Found %d workflow runs for workflow %s", len(workflow_runs), w)
                for run in workflow_runs:
                    if instance_runs and run["id"] in instance_runs:
                        logger.info("Found matching run %d for test instance %r", run["id"], instance.uuid)
                        cached_run = cache_manager.get_run_by_id(w, run["id"])
                        if cached_run and cached_run["conclusion"]:
                            logger.info("The workflow run %d for test instance %r is in cache and completed",
                                        run["id"], instance.uuid)
                            continue
                    # Try to match the test instance with the workflow run
                    params = (run["head_branch"], run["head_branch"], run["created_at"])
                    match = match_test_instance_params(instance, params)
                    if match:
                        logger.info("Found matching test instance %r: %r", instance.uuid, params)
                        cache_manager\
                            .associate_and_insert_run(instance.uuid, w,
                                                      run["id"], run["head_branch"], run, True)
                cache_manager.set_update_timestamp(instance.uuid)
                # Add instance to updated instances
                updated_instances.add(instance)

        # Compute elapsed time
        elapsed_time = time.time() - start_time
        logger.info("Mapping fetched workflows to test instances completed in %.2f seconds", elapsed_time)

        # Keep total execution time
        total_elapsed_time = time.time() - total_start_time
        logger.info("Total execution time for 'check_last_build' task: %.2f seconds", total_elapsed_time)
        return updated_instances
