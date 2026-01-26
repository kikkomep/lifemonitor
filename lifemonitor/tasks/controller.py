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
import time

import flask
from flask_login import current_user

from lifemonitor.auth.services import authorized
from lifemonitor.cache import cache

from . import utils

# Config a module level logger
logger = logging.getLogger(__name__)

blueprint = flask.Blueprint("jobs", __name__,
                            url_prefix="/jobs",
                            template_folder='templates',
                            static_folder="static", static_url_path='../static')


@authorized
@blueprint.route("/status/<job_id>", methods=("GET",))
def get_job_status(job_id: str):
    if not utils.validate_job_id(job_id):
        raise ValueError(f"Invalid job id: {job_id}")
    serialized_job_data = cache.get(utils.get_job_key(job_id=job_id))
    if not serialized_job_data:
        return f"job ${job_id} not found", 404
    return json.loads(serialized_job_data)


@authorized
@blueprint.route("/<job_id>/events", methods=("GET",))
def get_job_events(job_id: str):
    if not utils.validate_job_id(job_id):
        raise ValueError(f"Invalid job id: {job_id}")

    def event_stream():
        import json
        i = 0
        sleep_interval = 1
        last_sent_data = None
        try:
            while True:
                serialized_job_data = cache.get(utils.get_job_key(job_id=job_id))
                if not serialized_job_data:
                    return f"job ${job_id} not found", 404
                if serialized_job_data == last_sent_data:
                    logger.warning("No new data for job %s, sleeping...", job_id)
                    time.sleep(sleep_interval)
                    continue
                job_data = json.loads(serialized_job_data)
                data = {
                    "counter": i,
                    "timestamp": time.time(),
                    "type": "jobUpdate",
                    "data": job_data
                }
                logger.info(f"Sending event data: {job_data['status']}")
                yield f"data: {json.dumps(data)}\n\n"
                if job_data.get("status", "") in ["completed", "failed", "canceled"]:
                    break
                i += 1
                time.sleep(sleep_interval)
        except Exception as e:
            logger.error(f"Error in event stream for job {job_id}: {str(e)}")
        logger.info(f"Job {job_id} ended with status: {job_data.get('status', '')}")

    return flask.Response(
        flask.stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # <--- IMPORTANT FOR NGINX
        },
    )
