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

FROM fairdom/seek:main

# Set environment variable for seek-data folder
ENV SEEK_DATA_DIR=/seek-data

# Copy the backup script
COPY backup.sh /seek/backup.sh
COPY restore.sh /seek/restore.sh

USER root

# Fix permissions
RUN chmod +x /seek/backup.sh
RUN chmod +x /seek/restore.sh

# Create a directory for backups
RUN mkdir -p $SEEK_DATA_DIR
# Copy seek data
COPY seek-filestore.tar $SEEK_DATA_DIR
COPY seek-mysql-db.tar $SEEK_DATA_DIR/seek-mysql-db.tar

# Fix permissions
RUN chown -R www-data:www-data $SEEK_DATA_DIR

# Restore the seek data
USER www-data

VOLUME $SEEK_DATA_DIR
