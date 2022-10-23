src-paths := src

.PHONY: all check format up down export-grafana backup-metrics restore-metrics

all: format check

check:
	mypy $(src-paths)
	flake8 $(src-paths)

format:
	isort $(src-paths)
	black $(src-paths)

up:
	docker compose up --detach --build --always-recreate-deps

down:
	docker compose down

restart: down up

export-grafana:
	curl localhost:3000/api/dashboards/uid/latency | jq ".dashboard" > ./grafana/dashboards/latency.json
	curl localhost:3000/api/dashboards/uid/modem | jq ".dashboard" > ./grafana/dashboards/modem.json
	curl localhost:3000/api/dashboards/uid/ip-address | jq ".dashboard" > ./grafana/dashboards/ip-address.json

backup-metrics:
	docker run \
	  --rm \
	  -it \
	  --network conn-probe-network \
	  --mount "type=volume,src=conn-probe-victoriametrics-storage,dst=/storage,readonly" \
	  --mount "type=bind,src=${CURDIR},dst=/host" \
	  --entrypoint "sh" \
	  victoriametrics/vmbackup \
	  	/host/backup-restore/backup-metrics.sh

restore-metrics: down
	docker run \
	  --rm \
	  -it \
	  --mount "type=volume,src=conn-probe-victoriametrics-storage,dst=/storage" \
	  --mount "type=bind,src=${CURDIR},dst=/host" \
	  --entrypoint "sh" \
	  victoriametrics/vmrestore \
	  	/host/backup-restore/restore-metrics.sh
