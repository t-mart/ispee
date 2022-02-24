src-paths = prober

.PHONY: all
all: isort black flake8 pylint mypy

.PHONY: mypy
mypy:
	mypy $(src-paths)

.PHONY: isort
isort:
	isort $(src-paths)

.PHONY: flake8
flake8:
	flake8 $(src-paths)

.PHONY: pylint
pylint:
	pylint $(src-paths)

.PHONY: black
black:
	black $(src-paths)

.PHONY: up
up:
	docker compose up --detach --build --always-recreate-deps

.PHONY: down
down:
	docker compose down

.PHONY: rebuild
rebuild: down up

.PHONY: export-grafana
export-grafana:
	curl localhost:3000/api/dashboards/uid/internet-performance | jq ".dashboard" > ./grafana/dashboards/internet-performance.json

.PHONY: backup-metrics
backup-metrics:
	docker run \
	  --rm \
	  -it \
	  --network conn-probe-network \
	  --mount "type=volume,src=conn-probe-victoriametrics,dst=/storage,readonly" \
	  --mount "type=bind,src=${CURDIR},dst=/host" \
	  --entrypoint "sh" \
	  victoriametrics/vmbackup \
	  	/host/backup-restore/backup-metrics.sh

.PHONY: archive-metrics
restore-metrics: down
	docker run \
	  --rm \
	  -it \
	  --mount "type=volume,src=conn-probe-victoriametrics,dst=/storage" \
	  --mount "type=bind,src=${CURDIR},dst=/host" \
	  --entrypoint "sh" \
	  victoriametrics/vmrestore \
	  	/host/backup-restore/restore-metrics.sh
