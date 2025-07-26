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

# Query to get the rate limit status of the GitHub API.
# This query retrieves the limit, cost, remaining requests, and reset time.


get_rate_limit = """
query GetRateLimit {
    rateLimit {
        limit
        cost
        remaining
        resetAt
    }
}
"""


workflow_info_fragment = """
fragment WorkflowInfo on Workflow {
    id
    name
    resourcePath
    url
    createdAt
    updatedAt
    runs(first: 10, orderBy: {field: CREATED_AT, direction: DESC}) {
        nodes {
            id
            url
            resourcePath
            runNumber
            createdAt
            updatedAt
            checkSuite {
                id
                createdAt
                updatedAt
                status
                conclusion
                app {
                    name
                    slug
                }
                commit {
                    id
                    oid
                    message
                    committedDate
                    author {
                        name
                        email
                    }
                }
                branch {
                    name
                    prefix
                }
            }
        }
    }
}
"""


def build_workflows_info_query(workflow_urls: list[str]) -> str:
    """
    Build a GraphQL query to retrieve workflow information for a list of workflow URLs.
    """
    subqueries = []
    for i, url in enumerate(workflow_urls):
        alias = f"q{i + 1}"
        subquery = f"{alias}: resource(url: \"{url}\") {{ ...WorkflowInfo }}\n{' '*3}"
        subqueries.append(subquery)

    graphql_query = workflow_info_fragment + f"""
query {{
    rateLimit {{
        cost
        resetAt
        remaining
        used
        nodeCount
    }}
    viewer {{
        login
    }}
    {' '.join(subqueries)}
}}
"""
    return graphql_query
