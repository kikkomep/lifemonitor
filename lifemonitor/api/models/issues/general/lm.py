# Copyright (c) 2020-2026 CRS4
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

from flask import current_app, has_app_context

from lifemonitor import config as lm_config
from lifemonitor.api.models.issues import IssueMessage, WorkflowRepositoryIssue
from lifemonitor.api.models.issues.general.repo_layout import \
    GitRepositoryWithoutMainBranch
from lifemonitor.api.models.repositories import WorkflowRepository
from lifemonitor.schemas.validators import ValidationError, ValidationResult
from lifemonitor.utils import get_validation_schema_url

# set module level logger
logger = logging.getLogger(__name__)


class MissingLMConfigFile(WorkflowRepositoryIssue):
    name = "Missing LifeMonitor configuration file"
    description = "No <code>lifemonitor.yaml</code> configuration file found on this repository.<br>"\
        "The <code>lifemonitor.yaml</code> should be placed on the root of this repository."
    labels = ['lifemonitor']
    depends_on = [GitRepositoryWithoutMainBranch]

    def check(self, repo: WorkflowRepository) -> bool:
        if repo.config is None:
            config = repo.generate_config()
            validation_result = config.validate()
            if validation_result:
                self.add_change(config)
            else:
                logger.error("MissingLMConfigFile generated an invalid configuration!")
                logger.error("Error:\n%s", validation_result)
                logger.error("Configuration:\n%s", config)
            return True
        return False


class InvalidConfigFile(WorkflowRepositoryIssue):

    name = "Invalid LifeMonitor configuration file"
    description = "The LifeMonitor configuration file found on this repository "\
                  f"is not valid according to the schema " \
                  f"<a href='{get_validation_schema_url()}'>{get_validation_schema_url()}</a>.<br>"
    labels = ['lifemonitor']
    depends_on = [MissingLMConfigFile]

    def check(self, repo: WorkflowRepository) -> bool:
        if repo.config is None:
            return True
        result: ValidationResult = repo.config.validate()
        if not result.valid:
            if isinstance(result, ValidationError):
                self.add_message(IssueMessage(IssueMessage.TYPE.ERROR, result.error))
                return True
        return False


class UnknownLifeMonitorInstance(WorkflowRepositoryIssue):

    name = "Unknown LifeMonitor instance in configuration file"
    enable_message_updates = True
    description = (
        "The LifeMonitor configuration file references one or more unknown values for "
        "<code>push.*.lifemonitor_instance</code>."
    )
    labels = ['lifemonitor']
    depends_on = [InvalidConfigFile]

    @staticmethod
    def _get_proxy_entries() -> dict | None:
        if has_app_context():
            entries = current_app.config.get('PROXY_ENTRIES', None)
            if entries is not None:
                return entries
            return lm_config.load_proxy_entries(current_app.config)
        return None

    def check(self, repo: WorkflowRepository) -> bool:
        if repo.config is None:
            return False

        proxy_entries = self._get_proxy_entries()
        if proxy_entries is None:
            logger.debug("Skipping proxy-instance validation: no Flask application context available")
            return False

        valid_instances = {str(name).strip().lower() for name in proxy_entries.keys() if str(name).strip()}
        push_data = repo.config._raw_data.get('push', {})

        unknown_instances = []
        for ref_type in ('branches', 'tags'):
            for ref in push_data.get(ref_type, []):
                configured_instance = ref.get('lifemonitor_instance', None)
                if configured_instance is None:
                    continue
                instance_name = str(configured_instance).strip().lower()
                if instance_name and instance_name not in valid_instances:
                    unknown_instances.append((ref_type, ref.get('name', '<unknown>'), instance_name))

        if not unknown_instances:
            return False

        available = ", ".join(sorted(valid_instances)) if valid_instances else "<none>"
        details = "\n".join(
            [f"- push.{ref_type} '{ref_name}': '{instance_name}'"
             for ref_type, ref_name, instance_name in unknown_instances]
        )
        message = (
            "Unable to resolve one or more configured LifeMonitor instances:\n"
            f"{details}\n\n"
            f"Available instances are: {available}.\n"
        )
        self.add_message(IssueMessage(IssueMessage.TYPE.ERROR, message))
        return True
