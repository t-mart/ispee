from collections.abc import Callable, Iterable
from functools import partial
from pathlib import Path

import yaml

from prober.prometheus import record_icmp_ping_probe, record_tcp_ping_probe

DEFAULT_CONFIG_PATH = Path("/etc/prober/probes.yml")


class ConfigSchemaError(Exception):
    """Indicates that a read file does not match the prescribed schema."""


def get_config_probe_record_fns(
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> Iterable[Callable[[], None]]:
    """
    Read the config file at config_path and produce a representative object with very
    basic schema validation.
    """
    with config_path.open("r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    if "probes" not in config:
        raise ConfigSchemaError('Could not find key "probes"')

    for probe in config["probes"]:
        if "type" not in probe:
            raise ConfigSchemaError('Could not find key "type"')
        if "host" not in probe:
            raise ConfigSchemaError('Could not find key "host"')

        match probe["type"]:
            case "icmp-ping":
                yield partial(record_icmp_ping_probe, host=probe["host"])
            case "tcp-ping":
                if "port" not in probe:
                    raise ConfigSchemaError('Could not find key "port"')
                yield partial(
                    record_tcp_ping_probe, host=probe["host"], port=int(probe["port"])
                )
            case _:
                raise ConfigSchemaError(f"Unknown type {probe['type']}")
