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
from typing import Optional

import github

import lifemonitor.api.models as models

from .models import GithubConclusion, GithubStatus

# set module level logger
logger = logging.getLogger(__name__)


class GithubTestBuild(models.TestBuild):
    def __init__(self,
                 testing_service: models.TestingService,
                 test_instance: models.TestInstance,
                 metadata: github.WorkflowRun.WorkflowRun) -> None:
        super().__init__(testing_service, test_instance, metadata)

    @property
    def id(self) -> str:
        # if self.attempt_number is not None:
        #     return f"{self._metadata.id}_{self.attempt_number}"
        return self._metadata.id

    @property
    def build_number(self) -> int:
        return self._metadata.id

    @property
    def attempt_number(self) -> Optional[int]:
        try:
            return self._metadata.raw_data.get('run_attempt', None)
        except AttributeError:
            # If the metadata does not have 'run_attempt', it means this is the first attempt
            return None

    @property
    def duration(self) -> int:
        return int((self._metadata.updated_at - self._metadata.created_at).total_seconds())

    def is_running(self) -> bool:
        return self._metadata.status == GithubStatus.IN_PROGRESS

    @property
    def metadata(self):
        # Rather than expose the PyGithub object outside this class, we expose
        # the raw metadata from Github
        return self._metadata.raw_data

    @property
    def result(self) -> models.TestBuild.Result:
        if self._metadata.status == GithubStatus.COMPLETED:
            if self._metadata.conclusion == GithubConclusion.SUCCESS:
                return models.TestBuild.Result.SUCCESS
            return models.TestBuild.Result.FAILED
        return None

    @property
    def revision(self):
        return self._metadata.head_sha

    @property
    def status(self) -> str:
        logger.debug("Determining status for build with metadata: status=%s, conclusion=%s",
                     self._metadata.status, self._metadata.conclusion)
        if self._metadata.status:
            status = self._metadata.status.lower()
            if status == GithubStatus.IN_PROGRESS:
                return models.BuildStatus.RUNNING
            if status == GithubStatus.QUEUED:
                return models.BuildStatus.WAITING
            if not status or status != GithubStatus.COMPLETED:
                logger.error("Unexpected run status value '%s'!!", status)
                # Try to keep going notwithstanding the unexpected status
        if self._metadata.conclusion:
            conclusion = self._metadata.conclusion.lower()
            if conclusion == GithubConclusion.SUCCESS:
                return models.BuildStatus.PASSED
            if conclusion == GithubConclusion.CANCELLED:
                return models.BuildStatus.ABORTED
            if conclusion == GithubConclusion.FAILURE:
                return models.BuildStatus.FAILED
        return models.BuildStatus.ERROR

    @property
    def timestamp(self) -> int:
        return int(self._metadata.created_at.timestamp())

    @property
    def created_at(self) -> int:
        return self._metadata.created_at

    @property
    def updated_at(self) -> int:
        return self._metadata.updated_at

    @property
    def url(self) -> str:
        if self.attempt_number:
            return f"{self._metadata.url}/runs/{self.attempt_number}"
        # If no attempt number, return the URL for the workflow run
        # It should point to the latest attempt
        return self._metadata.url

    def get_external_link(self):
        return self.url
