"""Configuration reader"""
from collections.abc import Iterable
from pathlib import Path

import yaml

from prober.exception import ConfigSchemaError
from prober.prometheus import MetricJob, ArrisS33ModemMetricJob, ProbeMetricJob


def read_metric_jobs(
    config_path: Path,
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
        if "name" not in probe:
            raise ConfigSchemaError('Could not find key "name"')

        if probe["type"] == "icmp-ping":
            yield ProbeMetricJob.build_icmp_ping(host=probe["host"], name=probe["name"])
        elif probe["type"] == "tcp-ping":
            if "port" not in probe:
                raise ConfigSchemaError('Could not find key "port"')
            yield ProbeMetricJob.build_tcp_ping(
                host=probe["host"], port=int(probe["port"]), name=probe["name"]
            )
        else:
            raise ConfigSchemaError(f"Unknown type {probe['type']}")

    if "arris_s33_modem" in config:
        modem = config["arris_s33_modem"]
        if "host" not in modem:
            raise ConfigSchemaError('Could not find key "host"')
        if "password" not in modem:
            raise ConfigSchemaError('Could not find key "password"')

        yield ArrisS33ModemMetricJob.build(
            host=modem["host"], password=modem["password"]
        )
