"""Открытые ряды sberindex.ru.

Дашборды сайта берут данные через POST /api/sowa: GET-маршрут
(/dataset/v1/<имя>?limit=&offset=) кодируется в base64, а ответ приходит
в типизированной обёртке: строки как __string__<base64>, числа как
__number__<x>. Модуль повторяет эту схему и отдаёт обычные таблицы.
"""
from __future__ import annotations

import base64
import re
import time
import uuid

import pandas as pd

from .. import net

_TYPED = re.compile(r"^__([a-z0-9]*)__(.*)$", re.S)


def _decode(node):
    """Разворачивает типизированную обёртку ответа в обычные dict, list и скаляры."""
    if isinstance(node, list):
        return [_decode(x) for x in node]
    if isinstance(node, dict):
        if "type" in node and "value" in node and set(node) <= {"key", "type", "value"}:
            if node["type"] == "object":
                value = node["value"]
                if isinstance(value, list) and value and all(isinstance(v, dict) and "key" in v for v in value):
                    return {v["key"]: _decode(v) for v in value}
                return _decode(value)
            return _decode(node["value"])
        return {k: _decode(v) for k, v in node.items()}
    m = _TYPED.match(str(node))
    if not m:
        return node
    kind, payload = m.groups()
    if kind == "null":
        return None
    if kind == "number":
        return float(payload)
    if kind == "boolean":
        return payload == "true"
    if kind == "string":
        return base64.b64decode(payload).decode("utf-8")
    return payload


class Client:
    def __init__(self, url: str, pause: float = 0.3):
        self.url = url
        self.s = net.session()
        self.pause = pause

    def get(self, route: str):
        body = {"SOWA": {"method": "GET", "route": base64.b64encode(route.encode()).decode(),
                         "data": {"type": "object", "value": []}}}
        for attempt in range(4):
            try:
                # сервер требует уникальный идентификатор запроса
                r = self.s.post(self.url, json=body, headers={"rquid": uuid.uuid4().hex}, timeout=120)
                r.raise_for_status()
                time.sleep(self.pause)
                return _decode(r.json()["SOWA"]["data"])
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    def dataset(self, name: str, page: int = 1000) -> pd.DataFrame:
        frames, offset = [], 0
        while True:
            res = self.get(f"/dataset/v1/{name}?limit={page}&offset={offset}")
            rows = (res or {}).get("data") or []
            if not rows:
                break
            frames.append(pd.DataFrame(rows, columns=res["fields"]))
            if len(rows) < page:
                break
            offset += page
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def download(cfg) -> None:
    out = cfg.path("external") / "sberindex"
    out.mkdir(parents=True, exist_ok=True)
    client = Client(cfg["sources"]["sberindex_api"])
    for name in cfg["sberindex_datasets"]:
        target = out / f"{name}.parquet"
        if target.exists():
            continue
        df = client.dataset(name)
        if df.empty:
            print(f"  {name}: пусто")
            continue
        df.to_parquet(target, index=False)
        net.record(cfg.path("manifest"), target, f"{cfg['sources']['sberindex_api']} /dataset/v1/{name}")
        print(f"  {name}: {len(df):,} строк")
