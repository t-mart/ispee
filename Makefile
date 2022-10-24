src-paths := src scripts

.PHONY: all check format up down backup-dashbaords backup-metrics restore-metrics

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

backup-dashboards:
	python scripts/backup_dashboards.py

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
