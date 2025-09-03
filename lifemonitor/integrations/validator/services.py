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
from enum import Enum
from typing import Optional

from rocrate_validator import __version__ as rocrate_validator_version
from rocrate_validator.models import ValidationResult as ValidationResultBase
from rocrate_validator.models import ValidationSettings
from rocrate_validator.services import validate as validate_rocrate

# Config a module level logger
logger = logging.getLogger(__name__)

# Debug log the version of the rocrate-validator
logger.debug(f"Using rocrate-validator version {rocrate_validator_version}")


class OUTPUT_FORMAT(Enum):
    JSON = "json"
    TEXT = "text"


class ValidationResult(ValidationResultBase):
    pass


def validate_workflow_version(workflow_path: str,
                              severity: Optional[str] = None) -> ValidationResult:
    logger.debug(f"Validating workflow on path {workflow_path}")
    assert workflow_path is not None, "Workflow path not defined"
    result: ValidationResult = validate_rocrate(
        ValidationSettings(**{
            "rocrate_uri": workflow_path,
            "profile_identifier": "workflow-testing-ro-crate",
            "requirement_severity": severity
        }))
    logger.debug(f"Validation result: {result}")
    return result
