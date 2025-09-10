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

from flask import current_app

import lifemonitor.exceptions as lm_exceptions
from lifemonitor.api.models.workflows import Workflow, WorkflowVersion
from lifemonitor.api.services import LifeMonitor
from lifemonitor.integrations.validator.services import \
    validate_workflow_version as do_validate_workflow_version

# Initialize a reference to the LifeMonitor instance
lm = LifeMonitor.get_instance()

# Config a module level logger
logger = logging.getLogger(__name__)


def validate_workflow(wf_uuid: str, severity: str) -> dict:
    try:
        workflow: Workflow = Workflow.find_by_uuid(wf_uuid)
        if not workflow:
            raise lm_exceptions.EntityNotFoundException(Workflow, entity_id=wf_uuid)
        return validation_workflow_version_object(workflow.latest_version, severity)
    except (KeyError, ValueError) as e:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Error handling workflow {wf_uuid}: {e}")
        raise lm_exceptions.BadRequestException(detail=f"Invalid workflow {wf_uuid}")


def validate_workflow_version(wf_uuid: str, wf_version: str, severity: str) -> dict:
    try:
        workflow: Workflow = Workflow.find_by_uuid(wf_uuid)
        if not workflow:
            raise lm_exceptions.EntityNotFoundException(Workflow, entity_id=wf_uuid)
        workflow_version: WorkflowVersion = workflow.versions[wf_version]
        return validation_workflow_version_object(workflow_version, severity)
    except (KeyError, ValueError) as e:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Error handling workflow {wf_uuid} version {wf_version}: {e}")
        raise lm_exceptions.BadRequestException(detail=f"Invalid workflow {wf_uuid} version {wf_version}")


def validation_workflow_version_object(workflow_version: WorkflowVersion,
                                       severity: Optional[str] = None) -> dict:
    logger.debug(f"Validating workflow {workflow_version}")
    assert workflow_version is not None, "Workflow version not defined"
    assert isinstance(workflow_version, WorkflowVersion), "Invalid workflow version object"
    try:
        result = do_validate_workflow_version(workflow_version.local_path, severity)
        response = current_app.response_class(
            response=result.to_json(),
            status=200,
            mimetype='application/json'
        )
        return response
    except Exception as e:
        logger.error(f"Error validating workflow {workflow_version}: {e}")
        return {
            "error": str(e)
        }
