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
import re
import time
from typing import List, Optional

import github
from github import GithubException
from github import \
    RateLimitExceededException as GithubRateLimitExceededException
from github.GithubException import UnknownObjectException
from github.RateLimit import RateLimit
from github.Repository import Repository
from github.Workflow import Workflow
from github.WorkflowRun import WorkflowRun

import lifemonitor.api.models as models
import lifemonitor.exceptions as lm_exceptions
from lifemonitor.api.models.testsuites.testbuild import TestBuild
from lifemonitor.api.models.testsuites.testinstance import TestInstance
from lifemonitor.cache import Timeout, cached
from lifemonitor.integrations.github.utils import (CachedPaginatedList,
                                                   GithubApiWrapper)

from ..models import GithubStatus
from ..test_build import GithubTestBuild
from ..utils import get_workflow_params, parse_workflow_url

# set module level logger
logger = logging.getLogger(__name__)

# TODO: make these configurable
__configuration__ = {
    'retry': 2,
    'timeout': 11,
    'per_page': 100
}


class GithubRestService():

    _gh_obj = None
    __mapper_args__ = {
        'polymorphic_identity': 'github_testing_service'
    }

    def __init__(self, url: str = None,
                 token: models.TestingServiceToken = None,
                 retry=__configuration__['retry'],
                 timeout=__configuration__['timeout'],
                 per_page=__configuration__['per_page']) -> None:
        logger.debug("GithubTestingService constructor instantiating client")
        # If no URL is provided, use the default Github API base URL
        if not url:
            url = github.MainClass.DEFAULT_BASE_URL
        # Call the parent constructor
        # to initialize the TestingService with the URL and token
        # super(GithubRestService, self).__init__(url, token=token)
        self.url = url
        self.token = token
        # Store the configuration parameters
        self._configuration_ = {
            'retry': retry,
            'timeout': timeout,
            'per_page': per_page
        }

    def __repr__(self):
        return f"<GithubRestService url={self.url} token={self.token is not None}>"

    def __str__(self):
        return f"GithubRestService(url={self.url}, token={self.token is not None})"

    def initialize(self):
        try:
            logger.debug("Instantiating with: url %s; token: %r\nClient configuration: %s",
                         self.url, self.token is not None, self._configuration_)
            self._gh_obj = GithubApiWrapper(base_url=self.url,
                                            login_or_token=self.token.value if self.token else None,
                                            **self._configuration_)
            logger.debug("Github client created.")
        except Exception as e:
            raise lm_exceptions.TestingServiceException(e)

    @property
    def base_url(self):
        return 'https://github.com'

    @property
    def api_base_url(self):
        return github.MainClass.DEFAULT_BASE_URL

    @property
    def _gh_service(self) -> GithubApiWrapper:
        logger.debug("Github client requested.")
        if not self._gh_obj:
            self.initialize()
        return self._gh_obj

    def get_rate_limit(self) -> RateLimit:
        """
        Fetches the current rate limit status from the GitHub REST API.

        :return: A dictionary containing the rate limit status.
        """
        try:
            rate_limit = self._gh_service.get_rate_limit()
            logger.debug("Rate limit status: %s", rate_limit)
            return rate_limit
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e))

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _get_workflow_info(self, resource):
        server, owner, repo, workflow_id = parse_workflow_url(resource)
        return server, f"{owner}/{repo}", workflow_id

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _get_fine_grained_workflow_info(self, resource):
        return parse_workflow_url(resource)

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _get_repo(self, test_instance: models.TestInstance):
        logger.debug("Getting github repository from remote service...")
        _, repo_full_name, _ = self._get_workflow_info(test_instance.resource)
        repository = self._gh_service.get_repo(repo_full_name)
        logger.debug("Repo ID: %s", repository.id)
        logger.debug("Repo full name: %s", repository.full_name)
        logger.debug("Repo URL: %s", f'https://github.com/{repository.full_name}')
        return repository

    @staticmethod
    def _convert_github_exception_to_lm(github_exc: GithubException) -> lm_exceptions.LifeMonitorException:
        return lm_exceptions.LifeMonitorException(
            title=github_exc.__class__.__name__,
            status=github_exc.status,
            detail=str(github_exc),
            data=github_exc.data,
            headers=github_exc.headers)

    def check_connection(self) -> bool:
        try:
            # Call the GET /rate_limit API to test the connection. Seems to be the
            # simplest call with a small, constant-size result
            self._gh_service.get_rate_limit()
            logger.debug("GithubTestingService:  check_connection() -> seems ok")
            return True
        except GithubException as e:
            logger.info("Caught exception from Github GET /rate_limit: %s.  Connection not working?", e)
            return False

    def fetch_workflow_runs_by_test_instance(self, i: TestInstance,
                                             branch=None,
                                             tag=None,
                                             created=None,
                                             limit: int = None,
                                             max_retries: int = 5,
                                             retry_delay: int = 1) -> list[WorkflowRun]:
        """
        Returns the GitHub workflow object for the service.
        This method is a placeholder and should be implemented in subclasses.
        """
        from requests import Session
        session = Session()
        session.headers.update({
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'requests',
            'Authorization': f'token {self.token.value}' if self.token else ''
        })

        # if none of branch, tag, created are set, try to ex
        if branch is None and tag is None and created is None:
            logger.debug("No filter provided, trying to extract from test instance...")
            # Compute workflow parameters
            branch, tag, created = get_workflow_params(i)
            logger.debug("Fetching workflow runs for test instance %s - branch: %r, tag: %r, created: %r",
                         i.uuid, branch, tag, created)
            # Skip created filter if branch or tag is set
            if branch is not github.GithubObject.NotSet or tag is not github.GithubObject.NotSet:
                created = github.GithubObject.NotSet

        # Construct the API URL for workflow runs
        api_url = (f"{self.api_base_url}/{i.resource}/runs")
        logger.debug("API URL: %s", api_url)
        # Start building the query string
        params = []
        if branch and branch is not github.GithubObject.NotSet:
            params.append(f"branch={branch}")
        elif tag is not github.GithubObject.NotSet:
            params.append(f"head_sha={i.test_suite.workflow_version.repository.revision.sha}")

        if created and created is not github.GithubObject.NotSet:
            params.append(f"created={created}")

        # Add query parameters to the URL
        if params:
            api_url += "?" + "&".join(params)
        logger.debug("Final API URL with params: %s", api_url)

        # Start timing
        start_time = time.time()
        # Log the start of the query execution
        logger.info("Starting REST query execution at %s", start_time)
        # Set up retry parameters
        retry_count = 0
        # Perform the request with retries
        while True:
            try:
                # Execute the query using the session
                response = session.get(api_url)

                # Check for HTTP errors
                if response.status_code == 403 or \
                        response.status_code == 429 or 500 <= response.status_code < 600:
                    # Handle rate limit headers for GitHub API
                    rate_limit_remaining = int(response.headers.get("x-ratelimit-remaining", 1))
                    rate_limit_reset = int(response.headers.get("x-ratelimit-reset", 0))
                    current_time = time.time()

                    # If Retry-After header exists, respect it
                    retry_after = int(response.headers.get("retry-after", 0))
                    if retry_after > 0:
                        logger.warning(f"Received status {response.status_code} with Retry-After={retry_after}. Sleeping...")
                        time.sleep(retry_after)
                    elif rate_limit_remaining == 0:
                        # Calculate wait time until rate limit reset
                        wait_time = rate_limit_reset - current_time
                        if wait_time > 0:
                            logger.warning(f"Rate limit reached, waiting {wait_time:.2f} seconds before retry")
                            time.sleep(wait_time)
                    else:
                        # Handle other 5xx errors with exponential backoff
                        if retry_count < max_retries:
                            retry_count += 1
                            wait_time = retry_delay * (2 ** (retry_count - 1))
                            logger.warning(f"Request failed with status {response.status_code}. Retrying in {wait_time}s (attempt {retry_count}/{max_retries})")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"Request failed with status {response.status_code} after {max_retries} retries")
                            response.raise_for_status()
                    continue

                # Break the loop if no retry needed or retries exhausted
                break

            except Exception as e:
                # Network-related errors
                if retry_count < max_retries:
                    retry_count += 1
                    wait_time = retry_delay * (2 ** (retry_count - 1))
                    logger.warning(f"Request failed with error: {str(e)}. Retrying in {wait_time}s (attempt {retry_count}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {max_retries} retries: {str(e)}")
                    logger.error("Failed to fetch workflow runs from GitHub API. Status code: %s", response.status_code)
                    raise lm_exceptions.GithubApiException(
                        title="GitHub API Error",
                        status=response.status_code,
                        detail=response.text
                    )

        logger.debug("Successfully fetched workflow runs from GitHub API.")
        # End timing
        execution_time = time.time() - start_time
        logger.info("REST query execution completed in %.2f seconds", execution_time)
        # Parse the response JSON to get the workflow runs
        workflow_runs = response.json().get('workflow_runs', [])
        if workflow_runs:
            # Assuming we want the first workflow run for simplicity
            workflow_runs = workflow_runs[:limit] if limit else workflow_runs
            return [WorkflowRun(
                requester=None,  # self._gh_service.__requester,
                headers=response.headers,
                attributes=run,
                completed=True
            ) for run in workflow_runs]
        # Return an empty list if no workflow runs were found
        return []

    def get_test_instance_builds(self, test_instance: TestInstance) -> dict[str, TestBuild]:
        """
        Returns the test instance builds for the given test instance.
        """
        workflow_runs = self.fetch_workflow_runs_by_test_instance(test_instance)
        builds = {}
        if not workflow_runs:
            logger.debug("No workflow runs found for test instance %s", test_instance.uuid)
            return builds
        for run in workflow_runs:
            logger.debug("Processing workflow run: %s", run.id)
            # Create a GithubTestBuild instance for each workflow run
            build = GithubTestBuild(
                testing_service=test_instance.testing_service,
                test_instance=test_instance,
                metadata=run
            )
            builds[build.id] = build
        logger.debug("Found %d builds for test instance %s", len(builds), test_instance.uuid)
        if not builds:
            logger.debug("No builds found for test instance %s", test_instance.uuid)
        return builds

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _get_gh_workflow(self, repository, workflow_id) -> Workflow:
        logger.debug("Getting github workflow...")
        return self._gh_service.get_repo(repository).get_workflow(workflow_id)

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _get_gh_workflow_from_test_instance_resource(self, test_instance_resource: str) -> Workflow:
        _, repository, workflow_id = self._get_workflow_info(test_instance_resource)
        logger.debug("Getting github workflow --  wf id: %s; repository: %s", workflow_id, repository)

        workflow = self._get_gh_workflow(repository, workflow_id)
        logger.debug("Retrieved workflow %s from github", workflow_id)

        return workflow

    def __get_gh_workflow_runs__(self,
                                 workflow: github.Worflow.Workflow,
                                 branch=github.GithubObject.NotSet,
                                 status=github.GithubObject.NotSet,
                                 created=github.GithubObject.NotSet,
                                 limit: Optional[int] = None) -> CachedPaginatedList:
        """
        Extends `Workflow.get_runs` to support `created` param
        """
        logger.debug("Getting runs of workflow %r ...", workflow)
        branch = branch or github.GithubObject.NotSet
        status = status or github.GithubObject.NotSet
        created = created or github.GithubObject.NotSet
        assert (branch is github.GithubObject.NotSet or isinstance(branch, github.Branch.Branch) or isinstance(branch, str)), branch
        assert status is github.GithubObject.NotSet or isinstance(status, str), status
        url_parameters = dict()
        if branch is not github.GithubObject.NotSet:
            url_parameters["branch"] = (
                branch.name if isinstance(branch, github.Branch.Branch) else branch
            )
        if created is not github.GithubObject.NotSet:
            url_parameters["created"] = created
        if status is not github.GithubObject.NotSet:
            url_parameters["status"] = status
        logger.debug("Getting runs of workflow %r - branch: %r", workflow, branch)
        logger.debug("Getting runs of workflow %r - status: %r", workflow, status)
        logger.debug("Getting runs of workflow %r - created: %r", workflow, created)
        logger.debug("Getting runs of workflow %r - params: %r", workflow, url_parameters)
        # return github.PaginatedList.PaginatedList( # Default pagination class
        logger.debug("Getting runs of workflow %r - limit: %r %r", workflow, limit, url_parameters)
        # return self.__get_gh_workflow_runs_iterator(workflow, url_parameters, limit=limit)

        return CachedPaginatedList(
            github.WorkflowRun.WorkflowRun,
            workflow._requester,
            f"{workflow.url}/runs",
            url_parameters,
            None,
            transactional_update=True,
            list_item="workflow_runs",
            limit=limit,
            # disable force_use_cache: a run might be updated with new attempts even when its status is completed
            # force_use_cache=lambda r: r.status == GithubStatus.COMPLETED and r.raw_data['run']
        )

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True,
            force_cache_value=lambda r: r[1]["status"] == GithubStatus.COMPLETED)
    def __get_gh_workflow_run_attempt__(self,
                                        workflow_run: github.WorkflowRun.WorkflowRun,
                                        attempt: int):
        url = f"{workflow_run.url}/attempts/{attempt}"
        logger.debug("Attempt URL: %r", url)
        headers, data = workflow_run._requester.requestJsonAndCheck("GET", url)
        return headers, data

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def __get_gh_workflow_run_attempts__(self,
                                         workflow_run: github.WorkflowRun.WorkflowRun,
                                         limit: Optional[int] = None) -> List[github.WorkflowRun.WorkflowRun]:
        result = []
        i = workflow_run.raw_data['run_attempt']
        while i >= 1:
            headers, data = self.__get_gh_workflow_run_attempt__(workflow_run, i)
            result.append(WorkflowRun(workflow_run._requester, headers, data, True))
            i -= 1
            if limit and len(result) == limit:
                break
        return result

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def __get_workflow_runs_iterator(self, workflow: Workflow.Workflow, test_instance: models.TestInstance,
                                     limit: Optional[int] = None) -> CachedPaginatedList:
        branch = github.GithubObject.NotSet
        created = github.GithubObject.NotSet
        try:
            branch = test_instance.test_suite.workflow_version.revision.main_ref.shorthand
            assert branch, "Branch cannot be empty"
        except Exception:
            branch = github.GithubObject.NotSet
            logger.debug("No revision associated with workflow version %r", workflow)
            workflow_version = test_instance.test_suite.workflow_version
            logger.debug("Checking Workflow version: %r (previous: %r, next: %r)",
                         workflow_version, workflow_version.previous_version, workflow_version.next_version)
            if workflow_version.previous_version and workflow_version.next_version:
                created = "{}..{}".format(workflow_version.created.isoformat(),
                                          workflow_version.next_version.created.isoformat())
            elif workflow_version.previous_version:
                created = ">={}".format(workflow_version.created.isoformat())
            elif workflow_version.next_version:
                created = "<{}".format(workflow_version.next_version.created.isoformat())
            else:
                logger.debug("No previous version found, then no filter applied... Loading all available builds")
        logger.debug("Fetching runs : %r - %r", branch, created)
        # return list(self.__get_gh_workflow_runs__(workflow, branch=branch, created=created))
        # return list(itertools.islice(self.__get_gh_workflow_runs__(workflow, branch=branch, created=created), limit))

        # return self.__get_gh_workflow_runs__(workflow, branch=branch, created=created, limit=limit)
        return workflow.get_runs(
            branch=branch,
            status=github.GithubObject.NotSet,
            created=created,
            limit=limit
        )

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _list_workflow_runs(self, test_instance: models.TestInstance,
                            status: Optional[str] = None, limit: int = 10) -> List[github.WorkflowRun.WorkflowRun]:
        # get gh workflow
        workflow = self._get_gh_workflow_from_test_instance_resource(test_instance.resource)
        logger.debug("Retrieved workflow %s from github", workflow)
        logger.debug("Workflow Runs Limit: %r", limit)
        logger.debug("Workflow Runs Status: %r", status)

        return [_ for _ in self.__get_workflow_runs_iterator(workflow, test_instance, limit=limit)][:limit]

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _list_workflow_run_attempts(self, test_instance: models.TestInstance,
                                    status: Optional[str] = None, limit: int = 10) -> List[github.WorkflowRun.WorkflowRun]:
        # get gh workflow
        workflow = self._get_gh_workflow_from_test_instance_resource(test_instance.resource)
        logger.debug("Retrieved workflow %s from github", workflow)
        logger.debug("Workflow Runs Limit: %r", limit)
        logger.debug("Workflow Runs Status: %r", status)

        result = []
        for run in self.__get_workflow_runs_iterator(workflow, test_instance):
            logger.debug("Loading Github run ID %r", run.id)
            # The Workflow.get_runs method in the PyGithub API has a status argument
            # which in theory we could use to filter the runs that are retrieved to
            # only the ones with the status that interests us.  This worked in the past,
            # but as of 2021/06/23 the relevant Github API started returning only the
            # latest three matching runs when we specify that argument.
            #
            # To work around the problem, we call `get_runs` with no arguments, thus
            # retrieving all the runs regardless of status, and then we filter below.
            # if status is None or run.status == status:
            logger.debug("Number of attempts of run ID %r: %r", run.id, run.raw_data['run_attempt'])
            if (limit is None or limit > 1) and run.raw_data['run_attempt'] > 1:
                for attempt in self.__get_gh_workflow_run_attempts__(
                        run, limit=(limit - len(result) if limit else None)):
                    logger.debug("Attempt: %r %r %r", attempt, status, attempt.status)
                    if status is None or attempt.status == status:
                        result.append(attempt)
            else:
                if status is None or run.status == status:
                    result.append(run)
            # stop iteration if the limit is reached
            if len(result) >= limit:
                break

        for run in result:
            logger.debug("Run: %r --> %r -- %r", run, run.created_at, run.updated_at)
        return result

    def get_last_test_build(self, test_instance: models.TestInstance) -> Optional[GithubTestBuild]:
        try:
            logger.debug("Getting latest build...")
            for run in self._list_workflow_run_attempts(test_instance, status=self.GithubStatus.COMPLETED):
                return GithubTestBuild(self, test_instance, run)
            logger.debug("Getting latest build... DONE")
            return None
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    def get_last_passed_test_build(self, test_instance: models.TestInstance) -> Optional[GithubTestBuild]:
        try:
            logger.debug("Getting last passed build...")
            for run in self._list_workflow_run_attempts(test_instance, status=self.GithubStatus.COMPLETED):
                if run.conclusion == self.GithubConclusion.SUCCESS:
                    return GithubTestBuild(self, test_instance, run)
            return None
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    def get_last_failed_test_build(self, test_instance: models.TestInstance) -> Optional[GithubTestBuild]:
        try:
            logger.debug("Getting last failed build...")
            for run in self._list_workflow_run_attempts(test_instance, status=self.GithubStatus.COMPLETED):
                if run.conclusion == self.GithubConclusion.FAILURE:
                    return GithubTestBuild(self, test_instance, run)
            return None
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    def get_test_builds(self, test_instance: models.TestInstance, limit=10) -> list:
        try:
            logger.debug("Getting test builds...")
            return [GithubTestBuild(self, test_instance, run)
                    for run in self._list_workflow_run_attempts(test_instance, limit=limit)[:limit]]
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), instance=test_instance)

    @cached(timeout=Timeout.NONE, client_scope=False,
            force_cache_value=lambda b: b._metadata.status == GithubStatus.COMPLETED)
    def get_test_build(self, test_instance: models.TestInstance, build_number: int) -> GithubTestBuild:
        try:
            # parse build identifier
            run_attempt = None
            if isinstance(build_number, str) and re.match(r".*_\d+$", build_number):
                run_id, run_attempt = build_number.split('_')
            else:
                run_id = build_number
            logger.debug("Searching build: %r %r", run_id, run_attempt)
            # get a reference to the test instance repository
            repo: Repository = self._get_repo(test_instance)
            headers, data = self._get_test_build(run_id, run_attempt, repo)
            return GithubTestBuild(self, test_instance, WorkflowRun(repo._requester, headers, data, True))
        except ValueError as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(e)
            raise lm_exceptions.BadRequestException(detail="Invalid build identifier")

    @cached(timeout=Timeout.NONE, client_scope=False,
            force_cache_value=lambda b: b[1]['status'] == GithubStatus.COMPLETED)
    def _get_test_build(self, run_id, run_attempt, repo: Repository) -> GithubTestBuild:
        try:
            # build url
            if run_attempt:
                url = f"/repos/{repo.full_name}/actions/runs/{run_id}/attempts/{run_attempt}"
            else:
                url = f"/repos/{repo.full_name}/actions/runs/{run_id}"
            logger.debug("Build URL: %s", url)
            headers, data = repo._requester.requestJsonAndCheck("GET", url)
            return headers, data
        except ValueError as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(e)
            raise lm_exceptions.BadRequestException(detail="Invalid build identifier")
        except GithubRateLimitExceededException as e:
            raise lm_exceptions.RateLimitExceededException(detail=str(e), run_id=run_id, run_attempt=run_attempt)
        except UnknownObjectException as e:
            raise lm_exceptions.EntityNotFoundException(models.TestBuild, entity_id=f"{run_id}_{run_attempt}", detail=str(e))

    def get_instance_external_link(self, test_instance: models.TestInstance) -> str:
        _, repo_full_name, workflow_id = self._get_workflow_info(test_instance.resource)
        return f'https://github.com/{repo_full_name}/actions/workflows/{workflow_id}'

    def get_test_build_external_link(self, test_build: models.TestBuild) -> str:
        repo = self._get_repo(test_build.test_instance)
        if test_build.attempt_number is None:
            return f'https://github.com/{repo.full_name}/actions/runs/{test_build.build_number}'
        return f'https://github.com/{repo.full_name}/actions/runs/{test_build.build_number}/attempts/{test_build.attempt_number}'

    def get_test_build_output(self, test_instance: models.TestInstance, build_number, offset_bytes=0, limit_bytes=131072):
        raise lm_exceptions.NotImplementedException(detail="not supported for GitHub test builds")

    def start_test_build(self, test_instance: models.TestInstance, build_number: int = None) -> bool:
        try:
            last_build = self.get_last_test_build(test_instance) \
                if build_number is None else self.get_test_build(test_instance, build_number)
            assert last_build
            if last_build:
                run: WorkflowRun = last_build._metadata
                assert isinstance(run, WorkflowRun)
                return run.rerun()
            else:
                workflow = self._get_gh_workflow_from_test_instance_resource(test_instance.resource)
                assert isinstance(workflow, Workflow), workflow
                return workflow.create_dispatch(test_instance.test_suite.workflow_version.version)
        except Exception as e:
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(e)
        return False
