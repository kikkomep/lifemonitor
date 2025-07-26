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

from datetime import datetime
from typing import Optional

from lifemonitor.cache import CacheMixin, cache


class GhWorkflow(CacheMixin):
    """
    Represents a GitHub workflow.
    This class provides methods to access workflow details and associated runs.
    It also provides methods to save and load workflows from the cache.
    The workflow is initialized with raw data from the GitHub GraphQL API.
    """

    def __init__(self, raw_data: dict) -> None:
        self._raw_data = raw_data
        self.__runs_map__ = None

    def __repr__(self) -> str:
        return f"<GhWorkflow id={self.id}, name={self.name}, url={self.url}>"

    def __str__(self) -> str:
        return f"GhWorkflow(id={self.id}, name={self.name}, url={self.url})"

    @property
    def raw_data(self) -> dict:
        """
        Returns the raw data of the workflow.
        """
        return self._raw_data

    @property
    def id(self) -> str:
        return self._raw_data["id"]

    @property
    def name(self) -> str:
        return self._raw_data["name"]

    @property
    def resource_path(self) -> str:
        return self._raw_data["resourcePath"]

    @property
    def url(self) -> str:
        return self._raw_data["url"]

    @property
    def runs_map(self) -> dict:
        """
        Returns a dictionary mapping run IDs to GhWorkflowRun objects.
        This allows for quick access to runs by their ID.
        """
        if self.__runs_map__ is None:
            if "runs" not in self._raw_data or \
                    "nodes" not in self._raw_data["runs"] and not isinstance(self._raw_data["runs"]["nodes"], list):
                self.__runs_map__ = {}
            else:
                # Create a map of run IDs to GhWorkflowRun objects
                # This assumes that each run in the raw data has a unique ID
                # and that the raw data is structured correctly.
                self.__runs_map__ = {run["id"]: GhWorkflowRun(self, run)
                                     for run in self._raw_data["runs"]["nodes"] if run}
        return self.__runs_map__

    @classmethod
    def from_raw_data(cls, raw_data: dict) -> GhWorkflow:
        """
        Creates a GhWorkflow instance from raw data.
        """
        return cls(raw_data)

    @property
    def runs(self) -> list:
        """
        Returns a list of workflow runs associated with this workflow.
        Each run is represented as a GhWorkflowRun object.
        """
        return list(self.runs_map.values())

    def get_run_by_id(self, run_id: str) -> Optional[GhWorkflowRun]:
        """
        Returns a workflow run by its ID.
        """
        return self.runs_map.get(run_id)

    def save(self) -> None:
        """
        Saves the workflow to the cache.
        This method is a placeholder for any caching logic you might want to implement.
        """
        with self.cache.transaction(force_update=True)as transaction:
            # transaction.set(self.id, self.raw_data, timeout=None)
            # transaction.set(self.resource_path.raw_data, self, timeout=None)
            transaction.set(self.url, self.raw_data, timeout=None)

    @classmethod
    def load(cls, url: str) -> Optional[GhWorkflow]:
        """
        Loads a GhWorkflow from the cache using its URL.
        Returns None if the workflow is not found in the cache.
        """
        raw_data = cache.get(url)
        if raw_data:
            return cls.from_raw_data(raw_data)
        return None


class GhWorkflowRun:

    """
    Represents a run of a GitHub workflow.
    This class provides methods to access run details such as status, conclusion,
    associated commit, branch, and other metadata.
    """

    def __init__(self, workflow: GhWorkflow, raw_data: dict) -> None:
        self._workflow = workflow
        self._raw_data = raw_data

    def __repr__(self) -> str:
        return f"<GhWorkflowRun id={self.id}, run_number={self.run_number}, url={self.url}>"

    def __str__(self) -> str:
        return f"GhWorkflowRun(id={self.id}, run_number={self.run_number}, url={self.url})"

    @property
    def workflow(self) -> GhWorkflow:
        """
        Returns the workflow associated with this run.
        """
        return self._workflow

    @property
    def raw_data(self) -> dict:
        """
        Returns the raw data of the workflow run.
        """
        return self._raw_data

    @property
    def id(self) -> str:
        return self._raw_data["id"]

    @property
    def run_number(self) -> int:
        return self._raw_data["runNumber"]

    @property
    def created_at(self) -> datetime:
        return datetime.fromisoformat(self._raw_data["createdAt"].replace("Z", "+00:00"))

    @property
    def updated_at(self) -> datetime:
        return datetime.fromisoformat(self._raw_data["updatedAt"].replace("Z", "+00:00"))

    @property
    def status(self) -> str:
        return self._raw_data["checkSuite"]["status"].lower()

    @property
    def conclusion(self) -> str:
        return self._raw_data["checkSuite"]["conclusion"].lower()

    @property
    def ref_name(self) -> str:
        return self._raw_data["checkSuite"]["branch"]["name"]

    @property
    def ref_prefix(self) -> str:
        return self._raw_data["checkSuite"]["branch"]["prefix"]

    @property
    def revision(self) -> str:
        return self._raw_data["checkSuite"]["commit"]["oid"]

    @property
    def url(self) -> str:
        return self._raw_data["url"]

    @property
    def resource_path(self) -> str:
        return self._raw_data["resourcePath"]
