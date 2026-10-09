"""HTTP с проверкой TLS.

Сайты Сбера, СберИндекса и Росстата подписаны НУЦ Минцифры, а sberindex.ru
не отдаёт промежуточный сертификат. Проверку не выключаем: собираем bundle
из certifi и публичных сертификатов Минцифры из certs/.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import certifi
import requests

from .config import ROOT

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"


def ca_bundle() -> str:
    target = ROOT / "data" / "ca-bundle.pem"
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        parts = [Path(certifi.where()).read_text()]
        parts += [p.read_text() for p in sorted((ROOT / "certs").glob("*.pem"))]
        target.write_text("\n".join(parts))
    return str(target)


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = UA
    s.verify = ca_bundle()
    return s


def fetch(s: requests.Session, url: str, *, tries: int = 6, timeout: int = 300, **kw) -> requests.Response:
    for attempt in range(tries):
        try:
            r = s.get(url, timeout=timeout, **kw)
            if r.status_code == 429:   # сервер просит притормозить: ждём дольше обычного
                if attempt == tries - 1:
                    r.raise_for_status()
                time.sleep(int(r.headers.get("Retry-After", 30 * (attempt + 1))))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt)
    raise requests.HTTPError(f"{url}: сервер не отвечает после {tries} попыток")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record(manifest: Path, path: Path, url: str) -> None:
    """Пишет в манифест адрес, размер, sha256 и дату загрузки файла."""
    data = json.loads(manifest.read_text()) if manifest.exists() else {}
    rel = str(path.relative_to(ROOT))
    data[rel] = {
        "url": url,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "downloaded": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(dict(sorted(data.items())), ensure_ascii=False, indent=2) + "\n")
