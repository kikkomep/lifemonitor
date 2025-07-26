import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

import lifemonitor.api.models as models
from lifemonitor.api.models.services.github.graphql.models import GhWorkflow
from lifemonitor.api.models.services.github.test_build import GithubTestBuild
from lifemonitor.cache import CacheMixin, Timeout, cache

# Initialize logger
logger = logging.getLogger(__name__)


class TestInstanceCacheManager(CacheMixin):

    def __init__(self, instance: models.TestInstance):
        self._instance = instance
        assert isinstance(self._instance, models.TestInstance), \
            "instance must be a TestInstance"
        # Cache for the test instance data
        self.__instance_cache__: dict = None

    @property
    def _instance_cache_(self) -> Optional[dict]:
        """
        Get the cached data for the test instance.
        """
        if self.__instance_cache__ is None:
            logger.debug("Loading cache for test instance %s", self.cache_key)
            self.__instance_cache__ = self.load()
        return self.__instance_cache__

    def __repr__(self):
        return f"<TestInstanceCacheManager instance={self._instance.id}>"

    def __str__(self):
        return f"TestInstanceCacheManager(instance={self._instance.id})"

    @property
    def cache_key(self) -> str:
        """
        Get the cache key for the test instance.
        This is used to store and retrieve the cache from the cache service.
        """
        return str(self._instance.uuid)

    @property
    def test_instance(self) -> models.TestInstance:
        """
        Get the test instance associated with this cache manager.
        """
        return self._instance

    @property
    def updated_at(self) -> Optional[datetime]:
        """
        Get the last update time of the cache for the test instance.
        Returns None if the cache is not available.
        """
        if self.is_valid():
            return self._instance_cache_.get('updated_at')
        return None

    def get(self, key: str) -> Optional[Any]:
        """
        Get the value from the cache for the given key.
        """
        if self.is_valid():
            return self._instance_cache_.get(key)
        return None

    def set(self, key: str, value: Any) -> None:
        """
        Set the value in the cache for the given key.
        """
        self._instance_cache_[key] = value

    def get_test_builds(self, limit: int = 10) -> List[GithubTestBuild]:
        """
        Get the test builds from the cache for the test instance.
        If the cache is not available, returns an empty list.
        """
        if self.is_valid():
            builds = self._instance_cache_.get('builds', {})
            logger.debug("Returning %d cached test builds for test instance %s", len(builds), self._instance)
            return list(builds.values())[:limit]
        logger.debug("No valid cache found for test instance %s", self._instance)
        return []

    def get_test_build(self, build_number: str) -> Optional[GithubTestBuild]:
        """
        Get a specific test build from the cache for the test instance.
        If the cache is not available, returns None.
        """
        if self.is_valid():
            builds = self._instance_cache_.get('builds', {})
            logger.debug("Searching for test build %r in cached builds", build_number)
            return builds.get(build_number)
        logger.debug("No valid cache found for test instance %s", self._instance)
        return None

    def is_valid(self) -> bool:
        """
        Check if the cache is available for the test instance.
        """
        return self._instance_cache_ and self._instance_cache_.get('valid', False)

    def load(self) -> Optional[dict]:
        """
        Load the cache for the test instance.
        Returns None if the cache is not available.
        """
        cached_data = cache.get(self.cache_key)
        if cached_data:
            logger.debug("Cache found for test instance %s", self._instance)
            return cached_data
        logger.debug("No cache found for test instance %s", self._instance)
        return {}

    def invalidate(self) -> None:
        """
        Invalidate the cache for the test instance.
        This will force the cache to be reloaded next time it is accessed.
        """
        logger.debug("Invalidating cache for test instance %s", self._instance)
        with cache.transaction(name=self.cache_key, force_update=True) as t:
            t.delete(self.cache_key)
        # Clear the local cache
        self.__instance_cache__ = None

    def update(self, gh_workflow: GhWorkflow, instance_builds: dict[str, models.TestBuild]) -> None:
        """
        Update the cache with the given data.
        This will merge the new data with the existing cache.
        """

        assert isinstance(gh_workflow, GhWorkflow), \
            "gh_workflow must be an instance of GhWorkflow"
        assert gh_workflow.url == self.test_instance.external_link, \
            "gh_workflow URL must match the test instance external link"

        data = {
            'id': self.cache_key,
            'updated_at': datetime.now(tz=timezone.utc),
            'valid': True,
            'builds': instance_builds
        }

        logger.debug("Data to be cached for test instance %s: %s", self.cache_key, data)
        with cache.transaction() as t:
            t.set(self.cache_key, data, timeout=Timeout.NONE)
        logger.debug("Updating cache for test instance %s with data: %s", self.cache_key, gh_workflow)
