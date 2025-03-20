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
docker compose ${COMPOSE_FILE_OPTION} up --no-start
docker run --rm --volumes-from seek -v "${CURRENT_PATH}":/backup ubuntu bash -c "tar xfv /backup/seek-filestore.tar"
docker run --rm --volumes-from seek-mysql -v "${CURRENT_PATH}":/backup ubuntu bash -c "tar xfv /backup/seek-mysql-db.tar"
docker compose ${COMPOSE_FILE_OPTION} up -d


docker exec seek bundle exec rake seek:reindex_all
