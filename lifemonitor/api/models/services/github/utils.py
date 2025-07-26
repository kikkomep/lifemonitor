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
from typing import Tuple
from urllib.error import URLError
from urllib.parse import urlparse

import lifemonitor.exceptions as lm_exceptions

# set module level logger
logger = logging.getLogger(__name__)


_RESOURCE_PATTERN = re.compile(r"/?repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/actions/workflows/(?P<wf>[^/]+)")


def parse_workflow_url(resource: str) -> Tuple[str, str, str]:
    """
    Utility method to parse github workflow URIs.  Given a URL to the testing
    Github Workflow, returns a tuple (server, repository, workflow_id).

    The `resource` can be a full url to a Github workflow; e.g.,

            https://api.github.com/repos/crs4/life_monitor/actions/workflows/4094661

    Alternatively, `resource` can forego the server part (e.g., `https://api.github.com`)
    and even the leading root slash of the path part.  For instance, `resource` can be:

            repos/crs4/life_monitor/actions/workflows/4094661

    In the latter case, the return value for server will be an empty string.
    """
    try:

        result = urlparse(resource)
        if result.scheme and result.netloc:
            server = f"{result.scheme}://{result.netloc}"
        else:
            server = ""
        m = _RESOURCE_PATTERN.match(result.path)
        if not m:
            raise RuntimeError("Malformed GitHub workflow path. Expected: 'repos/{owner}/{reponame}/actions/workflows/{workflow_id}'")
        owner = m.group("owner")
        repo = m.group("repo")
        repository = f"{owner}/{repo}"

        workflow_id = m.group("wf")
        logger.debug("parse result -- server: '%s'; repository: '%s'; workflow_id: '%s'", server, repository, workflow_id)
        return server, owner, repo, workflow_id

    except URLError as e:
        raise lm_exceptions.SpecificationNotValidException(
            detail="Invalid link to Github Workflow",
            original_exception=str(e))
    except RuntimeError as e:
        raise lm_exceptions.SpecificationNotValidException(
            detail="Unexpected format of link to Github Workflow",
            parse_error=e.args[0])
