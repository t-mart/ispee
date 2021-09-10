FROM python:3.10-buster

WORKDIR /app

EXPOSE 8000/tcp

COPY pyproject.toml /app/
COPY prober/ /app/prober/

# just for testing. usually, you'll mount the config file as we do in the docker-compose.
# (what's best practice?)
# COPY probes.yml /etc/prober/probes.yml

RUN set -ex \
    && pip install /app

CMD ["python", "-m", "prober"]
