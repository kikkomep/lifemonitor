import json
import redis
import time
import logging
from datetime import datetime
import redis_lock  # python-redis-lock library

from lifemonitor.cache import cache


# Basic logger configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def iso_to_epoch(timestamp_iso):
    dt = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
    return int(dt.timestamp())


class RunCache:
    def __init__(self):
        self.redis_client = cache.get_backend()

    def _acquire_lock(self, lock_name, timeout=10):
        return redis_lock.Lock(self.redis_client, lock_name, expire=timeout, auto_renewal=True)

    # --- Write Operations with optional locking ---

    def insert_update_run(self, workflow_id, run_id, ref, metadata, use_lock=False, pipe=None):
        """
        Atomically insert or update a single run.
        Accepts a shared Redis pipeline for cross-cache transactions.
        """
        lock = None
        created_here = False
        if use_lock:
            lock_name = f"lock:{workflow_id}:run:{run_id}"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error(f"Failed to acquire lock for run {run_id}")
                return False
        try:
            created_at_iso = metadata.get("created_at")
            score = iso_to_epoch(created_at_iso) if created_at_iso else int(time.time())
            run_key = f"workflow:{workflow_id}:run:{run_id}"

            if pipe is None:
                pipe = self.redis_client.pipeline(transaction=True)
                created_here = True

            pipe.set(run_key, json.dumps(metadata))
            pipe.zadd(f"workflow:{workflow_id}:runs", {run_id: score})
            pipe.zadd(f"workflow:{workflow_id}:ref:{ref}:runs", {run_id: score})

            if created_here:
                pipe.execute()
            logger.debug(f"Run {run_id} inserted/updated with locking={use_lock}.")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis error inserting/updating run {run_id}: {e}")
            return False
        finally:
            if lock:
                lock.release()

    def delete_run(self, workflow_id, run_id, ref, use_lock=False, pipe=None):
        lock = None
        created_here = False
        if use_lock:
            lock_name = f"lock:{workflow_id}:run:{run_id}"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error(f"Failed to acquire lock for run {run_id}")
                return False
        try:
            run_key = f"workflow:{workflow_id}:run:{run_id}"

            if pipe is None:
                pipe = self.redis_client.pipeline(transaction=True)
                created_here = True

            pipe.delete(run_key)
            pipe.zrem(f"workflow:{workflow_id}:runs", run_id)
            pipe.zrem(f"workflow:{workflow_id}:ref:{ref}:runs", run_id)

            if created_here:
                pipe.execute()
            logger.debug(f"Run {run_id} deleted with locking={use_lock}.")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis error deleting run {run_id}: {e}")
            return False
        finally:
            if lock:
                lock.release()

    def batch_insert_update_runs(self, workflow_id, runs, use_lock=False, pipe=None, max_retry=3):
        lock = None
        if use_lock:
            lock_name = f"lock:{workflow_id}:batch_update"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error(f"Failed to acquire lock for batch update in workflow {workflow_id}")
                return False
        try:
            for attempt in range(max_retry):
                created_here = False
                try:
                    if pipe is None:
                        pipe = self.redis_client.pipeline(transaction=True)
                        created_here = True
                    for run in runs:
                        run_id = run['run_id']
                        ref = run['ref']
                        metadata = run['metadata']
                        created_at_iso = metadata.get("created_at")
                        score = iso_to_epoch(created_at_iso) if created_at_iso else int(time.time())
                        run_key = f"workflow:{workflow_id}:run:{run_id}"
                        pipe.set(run_key, json.dumps(metadata))
                        pipe.zadd(f"workflow:{workflow_id}:runs", {run_id: score})
                        pipe.zadd(f"workflow:{workflow_id}:ref:{ref}:runs", {run_id: score})
                    if created_here:
                        pipe.execute()
                    logger.debug(f"Batch runs inserted/updated on attempt {attempt + 1}.")
                    return True
                except redis.exceptions.RedisError as e:
                    logger.exception(e)
                    logger.error(f"Retry {attempt + 1} for batch insert/update: {e}")
                    time.sleep(0.2 * (attempt + 1))
            logger.error(f"Batch insert/update failed after {max_retry} attempts.")
            return False
        except Exception as e:
            logger.exception(e)
        finally:
            if lock:
                lock.release()

    def batch_delete_runs(self, workflow_id, runs, use_lock=False, pipe=None, max_retry=3):
        lock = None
        if use_lock:
            lock_name = f"lock:{workflow_id}:batch_delete"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error(f"Failed to acquire lock for batch delete in workflow {workflow_id}")
                return False
        try:
            for attempt in range(max_retry):
                created_here = False
                try:
                    if pipe is None:
                        pipe = self.redis_client.pipeline(transaction=True)
                        created_here = True
                    for run in runs:
                        run_id = run['run_id']
                        ref = run['ref']
                        run_key = f"workflow:{workflow_id}:run:{run_id}"
                        pipe.delete(run_key)
                        pipe.zrem(f"workflow:{workflow_id}:runs", run_id)
                        pipe.zrem(f"workflow:{workflow_id}:ref:{ref}:runs", run_id)
                    if created_here:
                        pipe.execute()
                    logger.debug(f"Batch runs deleted on attempt {attempt + 1}.")
                    return True
                except redis.exceptions.RedisError as e:
                    logger.error(f"Retry {attempt + 1} for batch delete: {e}")
                    time.sleep(0.2 * (attempt + 1))
            logger.error(f"Batch delete failed after {max_retry} attempts.")
            return False
        finally:
            if lock:
                lock.release()

    # --- Read Operations (no locking) ---

    @staticmethod
    def __decode_result__(result: str) -> dict:
        try:
            if not result:
                return None
            if isinstance(result, list):
                return [json.loads(item) for item in result]
            return json.loads(result)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON result: {e}")
            return None

    def get_run(self, workflow_id, run_id):
        """
        Retrieve full metadata of a single run by workflow_id and run_id.
        Returns a dictionary with run data or empty dict if not found/error.
        """
        run_key = f"workflow:{workflow_id}:run:{run_id}"
        try:
            return self.__decode_result__(self.redis_client.get(run_key))
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis error retrieving run {run_id} for workflow {workflow_id}: {e}")
            return None

    def get_runs_by_ids(self, workflow_id, run_ids):
        """
        Retrieve full metadata for each run ID in the list for the given workflow.
        Returns a list of dicts with run data.
        """
        if not run_ids:
            return []
        pipe = self.redis_client.pipeline()
        for run_id in run_ids:
            key = f"workflow:{workflow_id}:run:{run_id}"
            pipe.get(key)
        data = pipe.execute()
        logger.debug(f"Retrieved {len(data)} runs for workflow {workflow_id}.")
        return self.__decode_result__(data)

    def get_latest_runs(self, workflow_id, ref=None, n=10):
        """
        Retrieve last n runs by descending creation date for a workflow or ref.
        """
        if ref:
            key = f"workflow:{workflow_id}:ref:{ref}:runs"
        else:
            key = f"workflow:{workflow_id}:runs"

        try:
            run_ids = self.redis_client.zrevrange(key, 0, n - 1)
            pipe = self.redis_client.pipeline()
            for run_id in run_ids:
                pipe.get(f"workflow:{workflow_id}:run:{run_id}")
            return self.__decode_result__(pipe.execute())
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis error retrieving runs: {e}")
            return None

    def get_runs_by_date_range(self, workflow_id, ref=None, start_iso=None, end_iso=None, limit=100):
        """
        Retrieve runs with creation date between start_iso and end_iso (ISO format).
        """
        if ref:
            key = f"workflow:{workflow_id}:ref:{ref}:runs"
        else:
            key = f"workflow:{workflow_id}:runs"

        min_score = iso_to_epoch(start_iso) if start_iso else "-inf"
        max_score = iso_to_epoch(end_iso) if end_iso else "+inf"

        try:
            run_ids = self.redis_client.zrangebyscore(key, min_score, max_score, start=0, num=limit)
            pipe = self.redis_client.pipeline()
            for run_id in run_ids:
                pipe.get(f"workflow:{workflow_id}:run:{run_id}")
            return self.__decode_result__(pipe.execute())
        except redis.exceptions.RedisError as e:
            logger.error(f"Redis error retrieving runs by date range: {e}")
            return None
