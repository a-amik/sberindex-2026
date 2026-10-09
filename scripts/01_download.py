"""Шаг 1. Загрузка данных из первоисточников.

    python scripts/01_download.py                     все источники
    python scripts/01_download.py --only hackathon    названные
    python scripts/01_download.py --only news         заголовки лент (~1,5 ч, кэш по дням)

Уже скачанное не качается повторно; манифест data/manifest.json хранит
адрес, размер, sha256 и дату каждого файла.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sbi import config  # noqa: E402
from sbi.sources import hackathon, misc, news, rosstat, sberindex_api  # noqa: E402

STEPS = {
    "hackathon": hackathon.download,
    "sberindex": sberindex_api.download,
    "rosstat": rosstat.download,
    "cbr_calendar": misc.download,
    "weather": misc.download_weather,
    "news": news.download,
}


def main():
    cfg, args = config.cli(__doc__, lambda ap: ap.add_argument("--only", nargs="*", choices=list(STEPS), default=list(STEPS)))
    for name in args.only:
        print(f"· {name}")
        STEPS[name](cfg)


if __name__ == "__main__":
    main()
