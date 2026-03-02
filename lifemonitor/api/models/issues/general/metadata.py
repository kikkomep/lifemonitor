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

from lifemonitor.api.models.issues import IssueMessage, WorkflowRepositoryIssue
from lifemonitor.api.models.repositories import WorkflowRepository
from lifemonitor.integrations.validator.services import (
    ValidationResult, rocrate_validator_version, validate_workflow_version)

from .repo_layout import MissingROCrateFile, RepositoryNotInitialised

# set module level logger
logger = logging.getLogger(__name__)


class MissingWorkflowName(WorkflowRepositoryIssue):
    name = "Missing workflow name in metadata"
    description = "No name defined for this workflow. <br>You can set the workflow name on the `ro-crate-metadata.yaml` or `lifemonitor.yaml` file"
    labels = ['metadata']
    depends_on = [RepositoryNotInitialised]

    def check(self, repo: WorkflowRepository) -> bool:
        if repo.config and repo.config.workflow_name:
            return False
        if repo.metadata and repo.metadata.main_entity_name:
            return False
        return True


class InvalidMetadataFile(WorkflowRepositoryIssue):
    name = "Invalid metadata file"
    description = (
        "The validation of the metadata file `ro-crate-metadata.yaml` failed. "
        "<br>Check the file and fix the issues reported by the validator."
    )
    labels = ['metadata']
    depends_on = [MissingROCrateFile]

    def check(self, repo: WorkflowRepository) -> bool:
        try:
            # validate the metadata file
            result: ValidationResult = validate_workflow_version(repo.local_path, severity="REQUIRED")
            logger.debug(f"Validation result: {result}")
            # check if the validation failed
            if result and result.passed():
                return False
            # if the validation not passed, report the issues
            msg = ("The validation of the workflow repository using "
                   f"`rocrate-validator` (ver. {rocrate_validator_version}) "
                   "and the `workflow-testing-rocrate` profile revealed the following specification violations:\n")
            if result.failed_requirements:
                for requirement in sorted(result.failed_requirements, key=lambda x: x.identifier):
                    msg += f"\n{' ' * 128}[profile: {requirement.profile.name}]"
                    msg += f"\n{' ' * 5}[ {requirement.identifier} ]: {requirement.name}\n"
                    msg += f"\n{' ' * 6}{requirement.description}\n"
                    msg += f"\n{' ' * 10}Failed checks\n"
                    for check in sorted(result.get_failed_checks_by_requirement(requirement), key=lambda x: (-x.severity.value, x)):
                        msg += f"\n{' ' * 7}[ {check.identifier} ]  {check.name}:\n"
                        msg += f"{' ' * 29}{check.description}\n"
                        msg += f"{' ' * 9}Detected issues\n"
                        for issue in sorted(result.get_issues_by_check(check), key=lambda x: (-x.severity.value, x)):
                            path = ""
                            if issue.violatingProperty and issue.violatingPropertyValue:
                                path = f" of {issue.violatingProperty}"
                            if issue.violatingPropertyValue:
                                if issue.violatingProperty:
                                    path += "="
                                path += f"\"{issue.violatingPropertyValue}\" "
                            if issue.violatingEntity:
                                path = f"{path} on <{issue.violatingEntity}>"
                            msg += f"{' ' * 10}- [Violation{path}]: {issue.message}\n"
            # report the msg as issue comment
            self.add_message(IssueMessage(IssueMessage.TYPE.ERROR, msg))
            self.add_message(
                IssueMessage(IssueMessage.TYPE.INFO, (
                    "To reproduce offline the validation results, "
                    "you can execute the rocrate-validator with the following command:\n\n"
                    "`rocrate-validator --profile workflow-testing-ro-crate --requirement-severity REQUIRED <path-to-ro-crate-root>`"
                )))
            return True

        except Exception as e:
            logger.exception(f"Error validating metadata file: {e}")
