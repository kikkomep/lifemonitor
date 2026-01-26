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

import json
from datetime import datetime
from unittest.mock import MagicMock, call

import pytest
import redis
import redis_lock

from lifemonitor.api.models.services.github.run_cache import (RunCache,
                                                              iso_to_epoch)


@pytest.fixture
def mock_redis_client(redis_cache, mocker):
    pipeline_mock = mocker.Mock()
    pipeline_mock.execute.return_value = True
    pipeline_mock.set.return_value = True
    pipeline_mock.zadd.return_value = True
    pipeline_mock.delete.return_value = True
    pipeline_mock.zrem.return_value = True
    pipeline_mock.zrevrange.return_value = []
    pipeline_mock.hgetall.return_value = {}
    pipeline_mock.zrangebyscore.return_value = []

    redis_client = mocker.Mock(spec=redis.Redis)
    redis_client.pipeline.return_value = pipeline_mock  # pipeline mock returned here
    return redis_client


@pytest.fixture
def cache(mock_redis_client, mocker):
    # mocker.patch('redis.Redis', return_value=mock_redis_client)
    mocker.patch('redis_lock.Lock')
    result = RunCache()
    result.redis_client = mock_redis_client
    return result


def test_iso_to_epoch():
    iso_str = "2025-08-22T12:45:00Z"
    epoch = iso_to_epoch(iso_str)
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    assert epoch == int(dt.timestamp())


def test_insert_update_run_no_lock(cache, mock_redis_client, mocker):
    # retrieve the pipeline mock
    pipeline_mock = mock_redis_client.pipeline.return_value

    mocker.patch.object(redis_lock.Lock, 'acquire', return_value=True)

    metadata = {"created_at": "2025-08-22T12:00:00Z", "status": "success"}
    result = cache.insert_update_run("wf1", "run1", "ref1", metadata, use_lock=False)
    assert result is True
    assert pipeline_mock.set.called  # check calls on pipeline mock, not redis_client itself
    assert pipeline_mock.zadd.called


def test_insert_update_run_with_lock_acquire_fail(cache, mocker):
    # Simulate lock acquire fails
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = False
    mocker.patch('redis_lock.Lock', return_value=mock_lock)

    metadata = {"created_at": "2025-08-22T12:00:00Z"}
    result = cache.insert_update_run("wf1", "run1", "ref1", metadata, use_lock=True)
    assert result is False


def test_insert_update_run_with_lock_success(cache, mocker):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True
    mocker.patch('redis_lock.Lock', return_value=mock_lock)

    metadata = {"created_at": "2025-08-22T12:00:00Z"}
    result = cache.insert_update_run("wf1", "run1", "ref1", metadata, use_lock=True)
    assert result is True
    mock_lock.release.assert_called()


def test_delete_run_no_lock(cache, mock_redis_client):
    # retrieve the pipeline mock
    pipeline_mock = mock_redis_client.pipeline.return_value

    result = cache.delete_run("wf1", "run1", "ref1", use_lock=False)
    assert result is True
    assert pipeline_mock.delete.called
    assert pipeline_mock.zrem.called


def test_delete_run_with_lock_success(cache, mocker):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True
    mocker.patch('redis_lock.Lock', return_value=mock_lock)
    result = cache.delete_run("wf1", "run1", "ref1", use_lock=True)
    assert result is True
    mock_lock.release.assert_called()


@pytest.mark.parametrize("use_lock", [True, False])
def test_batch_insert_update_runs(cache, mocker, use_lock):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True
    mocker.patch('redis_lock.Lock', return_value=mock_lock)

    runs = [
        {"run_id": "r1", "ref": "ref1", "metadata": {"created_at": "2025-08-22T12:00:00Z"}},
        {"run_id": "r2", "ref": "ref2", "metadata": {"created_at": "2025-08-22T13:00:00Z"}},
    ]
    result = cache.batch_insert_update_runs("wf1", runs, use_lock=use_lock)
    assert result is True
    if use_lock:
        mock_lock.release.assert_called()


def test_insert_update_run_with_external_pipe(cache, mock_redis_client):
    pipe = MagicMock()
    pipe.set.return_value = None
    pipe.zadd.return_value = None
    # Simulate external pipeline, so execute should NOT be called inside method
    pipe.execute.return_value = None  # To confirm no double execution

    metadata = {"created_at": "2025-08-23T10:00:00Z", "status": "ok"}
    result = cache.insert_update_run("wf1", "run123", "refX", metadata, use_lock=False, pipe=pipe)

    assert result is True
    pipe.set.assert_called_once()
    pipe.zadd.assert_has_calls([
        call('workflow:wf1:runs', {'run123': iso_to_epoch(metadata['created_at'])}),
        call('workflow:wf1:ref:refX:runs', {'run123': iso_to_epoch(metadata['created_at'])})
    ])
    pipe.execute.assert_not_called()  # Must NOT execute because pipe was passed in externally


