# Download data from the server to be replaced
ssh root@tempstabilizer2018.org tar -C /var/lib -zcf - grafana > var_lib_grafana.tgz
ssh root@tempstabilizer2018.org tar -C /var/lib -zcf - influxdb > var_lib_influxdb.tgz
ssh root@tempstabilizer2018.org tar -C /home/pi/tempstabilizer2018/software/http_server -zcf - node_data > http_server.tgz

# Remove the volumes
docker-compose rm --stop --force

docker volume rm grafana-storage
docker volume rm influxdb-storage
docker volume rm http_server-storage

# Recreate the volumes and load the data
docker volume create grafana-storage
docker volume create influxdb-storage
docker volume create http_server-storage

cat var_lib_grafana.tgz | docker run --rm --name=restore_tmp -v grafana-storage:/var/lib/grafana -i --entrypoint="" grafana/grafana:7.3.7 tar -C /var/lib -xzvf -
cat var_lib_influxdb.tgz | docker run --rm --name=restore_tmp -v influxdb-storage:/var/lib/influxdb -i --entrypoint="" influxdb:1.8.3-alpine tar -C /var/lib -xzvf -
cat http_server.tgz | docker run --rm --name=restore_tmp -v http_server-storage:/app/http_server/node_data -i --entrypoint="" python:3.7-stretch tar -C /app/http_server -xzvf -





