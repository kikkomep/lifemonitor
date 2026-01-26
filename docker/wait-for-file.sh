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

set -o nounset
set -o errexit

function debug_log() {
  if [[ -n "${DEBUG:-}" ]]; then
    log "${@}"
  fi
}

function log() {
  printf "%s [wait-for-file] %s\n" "$(date +"%F %T")" "${*}" >&2
}

file="${1:-}"
timeout=${2:-0}

if [[ -z ${file} ]]; then
    log "You need to provide a filename"
    exit 1
fi

log "Waiting for file ${file} (timeout: ${timeout})..."

if [[ -e "$file" ]]; then
    log "File ${file} found!"
    exit 0
fi

if ((timeout > 0)); then
    end_time=$((SECONDS + timeout))
    while [[ ! -e "$file" && $SECONDS -lt $end_time ]]; do
        debug_log "File not found ${file} found... retry within 1 sec"
        sleep 1
    done
else
    while [[ ! -e "$file" ]]; do
        debug_log "File not found ${file} found... retry within 1 sec"
        sleep 1
    done
fi

if [[ -e "$file" ]]; then
    log "File ${file} found!"
    exit 0
else
    log "File ${file} not found!"
    exit 1
fi

