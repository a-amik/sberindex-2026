"""Чтение отдельных файлов из большого zip по HTTP без скачивания целиком.

Zip хранит оглавление в конце: читаем хвост диапазоном байтов, разбираем центральный
каталог (с поддержкой zip64), а нужный файл берём своим диапазоном и распаковываем.
Архивы «Если быть точным» по 1 ГБ так отдают часть одного субъекта за секунды.

    from tools.remote_zip import RemoteZip
    z = RemoteZip(url); z.names(); z.read(name) -> bytes
"""
from __future__ import annotations

import struct
import zlib

import requests


class RemoteZip:
    def __init__(self, url: str, session: requests.Session | None = None):
        self.url, self.s = url, session or requests.Session()
        h = self.s.head(url, allow_redirects=True, timeout=60)
        self.size = int(h.headers["content-length"])
        self.entries = self._directory()

    def _get(self, start: int, end: int) -> bytes:
        r = self.s.get(self.url, headers={"Range": f"bytes={start}-{end}"}, timeout=300)
        r.raise_for_status()
        return r.content

    def _directory(self):
        tail = self._get(max(0, self.size - 70000), self.size - 1)
        i = tail.rfind(b"PK\x05\x06")
        if i < 0:
            raise ValueError("нет EOCD")
        n, cd_size, cd_off = struct.unpack("<HII", tail[i + 10:i + 20])
        if cd_off == 0xFFFFFFFF or n == 0xFFFF or cd_size == 0xFFFFFFFF:
            j = tail.rfind(b"PK\x06\x06")
            n, cd_size, cd_off = struct.unpack("<QQQ", tail[j + 32:j + 56])
        cd = self._get(cd_off, cd_off + cd_size - 1)
        out, p = {}, 0
        while p < len(cd) and cd[p:p + 4] == b"PK\x01\x02":
            method, csize, usize, nlen, xlen, clen = struct.unpack("<H", cd[p + 10:p + 12])[0], *struct.unpack("<II", cd[p + 20:p + 28]), *struct.unpack("<HHH", cd[p + 28:p + 34])
            off = struct.unpack("<I", cd[p + 42:p + 46])[0]
            name = cd[p + 46:p + 46 + nlen].decode("utf-8", "replace")
            extra = cd[p + 46 + nlen:p + 46 + nlen + xlen]
            if 0xFFFFFFFF in (csize, usize, off):
                q = 0
                while q + 4 <= len(extra):
                    tag, ln = struct.unpack("<HH", extra[q:q + 4]); body = extra[q + 4:q + 4 + ln]
                    if tag == 1:
                        vals = list(struct.unpack("<" + "Q" * (ln // 8), body[: (ln // 8) * 8])); k = 0
                        if usize == 0xFFFFFFFF: usize = vals[k]; k += 1
                        if csize == 0xFFFFFFFF: csize = vals[k]; k += 1
                        if off == 0xFFFFFFFF: off = vals[k]; k += 1
                    q += 4 + ln
            out[name] = (method, csize, usize, off)
            p += 46 + nlen + xlen + clen
        return out

    def names(self):
        return list(self.entries)

    def read(self, name: str) -> bytes:
        method, csize, usize, off = self.entries[name]
        head = self._get(off, off + 29)
        nlen, xlen = struct.unpack("<HH", head[26:30])
        start = off + 30 + nlen + xlen
        data = self._get(start, start + csize - 1)
        if method == 0:
            return data
        if method == 8:
            return zlib.decompress(data, -15)
        raise ValueError(f"метод сжатия {method}")
