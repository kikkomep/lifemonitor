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

from typing import List


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

FRAGMENTS = """
fragment RestLikeWorkflow on Workflow {
    databaseId
    name
    resourcePath
}

fragment RestLikeCheckSuite on CheckSuite {
    id
    databaseId
    status
    conclusion
    app {
        name
        slug
    }
    commit {
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

fragment RestLikeWorkflowRun on WorkflowRun {
    databaseId
    id
    url
    resourcePath
    runNumber
    createdAt
    updatedAt
    workflow {
        ...RestLikeWorkflow
    }
    checkSuite {
        ...RestLikeCheckSuite
    }
}
"""


def build_multi_resources_query(n: int) -> str:
    """Generate a single GraphQL query with n `resource(url: ...)` selections.
    Why: one round-trip can fetch many workflows.
    """
    defs: List[str] = ["$first: Int!"]
    fields: List[str] = []
    for i in range(n):
        defs.append(f"$u{i}: URI!")
        defs.append(f"$a{i}: String")  # cursor
        # Use placeholder replacement to avoid f-string brace escaping issues
        snippet = f"""  r{i}: resource(url: $u{i}) {{
    __typename
    ... on Workflow {{
            id
            databaseId
            name
            resourcePath
            url
            createdAt
            updatedAt
            runs(first: $first, orderBy: {{field: CREATED_AT, direction: DESC}}, after: $a{i}) {{
                nodes {{...RestLikeWorkflowRun}}
                pageInfo {{hasNextPage endCursor}}
            }}
        }}
    }}"""
        fields.append(snippet)
    defs_s = ", ".join(defs)
    fields_s = "\n".join(fields)

    return (
        FRAGMENTS + f"""
query MultiWorkflowRuns({defs_s}) {{
    rateLimit {{cost resetAt remaining used nodeCount}}
    viewer {{login}}
{fields_s}
}}
"""
    )
