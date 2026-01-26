# Copyright (c) 2020-2026 CRS4
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
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

"""
Convert multiple GitHub GraphQL WorkflowRun nodes to REST-like envelopes
matching:
GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}/runs

Additions:
- Accept a list of workflow URLs and fetch them **in batch** via a single GraphQL
  request per page step using dynamic aliases.
- Cursor pagination with parameters: `--page` and `--per-page`.
- Output a mapping `{ url -> { total_count, workflow_runs[] } }`.

Notes:
- GraphQL does not support looping; we generate per-workflow aliases/variables
  ($u0,$a0), ($u1,$a1), ... and send one request.
- For page > 1 we advance cursors in (page-1) batch steps, minimizing requests.
- Some fields (event, run_attempt, triggering_actor, display_title, etc.) are
  not available here and are set to null for REST compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class UrlParts:
    owner: str
    repo: str
    api_base: str = "https://api.github.com"


def build_run_urls(
    parts: UrlParts,
    run_id: Optional[int],
    workflow_id: Optional[int],
    check_suite_id: Optional[int],
) -> Dict[str, str]:
    """Build REST URLs to mirror REST payload."""
    api = parts.api_base.rstrip("/")
    base = f"{api}/repos/{parts.owner}/{parts.repo}"
    r = run_id or 0
    w = workflow_id or 0
    cs = check_suite_id or 0
    return {
        "url": f"{base}/actions/runs/{r}",
        "jobs_url": f"{base}/actions/runs/{r}/jobs",
        "logs_url": f"{base}/actions/runs/{r}/logs",
        "artifacts_url": f"{base}/actions/runs/{r}/artifacts",
        "cancel_url": f"{base}/actions/runs/{r}/cancel",
        "rerun_url": f"{base}/actions/runs/{r}/rerun",
        "previous_attempt_url": f"{base}/actions/runs/{r}/attempts/1",
        "check_suite_url": f"{base}/check-suites/{cs}",
        "workflow_url": f"{base}/actions/workflows/{w}",
    }


def pick_head_branch(check_suite: Optional[dict]) -> Optional[str]:
    if not check_suite:
        return None
    branch = check_suite.get("branch") or {}
    return branch.get("name")


def map_run(parts: UrlParts, node: dict) -> dict:
    wf = node.get("workflow") or {}
    cs = node.get("checkSuite") or {}
    commit = cs.get("commit") or {}

    urls = build_run_urls(
        parts,
        node.get("databaseId"),
        wf.get("databaseId"),
        cs.get("databaseId"),
    )

    head_commit: Optional[dict]
    if commit:
        head_commit = {
            "id": commit.get("oid"),
            "message": commit.get("message"),
            "timestamp": commit.get("committedDate"),
            "author": {
                "name": (commit.get("author") or {}).get("name"),
                "email": (commit.get("author") or {}).get("email"),
            }
        }
    else:
        head_commit = None
    return {
        "id": node.get("databaseId"),
        "node_id": node.get("id"),
        "name": wf.get("name"),
        "path": wf.get("path"),
        "head_branch": pick_head_branch(cs),
        "head_sha": commit.get("oid") if commit else None,
        "run_number": int(node.get("runNumber")),
        "event": None,
        "status": cs.get("status"),
        "conclusion": cs.get("conclusion"),
        "workflow_id": wf.get("databaseId"),
        "check_suite_id": cs.get("databaseId"),
        "check_suite_node_id": cs.get("id"),
        "url": urls["url"],
        "html_url": node.get("url"),
        "jobs_url": urls["jobs_url"],
        "logs_url": urls["logs_url"],
        "check_suite_url": urls["check_suite_url"],
        "artifacts_url": urls["artifacts_url"],
        "cancel_url": urls["cancel_url"],
        "rerun_url": urls["rerun_url"],
        "previous_attempt_url": urls["previous_attempt_url"],
        "workflow_url": urls["workflow_url"],
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "run_attempt": None,
        "run_started_at": node.get("createdAt"),
        "triggering_actor": None,
        "head_commit": head_commit,
        "display_title": None,
    }


def map_resource_to_envelope(parts: UrlParts, resource: dict) -> dict:
    runs: List[dict] = ((resource.get("runs") or {}).get("nodes")) or []
    mapped = [map_run(parts, n) for n in runs]

    return {
        "total_count": len(mapped),
        "workflow_runs": [_ for _ in mapped]
    }


def parse_owner_repo_from_url(url: str) -> Optional[Tuple[str, str]]:
    m = re.match(r"^https?://github.com/([^/]+)/([^/]+)/", url)
    if not m:
        return None
    return m.group(1), m.group(2)


def normalize_batch_to_rest(
    urls: List[str],
    graphql_data: dict,
    exhausted: List[bool],
    api_base: str
) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for i, url in enumerate(urls):
        key = f"r{i}"
        resource = (graphql_data.get(key) or {})
        logger.debug("Processing resource: %r", resource)
        if exhausted[i] or not resource or "runs" not in resource:
            out[url] = {
                "total_count": 0,
                "workflow_runs": []
            }
            continue

        owner, repo = parse_owner_repo_from_url(url) or ("", "")
        parts = UrlParts(owner=owner, repo=repo, api_base=api_base)
        out[url] = map_resource_to_envelope(parts, resource)

    return out
