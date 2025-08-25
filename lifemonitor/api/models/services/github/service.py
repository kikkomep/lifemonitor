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

import lifemonitor.api.models as models
import lifemonitor.exceptions as lm_exceptions
from lifemonitor.api.models.services.github.cache import \
    TestInstanceCacheManager
from lifemonitor.api.models.services.github.graphql.models import GhWorkflow
from lifemonitor.api.models.services.github.graphql.service import \
    GithubGraphQLService
from lifemonitor.api.models.services.github.rest import GithubRestService
from lifemonitor.cache import Timeout, cache, cached

from ..service import TestingService
from .models import GithubStatus
from .test_build import GithubTestBuild
from .utils import parse_workflow_url

# set module level logger
logger = logging.getLogger(__name__)


class GithubTestingService(TestingService):

    _gh_obj = None
    _gh_graphql = None
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
            logger.debug("Latest build found: %s", builds[0])
            return builds[0] if builds else None
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    def get_last_passed_test_build(self, test_instance: models.TestInstance) -> Optional[GithubTestBuild]:
        try:
            logger.debug("Getting last passed build...")
            builds = self.get_test_builds(test_instance, limit=100)
            for build in builds:
                if build.conclusion == GithubStatus.SUCCESS:
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
                if build.conclusion == GithubStatus.FAILURE:
                    logger.debug("Last failed build found: %s", build)
                    return build
            logger.debug("No failed builds found for test instance %s", test_instance.uuid)
            return None
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    def get_test_builds(self, test_instance: models.TestInstance, limit=10) -> list:
        """
        Get the test builds for a given test instance.
        :param test_instance: The test instance to get the builds for.
        :param limit: The maximum number of builds to return.
        :return: A list of GithubTestBuild objects.
        """
        cache = TestInstanceCacheManager(test_instance)
        logger.debug("Getting test builds from cache for test instance %s", test_instance.uuid)
        # Check if the cache is valid
        if not cache.is_valid():
            logger.debug("Cache is not valid, fetching test builds from remote service")
            # Fetch the test builds from the remote service
            test_builds = self.update_test_instance(test_instance)
            return test_builds[:limit] if test_builds else []

        if cache.is_valid():
            logger.debug("Cache is valid, returning cached test builds")
            return cache.get_test_builds(limit=limit)

        logger.debug("Cache is not valid, but I'm not able to update it, returning empty list")
        # If the cache is not valid, return an empty list
        return []

    def get_test_build(self, test_instance: models.TestInstance, build_number: str) -> GithubTestBuild:
        """
        Get a specific test build by its build number.
        :param test_instance: The test instance to get the build for.
        :param build_number: The build number to get.
        :return: A GithubTestBuild object.
        """
        result = None
        try:
            cache = TestInstanceCacheManager(test_instance)
            logger.debug("Getting test build %s from cache for test instance %s", build_number, test_instance.uuid)
            # Check if the cache is valid
            if cache.is_valid():
                result = cache.get_test_build(build_number)
            # FIXME: This cause the reload of the test builds from the remote service: do we need it?
            # If the cache is not valid or the result is not found, fetch from remote service
            if not cache.is_valid() or result is None:
                logger.debug("Cache is not valid, fetching test builds from remote service")
                # Fetch the test builds from the remote service
                test_builds = self.update_test_instance(test_instance)
                result = next((build for build in test_builds if build.id == build_number), None)

        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

        # Uncomment the following lines
        # if you want to raise an exception when the build is not found
        # if result is None:
        #     raise lm_exceptions.NotFoundException(
        #         detail=f"Test build {build_number} not found for test instance {test_instance.uuid}",
        #         instance=test_instance
        #     )
        return result

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

    def update_test_instance(self, test_instance: models.TestInstance) -> list[GithubTestBuild]:
        """
        Update the test instance with the latest data from the remote service.
        This method is used to refresh the test instance data from the remote service.
        """
        logger.debug("Updating test instance %s", test_instance)
        # This method can be used to update the test instance with the latest data
        # from the remote service. Currently, it does nothing as we are not storing
        # any additional data in the test instance.
        return self.update_test_instances([test_instance])

    def update_test_instances(self, instances: list[models.TestInstance]) -> list[GithubTestBuild]:
        """
        Update the given test instances with the latest data from the remote service.
        This method is used to refresh the test instances data from the remote service.
        """
        logger.info("Starting update of test %d instances ...", len(instances))
        # extract the set of workflow urls from test instances
        urls_map = {}
        for instance in instances:
            url = instance.external_link
            if instance.resource not in urls_map:
                urls_map[url] = []
            urls_map[url].append(instance)
        logger.info("Collected %d URLs of workflows to update...", len(urls_map))

        # Fetch the workflows from the remote service
        logger.info("Fetching workflows from Github...")
        start_time = time.time()
        workflows = self._gh_graphql_service.get_workflows_by_url(urls_map.keys())
        elapsed_time = time.time() - start_time
        logger.info("Fetched %d workflows in %.2f seconds", len(workflows), elapsed_time)

        # Update the test instances with the fetched workflows
        # and extract the test builds from the workflows
        logger.info("- Updating test instances with the fetched workflows...")
        builds = []
        with cache.transaction(name=self.url, force_update=True) as t:
            start_time = time.time()
            for workflow in workflows:
                logger.debug("* Processing workflow %s...", workflow.url)
                logger.debug("- Processing test instances related to the workflow %s", workflow.url)
                t.set(workflow.url, workflow, timeout=Timeout.NONE)

                for instance in urls_map[workflow.url]:
                    logger.debug("-- Updating test instance %s for workflow %s", instance.uuid, workflow.url)
                    cache_manager = TestInstanceCacheManager(instance)
                    instance_builds = self.__extract_test_builds_from_workflow__(instance, workflow)
                    builds.extend(list(instance_builds.values()))
                    logger.debug("-- Found %d builds for test instance %s", len(instance_builds), instance.uuid)
                    # Update the test instance with the new builds
                    cache_manager.update(workflow, instance_builds)
                    instance._updated_at = cache_manager.updated_at
                    instance.save()
                    logger.debug("-- Updated test instance %s with %d builds", instance.uuid, len(instance_builds))
            # End timing
            elapsed_time = time.time() - start_time
            logger.info("- Extracted and updated test builds in %.2f seconds", elapsed_time)

        logger.info("- Updated %d test instances with %d builds", len(instances), len(builds))
        logger.info("Rate limit status after update: %s",
                    self._gh_graphql_service.get_rate_limit())
        logger.info("Update of test instances completed.")
        return builds

    def update_all_test_instances(self) -> list[GithubTestBuild]:
        """
        Update all test instances with the latest data from the remote service.
        This method is used to refresh the test instances data from the remote service.
        """
        logger.debug("Updating all test instances")
        # This method can be used to update all test instances with the latest data
        # from the remote service. Currently, it does nothing as we are not storing
        # any additional data in the test instance.
        instances = models.TestInstance.find_by_testing_service(self)
        logger.debug("Found %d test instances", len(instances))
        return self.update_test_instances(instances)

    def __extract_test_builds_from_workflow__(self, test_instance: models.TestInstance, gh_workflow: GhWorkflow) -> dict[str, GithubTestBuild]:
        """
        Extract test builds from the given workflow.
        This method is used to convert the workflow runs into GithubTestBuild objects.
        """

        assert isinstance(gh_workflow, GhWorkflow), \
            "gh_workflow must be an instance of GhWorkflow"
        assert gh_workflow.url == test_instance.external_link, \
            "gh_workflow URL must match the test instance external link"

        # Ensure the test instance has a workflow version associated
        workflow_version = test_instance.test_suite.workflow_version
        assert workflow_version, "Workflow version must be associated with the test instance"

        # Initialize the data structure to hold the builds
        builds = {}

        branch = None
        try:
            branch = workflow_version.revision.main_ref.shorthand
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug("No revision associated with workflow version %r: %s", workflow_version, e)
            branch = None

        for run in gh_workflow.runs:
            if branch:
                if branch != run.ref_name:
                    logger.debug("Skipping run %s with branch %s != %s", run.id, run.ref_name, branch)
                    continue
                else:
                    logger.debug("Adding run %s with branch %s", run.id, branch)
                    builds[run.id] = GithubTestBuild(
                        testing_service=test_instance.testing_service,
                        test_instance=test_instance,
                        metadata=run
                    )

            # If no branch is specified, we check the created date
            else:
                # If the run was created before the workflow version, skip it
                if run.created_at.isoformat() < workflow_version.created.isoformat():
                    logger.debug("Skipping run %s created at %s before workflow version created at %s",
                                 run.id, run.created_at, workflow_version.created)
                    continue
                # If the run was created after the next version, skip it
                elif workflow_version.next_version and \
                        run.created_at.isoformat() >= workflow_version.next_version.created.isoformat():
                    logger.debug("Skipping run %s created at %s after workflow version next version created at %s",
                                 run.id, run.created_at, workflow_version.next_version.created)
                    continue
                # Otherwise, we add the run to the builds
                else:
                    logger.debug("Adding run %s created at %s", run.id, run.created_at)
                    builds[run.id] = GithubTestBuild(
                        testing_service=test_instance.testing_service,
                        test_instance=test_instance,
                        metadata=run
                    )
        logger.debug("Extracted %d test builds from workflow %s", len(builds), gh_workflow.url)
        return builds
