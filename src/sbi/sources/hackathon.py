"""Датасет конкурса и справочник муниципальных образований.

Имена файлов в архиве конкурса записаны в cp866 без флага UTF-8, поэтому
архив распаковывается вручную, с перекодировкой имён.
"""
from __future__ import annotations

import io
import subprocess
import zipfile
from pathlib import Path

from .. import net


def _unzip_cp866(blob: bytes, out: Path) -> list[Path]:
    files = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for info in z.infolist():
            name = info.filename
            if not info.flag_bits & 0x800:
                try:
                    name = name.encode("cp437").decode("cp866")
                except UnicodeError:
                    pass
            if name.endswith("/"):
                continue
            dest = out / Path(name).name
            dest.write_bytes(z.read(info))
            files.append(dest)
    return files


def download(cfg) -> None:
    raw = cfg.path("raw") / "hackathon"
    raw.mkdir(parents=True, exist_ok=True)
    manifest = cfg.path("manifest")
    s = net.session()

    zip_path = raw / "hackathonlicence.zip"
    if not zip_path.exists():
        url = cfg["sources"]["hackathon_zip"]
        zip_path.write_bytes(net.fetch(s, url).content)
        net.record(manifest, zip_path, url)
    if not (raw / "consumption.parquet").exists():
        for f in _unzip_cp866(zip_path.read_bytes(), raw):
            net.record(manifest, f, cfg["sources"]["hackathon_zip"])

    rar = raw / "t_dict_municipal.rar"
    if not rar.exists():
        url = cfg["sources"]["municipal_dict"]
        rar.write_bytes(net.fetch(s, url).content)
        net.record(manifest, rar, url)
    xlsx = raw / "t_dict_municipal_districts.xlsx"
    if not xlsx.exists():
        # bsdtar (libarchive) есть в macOS и в большинстве Linux
        subprocess.run(["bsdtar", "-xf", str(rar), "-C", str(raw)], check=True)
        for f in raw.glob("t_dict_municipal_districts*"):
            net.record(manifest, f, cfg["sources"]["municipal_dict"])
