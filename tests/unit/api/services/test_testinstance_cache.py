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

from datetime import datetime
from unittest.mock import MagicMock

import pytest
import redis

from lifemonitor.api.models.services.github.testinstance_cache import (
    TestInstanceCache, iso_to_epoch)


@pytest.fixture
def mock_redis_client(redis_cache, mocker):
    pipeline_mock = mocker.Mock()
    pipeline_mock.execute.return_value = True
    pipeline_mock.hset.return_value = True
    pipeline_mock.zadd.return_value = True
    pipeline_mock.delete.return_value = True
    pipeline_mock.zrem.return_value = True
    pipeline_mock.zrevrange.return_value = []
    pipeline_mock.hgetall.return_value = {}
    pipeline_mock.zrangebyscore.return_value = []

    redis_client = mocker.Mock(spec=redis.Redis)
    redis_client.pipeline.return_value = pipeline_mock  # pipeline mock returned here
    # Needed for getter methods to retrieve full run details
    redis_client.smembers.return_value = {"run1", "run2"}
    redis_client.zrangebyscore.return_value = ["run1", "run2"]  # lista iterabile
    redis_client.zrevrangebyscore.return_value = ["run2", "run1"]
    redis_client.keys.return_value = [
        "testinstance:ti1:ref:ref1:runs",
        "testinstance:ti1:ref:ref2:runs"
    ]
    return redis_client


@pytest.fixture
def mock_run_cache(mocker):
    run_cache = mocker.Mock()
    run_cache.insert_update_run.return_value = True
    run_cache.batch_insert_update_runs.return_value = True
    run_cache.delete_run.return_value = True
    run_cache.batch_delete_runs.return_value = True
    run_cache.get_runs_by_ids.return_value = [{"id": "run1"}, {"id": "run2"}]
    return run_cache


@pytest.fixture
def cache(mock_redis_client, mock_run_cache, mocker):
    # mocker.patch('redis.Redis', return_value=mock_redis_client)
    mocker.patch('redis_lock.Lock')
    result = TestInstanceCache()
    result.redis_client = mock_redis_client
    result.run_cache = mock_run_cache  # inject the mock RunCache
    return result


def test_iso_to_epoch():
    iso_str = "2025-08-22T12:59:00Z"
    epoch = iso_to_epoch(iso_str)
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    assert epoch == int(dt.timestamp())


def test_set_update_timestamp_with_pipe(cache, mocker):
    pipe = mocker.Mock()
    pipe.set.return_value = None
    result = cache.set_update_timestamp("ti1", pipe=pipe)
    assert result is True
    pipe.set.assert_called_once()
    called_key = pipe.set.call_args[0][0]
    assert called_key == "testinstance:ti1:last_update"


def test_set_update_timestamp_without_pipe(cache, mock_redis_client):
    result = cache.set_update_timestamp("ti1")
    assert result is True
    mock_redis_client.set.assert_called_once()
    called_key = mock_redis_client.set.call_args[0][0]
    assert called_key == "testinstance:ti1:last_update"


def test_associate_run_calls_set_update_timestamp(cache, mocker):
    mocker.patch.object(cache, 'set_update_timestamp', return_value=True)
    result = cache.associate_run("ti1", "run1", ref="ref1", created_at_iso="2025-08-23T10:00:00Z", use_lock=False)
    assert result is True
    cache.set_update_timestamp.assert_called_once()
    args, kwargs = cache.set_update_timestamp.call_args
    assert args[0] == "ti1"


def test_disassociate_run_calls_set_update_timestamp(cache, mocker):
    mocker.patch.object(cache, 'set_update_timestamp', return_value=True)
    result = cache.disassociate_run("ti1", "run1", ref="ref1", use_lock=False)
    assert result is True
    cache.set_update_timestamp.assert_called_once()
    args, kwargs = cache.set_update_timestamp.call_args
    assert args[0] == "ti1"


def test_associate_and_insert_run_calls_set_update_timestamp(cache, mocker):
    mocker.patch.object(cache, 'set_update_timestamp', return_value=True)
    metadata = {"created_at": "2025-08-23T10:00:00Z"}
    result = cache.associate_and_insert_run("ti1", "wf1", "run1", "ref1", metadata, use_lock=False)
    assert result is True
    cache.set_update_timestamp.assert_called_once()
    # We test that pipe parameter is passed (a pipeline instance)
    args, kwargs = cache.set_update_timestamp.call_args
    assert args[0] == "ti1"
    assert 'pipe' in kwargs or len(args) > 1  # pipe passed either as kwarg or positional


