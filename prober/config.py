"""Configuration reader"""
from collections.abc import Iterable
from pathlib import Path

import yaml

from prober.exception import ConfigSchemaError
from prober.prometheus import MetricJob, ModemMetricJob, ProbeMetricJob

DEFAULT_CONFIG_PATH = Path("/etc/prober/config.yml")


def read_metric_jobs(
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> Iterable[MetricJob]:
    """
    Read the config file at config_path and produce a representative object with very
    basic schema validation.
    """
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    if "probes" not in config and "modems" not in config:
        raise ConfigSchemaError('Could not find key "probes"')

    for probe in config["probes"]:
        if "type" not in probe:
            raise ConfigSchemaError('Could not find key "type"')
        if "host" not in probe:
            raise ConfigSchemaError('Could not find key "host"')

        if probe["type"] == "icmp-ping":
            yield ProbeMetricJob.build_icmp_ping(host=probe["host"])
        elif probe["type"] == "tcp-ping":
            if "port" not in probe:
                raise ConfigSchemaError('Could not find key "port"')
            yield ProbeMetricJob.build_tcp_ping(
                host=probe["host"], port=int(probe["port"])
            )
        else:
            raise ConfigSchemaError(f"Unknown type {probe['type']}")

    for modem in config["modems"]:
        if "host" not in modem:
            raise ConfigSchemaError('Could not find key "host"')
        if "password" not in modem:
            raise ConfigSchemaError('Could not find key "password"')

        yield ModemMetricJob.build(host=modem["host"], password=modem["password"])
