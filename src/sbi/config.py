"""Конфигурация: YAML по умолчанию плюс переопределения из командной строки."""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class Config(dict):
    def path(self, key: str) -> Path:
        p = Path(self["paths"][key])
        return p if p.is_absolute() else ROOT / p


def _set(cfg: dict, dotted: str, value: str) -> None:
    keys = dotted.split(".")
    node = cfg
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = yaml.safe_load(value)


def load(path: str | Path | None = None, overrides: list[str] | None = None) -> Config:
    base = yaml.safe_load((ROOT / "configs" / "default.yaml").read_text())
    if path and Path(path).name != "default.yaml":
        extra = yaml.safe_load(Path(path).read_text()) or {}
        base = _merge(base, extra)
    for item in overrides or []:
        key, _, value = item.partition("=")
        _set(base, key, value)
    return Config(base)


def _merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def cli(doc: str, extra=None):
    ap = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=None)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    if extra:
        extra(ap)
    args = ap.parse_args()
    return load(args.config, args.set), args
