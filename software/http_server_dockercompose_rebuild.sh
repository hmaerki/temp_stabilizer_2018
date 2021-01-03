#!/bin/bash

set -x
set -e

docker-compose rm --stop --force
docker-compose up --build --remove-orphans