def test_batch_associate_and_insert_runs_calls_set_update_timestamp(cache, mocker):
    mocker.patch.object(cache, 'set_update_timestamp', return_value=True)
    runs = [
        {"run_id": "run1", "ref": "ref1", "metadata": {"created_at": "2025-08-23T10:00:00Z"}},
        {"run_id": "run2", "ref": "ref2", "metadata": {"created_at": "2025-08-23T11:00:00Z"}},
    ]
    result = cache.batch_associate_and_insert_runs("ti1", "wf1", runs, use_lock=False, max_retry=1)
    assert result is True
    cache.set_update_timestamp.assert_called()
    args, kwargs = cache.set_update_timestamp.call_args
    assert args[0] == "ti1"


def test_disassociate_and_delete_run_calls_set_update_timestamp(cache, mocker):
    mocker.patch.object(cache, 'set_update_timestamp', return_value=True)
    result = cache.disassociate_and_delete_run("ti1", "wf1", "run1", "ref1", use_lock=False)
    assert result is True
    cache.set_update_timestamp.assert_called_once()
    args, kwargs = cache.set_update_timestamp.call_args
    assert args[0] == "ti1"


def test_batch_disassociate_and_delete_runs_calls_set_update_timestamp(cache, mocker):
    mocker.patch.object(cache, 'set_update_timestamp', return_value=True)
    runs = [
        {"run_id": "run1", "ref": "ref1"},
        {"run_id": "run2", "ref": "ref2"}
    ]
    result = cache.batch_disassociate_and_delete_runs("ti1", "wf1", runs, use_lock=False, max_retry=1)
    assert result is True
    cache.set_update_timestamp.assert_called()
    args, kwargs = cache.set_update_timestamp.call_args
    assert args[0] == "ti1"


def test_associate_run_no_lock(cache, mock_redis_client):
    # retrieve the pipeline mock
    pipeline_mock = mock_redis_client.pipeline.return_value

    result = cache.associate_run("ti1", "run1", ref="ref1", created_at_iso="2025-08-22T12:00:00Z", use_lock=False)
    assert result is True
    assert pipeline_mock.sadd.called
    assert pipeline_mock.zadd.called
    assert pipeline_mock.execute.called


def test_associate_run_with_lock_acquire_fail(cache, mocker):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = False
    mocker.patch('redis_lock.Lock', return_value=mock_lock)

    result = cache.associate_run("ti1", "run1", ref="ref1", use_lock=True)
    assert result is False


def test_associate_run_with_lock_success(cache, mocker):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True
    mocker.patch('redis_lock.Lock', return_value=mock_lock)

    result = cache.associate_run("ti1", "run1", ref="ref1", use_lock=True)
    assert result is True
    mock_lock.release.assert_called()


def test_disassociate_run_no_lock(cache, mock_redis_client):
    # retrieve the pipeline mock
    pipeline_mock = mock_redis_client.pipeline.return_value

    result = cache.disassociate_run("ti1", "run1", ref="ref1", use_lock=False)
    assert result is True
    assert pipeline_mock.srem.called
    assert pipeline_mock.zrem.called


def test_disassociate_run_with_lock_success(cache, mocker):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True
    mocker.patch('redis_lock.Lock', return_value=mock_lock)

    result = cache.disassociate_run("ti1", "run1", ref="ref1", use_lock=True)
    assert result is True
    mock_lock.release.assert_called()


@pytest.mark.parametrize("use_lock", [True, False])
def test_batch_associate_runs(cache, mocker, use_lock):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True
    mocker.patch('redis_lock.Lock', return_value=mock_lock)

    runs = [
        {"run_id": "r1", "ref": "ref1", "created_at_iso": "2025-08-22T12:00:00Z"},
        {"run_id": "r2", "ref": "ref2", "created_at_iso": "2025-08-22T13:00:00Z"},
    ]
    result = cache.batch_associate_runs("ti1", runs, use_lock=use_lock)
    assert result is True
    if use_lock:
        mock_lock.release.assert_called()


