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

import json
import logging
from typing import Any, Optional

from lifemonitor.api.models.services.github.graphql.queries import (
    build_multi_resources_query, get_rate_limit)
from lifemonitor.api.models.services.github.graphql.requester import \
    GraphQLRequester
from lifemonitor.api.models.services.github.graphql.utils import \
    normalize_batch_to_rest

# set module level logger
logger = logging.getLogger(__name__)


class GithubGraphQLService():
    """
    A service for interacting with GitHub's GraphQL API.
    """

    def __init__(self, token: Optional[str] = None) -> None:
        """
        Initializes the GitHub GraphQL service with an optional token.

        :param token: The personal access token for GitHub API authentication.
        """
        self.token = token
        self.requester = GraphQLRequester(token)

    def get_rate_limit(self) -> dict:
        """
        Fetches the current rate limit status from the GitHub GraphQL API.

        :return: A dictionary containing the rate limit status.
        """
        result = self.requester.execute_query(get_rate_limit)

        # pretty print of the result
        logger.debug(json.dumps(result, indent=2))

        if 'data' in result and 'rateLimit' in result['data']:
            return result['data']['rateLimit']
        return {}

    def __fetch_multi__(
        self,
        urls: list[str],
        afters: list[Optional[str]],
        per_page: int = 100,
        page: int = 1
    ) -> dict[str, dict]:
        """
        Fetches multiple workflow runs from GitHub GraphQL API.

        :param urls: List of workflow URLs.
        :param per_page: Number of items per page.
        :param page: Page number to fetch.
        :param api_base: Base URL for the API.
        :return: A dictionary mapping workflow URLs to their runs.
        """
        query = build_multi_resources_query(len(urls))
        variables: dict[str, Any] = {"first": per_page}
        for i, (u, a) in enumerate(zip(urls, afters)):
            variables[f"u{i}"] = u
            variables[f"a{i}"] = a
        data = self.requester.execute_query(query, variables=variables)
        logger.debug(json.dumps(data, indent=2))
        return data.get("data") or {}

    def __paginate_to_page__(
        self,
        urls: list[str],
        per_page: int = 100,
        page: int = 1
    ) -> tuple[dict, list[bool]]:
        """
        Paginate through workflow runs to the requested page.

        Advance all workflows to the requested page using batched queries.
        Returns (final_data, exhausted_flags).
        exhausted_flags[i] == True means the requested page is beyond last page
        for workflow i (we'll return an empty list for it).

        :param urls: List of workflow URLs.
        :param per_page: Number of items per page.
        :param page: Page number to fetch.
        :param api_base: Base URL for the API.
        :return: Tuple of final data and exhausted flags.
        """
        n = len(urls)
        afters: list[Optional[str]] = [None] * n
        exhausted: list[bool] = [False] * n

        if page <= 1:
            data = self.__fetch_multi__(
                urls, afters, per_page
            )
            logger.debug(f"Fetched data for page 1: {data}")
            return data, exhausted

        # Warm-up steps to move to `page-1`
        active_idx = list(range(n))
        for _ in range(page - 1):
            if not active_idx:
                break
            batch_urls = [urls[i] for i in active_idx]
            batch_afters = [afters[i] for i in active_idx]
            batch_data = self.__fetch_multi__(
                batch_urls, batch_afters, per_page
            )

            # Update cursors per active alias r0..rk within the batch
            new_active: list[int] = []
            for j, i in enumerate(active_idx):
                key = f"r{j}"
                res = (batch_data.get(key) or {})
                if not res or "runs" not in res:
                    exhausted[i] = True
                    continue
                page_info = (res["runs"] or {}).get("pageInfo") or {}
                end = page_info.get("endCursor")
                has_next = bool(page_info.get("hasNextPage"))
                afters[i] = end
                if has_next:
                    new_active.append(i)
                else:
                    exhausted[i] = True
            active_idx = new_active

        final_data = self.__fetch_multi__(
            urls, afters, per_page=per_page, page=page
        )
        return final_data, exhausted

    def fetch_workflows_runs_by_urls(
        self,
        urls: list[str],
        per_page: int = 100,
        page: int = 1,
        api_base: str = "https://api.github.com"
    ) -> dict[str, dict]:
        """
        Fetches workflow runs for multiple workflows.

        :param urls: List of workflow URLs.
        :param per_page: Number of items per page.
        :param page: Page number to fetch.
        :return: A dictionary mapping workflow URLs to their runs.
        """
        data, exhausted = self.__paginate_to_page__(urls, per_page, page)
        return normalize_batch_to_rest(urls, data, exhausted, api_base)
