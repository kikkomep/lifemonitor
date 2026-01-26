#!/usr/bin/env bash

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

HOST=${REDIS_HOST:-redis}
PORT=${REDIS_PORT:-6379}
PASSWORD=${REDIS_PASSWORD:-foobar}

echo "Waiting for Redis @$HOST:$PORT ..."
echo "Try ping Redis... "
PONG=`redis-cli -h $HOST -p $PORT -a $PASSWORD ping | grep PONG`
while [ -z "$PONG" ]; do
    sleep 1
    echo "Retry Redis ping... "
    PONG=`redis-cli -h $HOST -p $PORT -a $PASSWORD ping | grep PONG`
done
echo "Redis at host '$HOST', port '$PORT' fully started."