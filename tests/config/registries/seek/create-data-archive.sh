#!/bin/bash

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

set -ex

seek_version=${1:-"1.12.0"}

script_path="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
root_project_path="$(realpath "${script_path}/../../../../")"
tmp_path="/tmp/seek_data"
data_path="${tmp_path}/data"
archive_filename="${seek_version}.tar.gz"

seek_container_id=$(docker compose -f "${root_project_path}/docker-compose.extra.yml" ps -q seek)

rm -rf "${data_path}"
mkdir -p "${data_path}"
docker cp ${seek_container_id}:/seek/filestore ${data_path}/filestore
docker cp ${seek_container_id}:/seek/sqlite3-db/production.sqlite3 ${data_path}/db.sqlite3

pushd ${tmp_path}
tar -czvf ${archive_filename} data
popd

mv "${tmp_path}/${archive_filename}" "${script_path}/backups/${archive_filename}"
rm -rf ${tmp_path}
