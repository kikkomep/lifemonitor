import json
import redis
import time
import logging
from datetime import datetime
import redis_lock
from lifemonitor.api.models.services.github.run_cache import RunCache
from lifemonitor.cache import cache

# Basic logger configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def iso_to_epoch(timestamp_iso):
    dt = datetime.fromisoformat(timestamp_iso.replace("Z", "+00:00"))
    return int(dt.timestamp())


class TestInstanceCache:
    def __init__(self):
        self.redis_client = cache.get_backend()
        self.run_cache = RunCache()

    def _acquire_lock(self, lock_name, timeout=10):
        return redis_lock.Lock(self.redis_client, lock_name, expire=timeout, auto_renewal=True)

    def set_update_timestamp(self, test_instance_id, pipe=None):
        """
        Set the current time.time() as last update timestamp for the test instance.
        """
        key = f"testinstance:{test_instance_id}:last_update"
        try:
            timestamp = time.time()
            if pipe is not None:
                pipe.set(key, timestamp)
            else:
                self.redis_client.set(key, timestamp)
            logger.debug(f"Set last_update={timestamp} for test instance {test_instance_id}")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Error setting update timestamp for test instance {test_instance_id}: {e}")
            return False

    def get_update_timestamp(self, test_instance_id):
        """
        Retrieve the last update timestamp of the test instance as float or None if not set.
        """
        key = f"testinstance:{test_instance_id}:last_update"
        try:
            val = self.redis_client.get(key)
            return float(val) if val is not None else None
        except (redis.exceptions.RedisError, ValueError) as e:
            logger.error(f"Error retrieving update timestamp for test instance {test_instance_id}: {e}")
            return None

    # --- Single run operations ---

    def associate_run(self, test_instance_id, run_id, ref=None, created_at_iso=None, use_lock=False):
        lock = None
        if use_lock:
            lock_name = f"lock:testinstance:{test_instance_id}:run:{run_id}"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error(f"Failed to acquire lock for associating run {run_id} in test instance {test_instance_id}")
                return False
        try:
            pipe = self.redis_client.pipeline(transaction=True)
            if ref:
                pipe.sadd(f"testinstance:{test_instance_id}:ref:{ref}:runs", run_id)
            score = iso_to_epoch(created_at_iso) if created_at_iso else int(time.time())
            pipe.zadd(f"testinstance:{test_instance_id}:runs_by_date", {run_id: score})
            # Update the last update timestamp
            self.set_update_timestamp(test_instance_id, pipe=pipe)
            pipe.execute()
            logger.debug(f"Run {run_id} associated to test instance {test_instance_id} with locking={use_lock}")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Error associating run {run_id} to test instance {test_instance_id}: {e}")
            return False
        finally:
            if lock:
                lock.release()

    def disassociate_run(self, test_instance_id, run_id, ref=None, use_lock=False):
        lock = None
        if use_lock:
            lock_name = f"lock:testinstance:{test_instance_id}:run:{run_id}"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error(f"Failed to acquire lock for disassociating run {run_id} from test instance {test_instance_id}")
                return False
        try:
            pipe = self.redis_client.pipeline(transaction=True)
            if ref:
                pipe.srem(f"testinstance:{test_instance_id}:ref:{ref}:runs", run_id)
            pipe.zrem(f"testinstance:{test_instance_id}:runs_by_date", run_id)
            self.set_update_timestamp(test_instance_id, pipe=pipe)
            pipe.execute()
            logger.debug(f"Run {run_id} disassociated from test instance {test_instance_id} with locking={use_lock}")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Error disassociating run {run_id} from test instance {test_instance_id}: {e}")
            return False
        finally:
            if lock:
                lock.release()

    # --- Batch operations ---

    def batch_associate_runs(self, test_instance_id, runs, use_lock=False, max_retry=3):
        lock = None
        if use_lock:
            lock_name = f"lock:testinstance:{test_instance_id}:batch_associate"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error(f"Failed to acquire lock for batch associate in test instance {test_instance_id}")
                return False
        try:
            for attempt in range(max_retry):
                try:
                    pipe = self.redis_client.pipeline(transaction=True)
                    for run in runs:
                        run_id = run['run_id']
                        ref = run.get('ref')
                        created_at_iso = run.get('created_at')
                        if ref:
                            pipe.sadd(f"testinstance:{test_instance_id}:ref:{ref}:runs", run_id)
                        score = iso_to_epoch(created_at_iso) if created_at_iso else int(time.time())
                        pipe.zadd(f"testinstance:{test_instance_id}:runs_by_date", {run_id: score})
                    self.set_update_timestamp(test_instance_id, pipe=pipe)
                    pipe.execute()
                    logger.debug(f"Batch runs associated to test instance {test_instance_id} at attempt {attempt + 1}")
                    return True
                except redis.exceptions.RedisError as e:
                    logger.error(f"Retry {attempt + 1} for batch associate: {e}")
                    time.sleep(0.2 * (attempt + 1))
            logger.error(f"Batch associate failed after {max_retry} attempts.")
            return False
        finally:
            if lock:
                lock.release()

    def batch_disassociate_runs(self, test_instance_id, runs, use_lock=False, max_retry=3):
        lock = None
        if use_lock:
            lock_name = f"lock:testinstance:{test_instance_id}:batch_disassociate"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error(f"Failed to acquire lock for batch disassociate in test instance {test_instance_id}")
                return False
        try:
            for attempt in range(max_retry):
                try:
                    pipe = self.redis_client.pipeline(transaction=True)
                    for run in runs:
                        run_id = run['run_id']
                        ref = run.get('ref')
                        if ref:
                            pipe.srem(f"testinstance:{test_instance_id}:ref:{ref}:runs", run_id)
                        pipe.zrem(f"testinstance:{test_instance_id}:runs_by_date", run_id)
                    self.set_update_timestamp(test_instance_id, pipe=pipe)
                    pipe.execute()
                    logger.debug(f"Batch runs disassociated from test instance {test_instance_id} at attempt {attempt + 1}")
                    return True
                except redis.exceptions.RedisError as e:
                    logger.error(f"Retry {attempt + 1} for batch disassociate: {e}")
                    time.sleep(0.2 * (attempt + 1))
            logger.error(f"Batch disassociate failed after {max_retry} attempts.")
            return False
        finally:
            if lock:
                lock.release()

    # --- Query methods ---

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

    def get_run_ids_by_ref(self, test_instance_id, ref):
        try:
            run_ids = self.redis_client.smembers(f"testinstance:{test_instance_id}:ref:{ref}:runs")
            # return list(run_ids)
            return self.__decode_result__(list(run_ids))
        except redis.exceptions.RedisError as e:
            logger.error(f"Error retrieving runs by ref {ref} for test instance {test_instance_id}: {e}")
            return []

    def get_run_ids_by_date_range(self, test_instance_id, start_iso=None, end_iso=None, limit=100):
        try:
            min_score = iso_to_epoch(start_iso) if start_iso else "-inf"
            max_score = iso_to_epoch(end_iso) if end_iso else "+inf"
            run_ids = self.redis_client.zrangebyscore(
                f"testinstance:{test_instance_id}:runs_by_date",
                min_score,
                max_score,
                start=0,
                num=limit
            )
            return self.__decode_result__(run_ids)
        except redis.exceptions.RedisError as e:
            logger.error(f"Error retrieving runs by date range for test instance {test_instance_id}: {e}")
            return []

    def get_all_refs(self, test_instance_id):
        try:
            keys = self.redis_client.keys(f"testinstance:{test_instance_id}:ref:*:runs")
            refs = [k.split(":")[3] for k in keys]
            return refs
        except redis.exceptions.RedisError as e:
            logger.error(f"Error listing refs for test instance {test_instance_id}: {e}")
            return []

    # --- Ordered retrieval by date ---

    def get_run_ids_ordered_by_date(self, test_instance_id, ascending=True, start_iso=None, end_iso=None, limit=100):
        try:
            min_score = iso_to_epoch(start_iso) if start_iso else "-inf"
            max_score = iso_to_epoch(end_iso) if end_iso else "+inf"
            zset_key = f"testinstance:{test_instance_id}:runs_by_date"
            if ascending:
                run_ids = self.redis_client.zrangebyscore(zset_key, min_score, max_score, start=0, num=limit)
            else:
                run_ids = self.redis_client.zrevrangebyscore(zset_key, max_score, min_score, start=0, num=limit)
            return self.__decode_result__(run_ids)
        except redis.exceptions.RedisError as e:
            logger.error(f"Error retrieving runs ordered by date for test instance {test_instance_id}: {e}")
            return []

    def get_latest_run_ids(self, test_instance_id, limit=100):
        return self.get_run_ids_ordered_by_date(test_instance_id, ascending=False, limit=limit)

    # --- Getters full runs ---

    def get_run_by_id(self, workflow_id, run_id):
        return self.run_cache.get_run(workflow_id, run_id)

    def get_run_by_ref(self, test_instance_id, ref, workflow_id):
        run_ids = self.get_run_ids_by_ref(test_instance_id, ref)
        if not run_ids:
            return []
        return self.run_cache.get_runs_by_ids(workflow_id, run_ids)

    def get_runs_by_date_range(self, test_instance_id, workflow_id, start_iso=None, end_iso=None, limit=100):
        run_ids = self.get_run_ids_by_date_range(test_instance_id, start_iso, end_iso, limit)
        if not run_ids:
            return []
        return self.run_cache.get_runs_by_ids(workflow_id, run_ids)

    def get_runs_ordered_by_date(self, test_instance_id, workflow_id, ascending=True, start_iso=None, end_iso=None, limit=100):
        run_ids = self.get_run_ids_ordered_by_date(test_instance_id, ascending, start_iso, end_iso, limit)
        if not run_ids:
            return []
        return self.run_cache.get_runs_by_ids(workflow_id, run_ids)

    def get_latest_runs(self, test_instance_id, workflow_id, limit=10):
        run_ids = self.get_latest_run_ids(test_instance_id, limit)
        if not run_ids:
            return []
        logger.debug("RUN IDS: %r", run_ids)
        return self.run_cache.get_runs_by_ids(workflow_id, run_ids)

    # --- Atomic cross-cache operations without needing RunCache argument ---

    def associate_and_insert_run(self, test_instance_id, workflow_id, run_id, ref, metadata, use_lock=False):
        return self._associate_and_insert_run_internal(test_instance_id, workflow_id, run_id, ref, metadata, use_lock)

    def batch_associate_and_insert_runs(self, test_instance_id, workflow_id, runs, use_lock=False, max_retry=3):
        return self._batch_associate_and_insert_runs_internal(test_instance_id, workflow_id, runs, use_lock, max_retry)

    def disassociate_and_delete_run(self, test_instance_id, workflow_id, run_id, ref, use_lock=False):
        return self._disassociate_and_delete_run_internal(test_instance_id, workflow_id, run_id, ref, use_lock)

    def batch_disassociate_and_delete_runs(self, test_instance_id, workflow_id, runs, use_lock=False, max_retry=3):
        return self._batch_disassociate_and_delete_runs_internal(test_instance_id, workflow_id, runs, use_lock, max_retry)

    # --- Internal implementations using self.run_cache ---

    def _associate_and_insert_run_internal(self, test_instance_id, workflow_id, run_id, ref, metadata, use_lock):
        lock = None
        if use_lock:
            lock_name = f"lock:testinstance:{test_instance_id}:run:{run_id}"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error("Failed to acquire transaction lock.")
                return False
        try:
            pipe = self.redis_client.pipeline(transaction=True)
            success = self.run_cache.insert_update_run(workflow_id, run_id, ref, metadata, use_lock=False, pipe=pipe)
            if not success:
                return False
            if ref:
                pipe.sadd(f"testinstance:{test_instance_id}:ref:{ref}:runs", run_id)
            created_at_iso = metadata.get("created_at")
            score = iso_to_epoch(created_at_iso) if created_at_iso else int(time.time())
            pipe.zadd(f"testinstance:{test_instance_id}:runs_by_date", {run_id: score})
            self.set_update_timestamp(test_instance_id, pipe=pipe)
            pipe.execute()
            logger.debug(f"Run {run_id} inserted in workflow and associated to testinstance {test_instance_id} atomically.")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Atomic associate and insert failed for run {run_id}: {e}")
            return False
        finally:
            if lock:
                lock.release()

    def _batch_associate_and_insert_runs_internal(self, test_instance_id, workflow_id, runs, use_lock, max_retry):
        lock = None
        if use_lock:
            lock_name = f"lock:testinstance:{test_instance_id}:batch_associate_and_insert"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error("Failed to acquire batch transaction lock.")
                return False
        try:
            for attempt in range(max_retry):
                try:
                    pipe = self.redis_client.pipeline(transaction=True)
                    success = self.run_cache.batch_insert_update_runs(workflow_id, runs, use_lock=False, pipe=pipe, max_retry=1)
                    if not success:
                        raise redis.exceptions.RedisError("Failed RunCache batch insert/update")
                    for run in runs:
                        run_id = run['run_id']
                        ref = run.get('ref')
                        created_at_iso = None
                        if 'metadata' in run and 'created_at' in run['metadata']:
                            created_at_iso = run['metadata']['created_at']
                        created_at_iso = run.get('created_at', created_at_iso)
                        if ref:
                            pipe.sadd(f"testinstance:{test_instance_id}:ref:{ref}:runs", run_id)
                        score = iso_to_epoch(created_at_iso) if created_at_iso else int(time.time())
                        pipe.zadd(f"testinstance:{test_instance_id}:runs_by_date", {run_id: score})
                    self.set_update_timestamp(test_instance_id, pipe=pipe)
                    pipe.execute(raise_on_error=True)
                    logger.debug(f"Batch runs inserted and associated atomically on attempt {attempt + 1}.")
                    return True
                except redis.exceptions.RedisError as e:
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.exception(e)
                    logger.error(f"Retry {attempt + 1} for batch associate and insert: {e}")
                    time.sleep(0.2 * (attempt + 1))
            logger.error(f"Batch associate and insert failed after {max_retry} attempts.")
            return False
        finally:
            if lock:
                lock.release()

    def _disassociate_and_delete_run_internal(self, test_instance_id, workflow_id, run_id, ref, use_lock):
        lock = None
        if use_lock:
            lock_name = f"lock:testinstance:{test_instance_id}:run:{run_id}"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error("Failed to acquire transaction lock.")
                return False
        try:
            pipe = self.redis_client.pipeline(transaction=True)
            success = self.run_cache.delete_run(workflow_id, run_id, ref, use_lock=False, pipe=pipe)
            if not success:
                return False
            pipe.srem(f"testinstance:{test_instance_id}:ref:{ref}:runs", run_id)
            pipe.zrem(f"testinstance:{test_instance_id}:runs_by_date", run_id)
            self.set_update_timestamp(test_instance_id, pipe=pipe)
            pipe.execute()
            logger.debug(f"Run {run_id} deleted and disassociated atomically.")
            return True
        except redis.exceptions.RedisError as e:
            logger.error(f"Atomic disassociate and delete failed for run {run_id}: {e}")
            return False
        finally:
            if lock:
                lock.release()

    def _batch_disassociate_and_delete_runs_internal(self, test_instance_id, workflow_id, runs, use_lock, max_retry):
        lock = None
        if use_lock:
            lock_name = f"lock:testinstance:{test_instance_id}:batch_disassociate_and_delete"
            lock = self._acquire_lock(lock_name)
            if not lock.acquire(blocking=True, timeout=5):
                logger.error("Failed to acquire batch transaction lock.")
                return False
        try:
            for attempt in range(max_retry):
                try:
                    pipe = self.redis_client.pipeline(transaction=True)
                    success = self.run_cache.batch_delete_runs(workflow_id, runs, use_lock=False, pipe=pipe, max_retry=1)
                    if not success:
                        raise redis.exceptions.RedisError("Failed RunCache batch delete")
                    for run in runs:
                        run_id = run['run_id']
                        ref = run['ref']
                        pipe.srem(f"testinstance:{test_instance_id}:ref:{ref}:runs", run_id)
                        pipe.zrem(f"testinstance:{test_instance_id}:runs_by_date", run_id)
                    self.set_update_timestamp(test_instance_id, pipe=pipe)
                    pipe.execute()
                    logger.debug(f"Batch runs deleted and disassociated atomically on attempt {attempt + 1}.")
                    return True
                except redis.exceptions.RedisError as e:
                    logger.error(f"Retry {attempt + 1} for batch disassociate and delete: {e}")
                    time.sleep(0.2 * (attempt + 1))
            logger.error(f"Batch disassociate and delete failed after {max_retry} attempts.")
            return False
        finally:
            if lock:
                lock.release()
