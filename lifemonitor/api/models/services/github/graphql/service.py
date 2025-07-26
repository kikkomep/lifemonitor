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

import json
import logging
from typing import Optional

from .models import GhWorkflow
from .queries import build_workflows_info_query, get_rate_limit
from .requester import GraphQLRequester

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

    def get_workflows_by_url(self, urls: list[str]) -> list[GhWorkflow]:
        """
        Fetches workflows by their URLs.

        :param workflows_urls: A list of workflow URLs.
        :return: A list of GhWorkflow objects.
        """
        query = build_workflows_info_query(urls)
        logger.debug(query)

        result = self.requester.execute_query(query)
        logger.debug(json.dumps(result, indent=2))

        workflows = []
        if 'data' in result:
            logger.debug(f"Found {len(result['data'])} workflows in the response: {result['data']}")
            for key, data in result['data'].items():
                logger.debug(f"Processing workflow data for key: {key}: {data}")
                if not data:
                    logger.debug(f"No data found for key: {key}, skipping...")
                    continue
                if isinstance(data, dict) and 'id' in data:
                    workflows.append(GhWorkflow(data))
        return workflows
