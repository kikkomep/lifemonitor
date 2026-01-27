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


#docker network create seek_default
docker run -d --network seek_default -p 3001:3000 \
  -v $(pwd)/nginx.conf:/etc/nginx/nginx.conf:ro -v $(pwd):/certs:ro \
  -v $(pwd)/data/config:/seek/config:rw \
  -v $(pwd)/data/public:/seek/public:rw \
  -v $(pwd)/data/solr:/seek/solr:rw \
  -v $(pwd)/data/log:/seek/log:rw \
  -v $(pwd)/data/tmp:/seek/tmp:rw \
  -v $(pwd)/data/db.sqlite3:/seek/sqlite3-db/production.sqlite3:rw \
  -v $(pwd)/data/filestore:/seek/filestore:rw \
  --name seek-test fairdom/seek:workflow


#--add-host seek.org:192.168.1.167 