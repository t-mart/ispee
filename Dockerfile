FROM python:3.10-slim-buster

# https://stackoverflow.com/questions/59812009/what-is-the-use-of-pythonunbuffered-in-docker-file
ENV PYTHONUNBUFFERED=1

# rich's log output defaults to super small 80 otherwise
ENV COLUMNS=200

WORKDIR /app

# expose prometheus http endpoint
EXPOSE 8000/tcp

COPY pyproject.toml /app/
RUN set -ex \
    # do a little dance to convince "pip install" that the module in pyproject.toml exists by simply
    # creating a dummy module.
    #
    # this lets us put the dependency installation step further up in the Dockerfile, so it can be
    # cached. otherwise, you're having to reinstall all dependencies again for a simple code change.
    #
    # imo, this is a considerable deficieny in pyproject.toml/poetry over requirement.txt files,
    # which do not require a module to exist before installation dependencies. additionally,
    # pyproject.toml only contains a "symbolic" representation of a dependency, while poetry.lock
    # contains discrete version-pinned/hashed depenedencies, so there could be differences.
    && mkdir /app/ispee \
    && touch /app/ispee/__init__.py \
    && pip install /app

# ok, now that deps are cached, actually copy the module.
COPY src/ispee/ /app/ispee/

# just for testing. usually, you'll mount the config file as we do in the docker-compose, so this'll
# get overwritten. bind-mount is better than baking-into-image because you don't need to rebuild the
# image when it changes.
COPY config.yml /etc/ispee/config.yml

CMD ["python", "-m", "ispee"]
