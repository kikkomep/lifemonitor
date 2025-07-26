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

import json
import logging
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
    _RESOURCE_PATTERN = re.compile(r"/?repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/actions/workflows/(?P<wf>[^/]+)")

    _gh_obj = None
    __mapper_args__ = {
        'polymorphic_identity': 'github_testing_service'
    }

    def __init__(self, url: str = None, token: models.TestingServiceToken = None) -> None:
        logger.debug("GithubTestingService constructor instantiating client")
        if not url:
            url = github.MainClass.DEFAULT_BASE_URL
        super().__init__(url, token)

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

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
    def _get_workflow_info(self, resource):
        return self._parse_workflow_url(resource)

    @cached(timeout=Timeout.NONE, client_scope=False, transactional_update=True)
        return parse_workflow_url(resource)

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
            # If no branch is specified, we check the created date
            else:
                server = ""
            m = cls._RESOURCE_PATTERN.match(result.path)
            if not m:
                raise RuntimeError("Malformed GitHub workflow path. Expected: 'repos/{owner}/{reponame}/actions/workflows/{workflow_id}'")
            repository = f'{m.group("owner")}/{m.group("repo")}'
            workflow_id = m.group("wf")
            logger.debug("parse result -- server: '%s'; repository: '%s'; workflow_id: '%s'", server, repository, workflow_id)
            return server, repository, workflow_id
        except URLError as e:
            raise lm_exceptions.SpecificationNotValidException(
                detail="Invalid link to Github Workflow",
                original_exception=str(e))
        except RuntimeError as e:
            raise lm_exceptions.SpecificationNotValidException(
                detail="Unexpected format of link to Github Workflow",
                parse_error=e.args[0])
