#!/bin/bash

set -x
set -e

# git pull

docker build -t tempstab_http -f http_server_Dockerfile .

docker container rm --force tempstab_http_container || true

docker run --rm -it -p 80:80 --name tempstab_http_container tempstab_http
