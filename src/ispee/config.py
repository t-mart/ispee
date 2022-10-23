"""Configuration reader"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from attrs import field, frozen

from ispee.exception import ConfigSchemaError


@frozen(kw_only=True)
class PingConfig:
    name: str
    host: str
    types: list[Literal["icmp", "dns-udp", "dns-tcp"]]

    @classmethod
    def from_python_object(cls, obj: dict[str, Any]) -> PingConfig:
        name = obj["name"]
        host = obj["host"]
        types = [type_ for type_ in obj["types"]]
        return cls(name=name, host=host, types=types)


@frozen(kw_only=True)
class ArrisS33ModemConfig:
    host: str
    password: str

    @classmethod
    def from_python_object(cls, obj: dict[str, Any]) -> ArrisS33ModemConfig:
        host = obj["host"]
        password = obj["password"]
        return cls(host=host, password=password)


@frozen(kw_only=True)
class Config:
    arris_s33_modem_config: ArrisS33ModemConfig | None = field(default=None)
    ip: bool = field(default=False)
    pings: list[PingConfig] = field(factory=list)

    @classmethod
    def from_python_object(cls, obj: dict[str, Any]) -> Config:
        arris_dict = obj.get("arris_s33_modem", None)
        arris_config = None
        if arris_dict:
            arris_config = ArrisS33ModemConfig.from_python_object(arris_dict)
        return cls(
            arris_s33_modem_config=arris_config,
            ip="ip" in obj,
            pings=[
                PingConfig.from_python_object(ping) for ping in obj.get("pings", [])
            ],
        )


def get_config(
    config_path: Path,
) -> Config:
    """
    Read the config file at config_path and produce a representative object with very
    basic schema validation.
    """
    with config_path.open("r", encoding="utf-8") as config_file:
        config_obj = yaml.safe_load(config_file)

    try:
        config = Config.from_python_object(config_obj)
    except KeyError as key_error:
        ConfigSchemaError(str(key_error))

    return config
