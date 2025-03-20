#!/bin/bash

docker compose stop
docker run --rm --volumes-from seek -v $(pwd):/backup ubuntu tar cvf /backup/seek-filestore.tar /seek/filestore
docker run --rm --volumes-from seek-mysql -v $(pwd):/backup ubuntu tar cvf /backup/seek-mysql-db.tar /var/lib/mysql
docker compose start