@pytest.mark.parametrize("use_lock", [True, False])
def test_batch_disassociate_runs(cache, mocker, use_lock):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True
    mocker.patch('redis_lock.Lock', return_value=mock_lock)

    runs = [
        {"run_id": "r1", "ref": "ref1"},
        {"run_id": "r2", "ref": "ref2"},
    ]
    result = cache.batch_disassociate_runs("ti1", runs, use_lock=use_lock)
    assert result is True
    if use_lock:
        mock_lock.release.assert_called()


def test_get_run_ids_by_ref_empty(cache, mock_redis_client):
    mock_redis_client.smembers.return_value = {"run1", "run2"}

    result = cache.get_run_ids_by_ref("ti1", "ref1")
    assert isinstance(result, list)
    assert "run1" in result


def test_get_run_ids_by_date_range_empty(cache, mock_redis_client):
    mock_redis_client.zrangebyscore.return_value = ["run1", "run2"]

    result = cache.get_run_ids_by_date_range("ti1", "2025-08-21T00:00:00Z", "2025-08-23T00:00:00Z")
    assert isinstance(result, list)
    assert "run1" in result


def test_get_all_refs(cache, mock_redis_client):
    mock_redis_client.keys.return_value = [
        "testinstance:ti1:ref:ref1:runs",
        "testinstance:ti1:ref:ref2:runs"
    ]
    result = cache.get_all_refs("ti1")
    assert isinstance(result, list)
    assert "ref1" in result
    assert "ref2" in result


def test_get_run_by_ref(cache):
    result = cache.get_run_by_ref("ti1", "ref1", "wf1")
    assert isinstance(result, list)
    cache.run_cache.get_runs_by_ids.assert_called_once_with("wf1", list({"run1", "run2"}))


def test_get_runs_by_date_range(cache):
    result = cache.get_runs_by_date_range("ti1", "wf1", start_iso=None, end_iso=None, limit=100)
    assert isinstance(result, list)
    cache.run_cache.get_runs_by_ids.assert_called_once_with("wf1", ["run1", "run2"])


def test_get_runs_ordered_by_date_ascending(cache):
    result = cache.get_runs_ordered_by_date("ti1", "wf1", ascending=True, limit=100)
    assert isinstance(result, list)
    cache.run_cache.get_runs_by_ids.assert_called_once_with("wf1", ["run1", "run2"])


def test_get_runs_ordered_by_date_descending(cache):
    result = cache.get_runs_ordered_by_date("ti1", "wf1", ascending=False, limit=100)
    assert isinstance(result, list)
    cache.run_cache.get_runs_by_ids.assert_called_once_with("wf1", ["run2", "run1"])


def test_get_latest_runs(cache):
    result = cache.get_latest_runs("ti1", "wf1", limit=10)
    assert isinstance(result, list)
    cache.run_cache.get_runs_by_ids.assert_called_once_with("wf1", ["run2", "run1"])


def test_associate_and_insert_run_calls_run_cache_insert_update_run(cache, mock_run_cache):
    metadata = {"created_at": "2025-08-23T10:00:00Z"}
    result = cache.associate_and_insert_run("ti1", "wf1", "run1", "ref1", metadata, use_lock=False)
    assert result is True
    mock_run_cache.insert_update_run.assert_called_once()


def test_batch_associate_and_insert_runs_calls_run_cache_batch_insert_update_runs(cache, mock_run_cache):
    runs = [{
        "run_id": "run1",
        "ref": "ref1",
        "metadata": {"created_at": "2025-08-23T10:00:00Z"}
    }]
    result = cache.batch_associate_and_insert_runs("ti1", "wf1", runs, use_lock=False, max_retry=1)
    assert result is True
    mock_run_cache.batch_insert_update_runs.assert_called_once()


def test_disassociate_and_delete_run_calls_run_cache_delete_run(cache, mock_run_cache):
    result = cache.disassociate_and_delete_run("ti1", "wf1", "run1", "ref1", use_lock=False)
    assert result is True
    mock_run_cache.delete_run.assert_called_once()


def test_batch_disassociate_and_delete_runs_calls_run_cache_batch_delete_runs(cache, mock_run_cache):
    runs = [{"run_id": "run1", "ref": "ref1"}]
    result = cache.batch_disassociate_and_delete_runs("ti1", "wf1", runs, use_lock=False, max_retry=1)
    assert result is True
    mock_run_cache.batch_delete_runs.assert_called_once()
