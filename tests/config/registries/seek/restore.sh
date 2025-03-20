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

#!/bin/bash

CURRENT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILENAME="docker-compose.yml"
COMPOSE_PATH="${CURRENT_PATH}/${COMPOSE_FILENAME}"
COMPOSE_FILE_OPTION="-f ${COMPOSE_PATH}"

VOLUME_PREFIX="$(basename $CURRENT_PATH)"
DB_VOLUME_NAME="${VOLUME_PREFIX}_seek-mysql-db"
FILESTORE_VOLUME_NAME="${VOLUME_PREFIX}_seek-filestore"

echo "Restoring Seek data from ${CURRENT_PATH}"
echo "Volumes: ${DB_VOLUME_NAME}, ${FILESTORE_VOLUME_NAME}"
echo "Compose file: ${COMPOSE_PATH}"

docker compose ${COMPOSE_FILE_OPTION} down
docker volume rm $DB_VOLUME_NAME
docker volume rm $FILESTORE_VOLUME_NAME
docker volume create --name=$DB_VOLUME_NAME
docker volume create --name=$FILESTORE_VOLUME_NAME
# Start the containers without starting the services
docker compose ${COMPOSE_FILE_OPTION} up --no-start
# Restore the data
# docker run --rm --volumes-from seek -v "${CURRENT_PATH}":/backup ubuntu bash -c "tar xfv /backup/seek-filestore.tar"
# docker run --rm --volumes-from seek-mysql -v "${CURRENT_PATH}":/backup ubuntu bash -c "tar xfv /backup/seek-mysql-db.tar"
docker run --rm --volumes-from seek-data --volumes-from seek-data ubuntu \
    bash -c "tar xfv /seek-data/seek-filestore.tar -C /seek --strip-components=1"
docker run --rm  --volumes-from seek-mysql --volumes-from seek-data ubuntu \
    bash -c "tar xfv /seek-data/seek-mysql-db.tar -C /var --strip-components=1"

# Start the main containers
docker compose ${COMPOSE_FILE_OPTION} up -d

# Reindex the data
docker exec seek bundle exec rake seek:reindex_all
