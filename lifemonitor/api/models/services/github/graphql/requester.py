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

import logging
import time
from typing import Optional

import requests

from lifemonitor.cache import Timeout, cached

# set module level logger
logger = logging.getLogger(__name__)


class GraphQLRequester:

    # The endpoint for the GitHub GraphQL API.
    endpoint = "https://api.github.com/graphql"

    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token
        self._session = None

    def __repr__(self):
        return "<GraphQLRequester token=*******>"

    def __str__(self):
        return "GraphQLRequester(token=*******)"

    """
    A class to handle GraphQL requests to the GitHub API.
    """

    def __make_headers__(self, token: Optional[str] = None) -> dict:
        """
        Returns the headers required for GitHub GraphQL API requests.

        :param token: The personal access token for GitHub API authentication.
        :return: A dictionary containing the required headers.
        """
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @property
    def headers(self) -> dict:
        """
        Returns the headers for the GraphQL request, using the service's token.

        :return: A dictionary containing the headers.
        """
        return self.__make_headers__(self._token)

    @property
    def session(self) -> requests.Session:
        """
        Returns a requests session with the appropriate headers for the GraphQL API.

        :return: A requests.Session object with the required headers.
        """
        if not self._session:
            self.create_session()
        return self._session

    def create_session(self) -> requests.Session:
        """
        Creates a requests session with the appropriate headers for the GraphQL API.
        This method is called to initialize the session when needed.
        """
        if self._session:
            logger.warning("Session already exists, replacing it with a new one.")
            try:
                self._session.close()
            except Exception as e:
                logger.error("Error closing previous session: %s", e)
        # Create a new session with the headers
        session = requests.Session()
        session.headers.update(self.headers)
        logger.debug("Created new session for GitHub GraphQL API.")
        # Store the session in the instance variable
        self._session = session
        # Return the session for further use
        return self._session

    @cached(timeout=Timeout.BUILD, client_scope=False, transactional_update=True)
    def execute_query(self, query: str, variables: Optional[dict] = None,
                      max_retries: int = 3, retry_delay: int = 1) -> dict:
        """
        Executes a GraphQL query against the GitHub API.

        :param query: The GraphQL query string.
        :param variables: Optional variables for the query.
        :return: The response from the GitHub API as a dictionary.
        """

        # Start timing
        start_time = time.time()
        # Log the start of the query execution
        logger.info("Starting GraphQL query execution at %s", start_time)
        logger.debug("Executing Github GraphQL query: %s with variables: %s", query, variables)
        # Set up retry parameters
        retry_count = 0

        # Perform the request with retries
        while True:
            try:
                # Execute the query using the session
                response = self.session.post(
                    self.endpoint,
                    json={'query': query, 'variables': variables},
                    headers=self.headers
                )

                # If we get a 429 (Too Many Requests) or 5xx server error, retry
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if retry_count < max_retries:
                        retry_count += 1
                        wait_time = retry_delay * (2 ** (retry_count - 1))  # Exponential backoff
                        logger.warning(f"Request failed with status {response.status_code}. Retrying in {wait_time}s (attempt {retry_count}/{max_retries})")
                        time.sleep(wait_time)
                        continue

                # Break the loop if no retry needed or retries exhausted
                break

            except (requests.ConnectionError, requests.Timeout) as e:
                # Network-related errors
                if retry_count < max_retries:
                    retry_count += 1
                    wait_time = retry_delay * (2 ** (retry_count - 1))
                    logger.warning(f"Request failed with error: {str(e)}. Retrying in {wait_time}s (attempt {retry_count}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {max_retries} retries: {str(e)}")
                    raise

        # End timing
        execution_time = time.time() - start_time
        logger.info("GraphQL query execution completed in %.2f seconds", execution_time)

        # Check the response status
        logger.debug("GraphQL query response status: %s", response.status_code)
        logger.debug("GraphQL query response headers: %s", response.headers)
        if response.status_code != 200:
            logger.error("GraphQL query failed with status code %s: %s", response.status_code, response.text)
            response.raise_for_status()
        # Parse the response JSON
        data = response.json()
        # Check for errors in the response
        if 'errors' in data:
            raise Exception(f"GraphQL query failed: {data['errors']}")
        if 'data' not in data:
            raise Exception("GraphQL query returned no data")
        # Add execution time to the data for debugging purposes
        data["data"]["execution_time"] = execution_time
        # Return the parsed data
        return data
