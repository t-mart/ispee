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
	http localhost:3000/api/dashboards/uid/internet-performance | jq ".dashboard" > ./grafana/dashboards/internet-performance.json