@pytest.mark.parametrize("use_lock", [True, False])
def test_batch_delete_runs(cache, mocker, use_lock):
    mock_lock = MagicMock()
    mock_lock.acquire.return_value = True
    mocker.patch('redis_lock.Lock', return_value=mock_lock)

    runs = [
        {"run_id": "r1", "ref": "ref1"},
        {"run_id": "r2", "ref": "ref2"},
    ]
    result = cache.batch_delete_runs("wf1", runs, use_lock=use_lock)
    assert result is True
    if use_lock:
        mock_lock.release.assert_called()


def test_batch_insert_update_runs_with_external_pipe(cache):
    pipe = MagicMock()
    pipe.set.return_value = None
    pipe.zadd.return_value = None
    pipe.execute.return_value = None

    runs = [
        {"run_id": "r1", "ref": "ref1", "metadata": {"created_at": "2025-08-23T09:00:00Z"}},
        {"run_id": "r2", "ref": "ref2", "metadata": {"created_at": "2025-08-23T10:00:00Z"}},
    ]

    result = cache.batch_insert_update_runs("wf1", runs, use_lock=False, pipe=pipe, max_retry=1)
    assert result is True

    expected_calls = []
    for run in runs:
        epoch = iso_to_epoch(run['metadata']['created_at'])
        expected_calls.append(call(f"workflow:wf1:run:{run['run_id']}", json.dumps(run['metadata'])))
    pipe.set.assert_has_calls(expected_calls, any_order=True)

    # also check zadd calls
    calls = []
    for run in runs:
        epoch = iso_to_epoch(run['metadata']['created_at'])
        calls.append(call("workflow:wf1:runs", {run['run_id']: epoch}))
        calls.append(call(f"workflow:wf1:ref:{run['ref']}:runs", {run['run_id']: epoch}))
    pipe.zadd.assert_has_calls(calls, any_order=True)

    pipe.execute.assert_not_called()  # execute must not be called inside method when pipe passed


def test_get_run_returns_data(cache, mock_redis_client):
    expected_data = {'field1': 'value1', 'field2': 'value2'}
    mock_redis_client.get.return_value = json.dumps(expected_data)

    result = cache.get_run('workflow1', 'run123')
    assert result == expected_data
    mock_redis_client.get.assert_called_once_with('workflow:workflow1:run:run123')


def test_get_run_handles_redis_error(cache, mock_redis_client, mocker):
    mock_redis_client.get.side_effect = redis.exceptions.RedisError('fail')

    result = cache.get_run('workflow1', 'run123')
    assert result is None


def test_get_runs_by_ids_returns_data(cache, mock_redis_client):
    run_ids = ['run1', 'run2']
    expected_results = [{'field': 'val1'}, {'field': 'val2'}]

    # Setup pipeline mock
    pipe_mock = MagicMock()
    mock_redis_client.pipeline.return_value = pipe_mock
    pipe_mock.get.side_effect = expected_results
    pipe_mock.execute.return_value = json.dumps(expected_results)

    results = cache.get_runs_by_ids('workflow1', run_ids)
    assert results == expected_results

    # Check that hgetall called with correct keys
    calls = [((f'workflow:workflow1:run:{run_id}',),) for run_id in run_ids]
    pipe_mock.get.assert_has_calls(calls, any_order=False)
    pipe_mock.execute.assert_called_once()


def test_get_runs_by_ids_empty_list(cache, mock_redis_client):
    results = cache.get_runs_by_ids('workflow1', [])
    assert results == []
    mock_redis_client.pipeline.assert_not_called()


def test_get_latest_runs_empty(cache, mock_redis_client):
    data = [{"id": "run1"}, {"id": "run2"}]
    mock_pipe = MagicMock()
    mock_pipe.execute.return_value = json.dumps(data)

    mock_redis_client.pipeline.return_value = mock_pipe
    mock_redis_client.zrevrange.return_value = ["run1", "run2"]
    mock_redis_client.get.side_effect = [{"id": "run1"}, {"id": "run2"}]

    result = cache.get_latest_runs("wf1", "ref1", n=2)
    assert isinstance(result, list)
    assert len(result) == 2


def test_get_runs_by_date_range_empty(cache, mock_redis_client):
    data = [{"id": "run1"}, {"id": "run2"}]
    mock_pipe = MagicMock()
    mock_pipe.execute.return_value = json.dumps(data)

    mock_redis_client.zrangebyscore.return_value = ["run1", "run2"]
    mock_redis_client.pipeline.return_value = mock_pipe
    mock_redis_client.get.side_effect = [{"id": "run1"}, {"id": "run2"}]

    result = cache.get_runs_by_date_range("wf1", "ref1", start_iso="2025-08-21T00:00:00Z", end_iso="2025-08-23T00:00:00Z", limit=2)
    assert isinstance(result, list)
    assert len(result) == 2
