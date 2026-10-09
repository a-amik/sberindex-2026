PY := .venv/bin/python

.PHONY: setup data dataset forecast grid lgbm-tune ensemble signals ahead cpd cases news shocks site all

setup:
	python3.12 -m venv .venv
	$(PY) -m pip install -q -r requirements-lock.txt

data:          ## загрузка из первоисточников, уже скачанное не качается
	$(PY) scripts/01_download.py

dataset:       ## панель, характеристики МО, соседи, внешние ряды, проверки
	$(PY) scripts/02_build_dataset.py

forecast:      ## бэктест: эталоны, Prophet, модели на панели (~30 мин на 10 ядрах), затем LightGBM,
               ## Chronos-2 в четырёх режимах и Chronos-Bolt — кандидаты ансамбля.
               ## LightGBM и torch — разными процессами: у каждого своя libomp, и в одном
               ## процессе на macOS они встают взаимоблокировкой на барьере OpenMP.
	$(PY) scripts/03_backtest.py
	$(PY) scripts/03_backtest.py --models lgbm
	$(PY) scripts/03_backtest.py --models chronos2_raw chronos2_raw_cl chronos2_dev chronos2_cov chronosbolt_dev chronosbolt_raw

grid:          ## чувствительность Prophet к настройкам на 1 200 рядах
	$(PY) scripts/03_backtest.py --grid

lgbm-tune:     ## подбор параметров LightGBM на окне отбора (цели до мая 2024) → results/metrics/lgbm_tuning.csv
	$(PY) scripts/43_lgbm_tune.py

ensemble:      ## ансамбль: выбор по целям до мая 2024 года, отчёт — точки с июня
	$(PY) scripts/04_ensemble.py

signals:       ## ансамбль с внешними сигналами и интервалами → results/forecasts/ensemble_signals.parquet
	$(PY) scripts/23_age_mo.py
	$(PY) scripts/35_final.py
	$(PY) scripts/37_strict.py

ahead:         ## прогноз вперёд 2025—2027 от декабря 2024: члены ансамбля, его свёртка, строгий итог с интервалами
	$(PY) scripts/17_forward.py --models snaive_growth panel_blend_sesseas_bytype panel_blend_ses_bytype prophet_default lgbm
	$(PY) scripts/17_forward.py --models chronos2_dev
	$(PY) scripts/17_forward.py --ensemble-only
	$(PY) scripts/37_strict.py --forward

shocks:        ## предсказание шоков: телеграм-каналы, разметка, шесть групп признаков против базы
	$(PY) scripts/31_telegram.py
	$(PY) scripts/33_telegram_events.py
	$(PY) scripts/36_shock_prediction.py
	$(PY) scripts/39_chs_markup.py

cpd:           ## детекторы точек изменений: полусинтетика и реальные данные
	$(PY) scripts/05_detect.py
	$(PY) scripts/38_chronos_detect.py

cases:         ## реальные кейсы и раннее предупреждение
	$(PY) scripts/06_real.py

news:          ## новости: разметка, согласование с данными, проверки
	$(PY) scripts/07_news.py

site:          ## данные сервиса web/public/data: признаки, чувствительности сценариев, устойчивость, выгрузка.
               ## Слои из данных, собранных руками (отрасли МО, люди, проверка 2025), пересобираются,
               ## только если их входы на месте; иначе остаются закоммиченные JSON.
	$(PY) scripts/build_features.py
	$(PY) scripts/18_sensitivity.py
	$(PY) scripts/19_shock_robustness.py
	$(PY) web/scripts/export_data.py
	@if [ -f data/processed/mo_industry_shares.parquet ]; then $(PY) web/scripts/export_industry.py; else echo "industry.json — из репозитория: нет data/processed/mo_industry_shares.parquet (36_shiftshare.py, 37_shiftshare_mo.py)"; fi
	@if [ -f data/external/bdmo/migration_2023.parquet ] && [ -f data/external/rosstat/age_mo_2023.parquet ]; then $(PY) web/scripts/export_people.py; else echo "people.json — из репозитория: нет миграции БД ПМО или возраста МО (41a—41c, 23_age_mo.py)"; fi
	@if [ -d results/forward_check ]; then $(PY) web/scripts/export_check2025.py; else echo "check2025.json — из репозитория: нет results/forward_check (33—35)"; fi

all: data dataset forecast grid ensemble signals ahead cpd cases news shocks site

deploy-web:    ## сборка web/ и заливка в бакет sberindex-amik-am (sberindex.amik.am)
	cd web && npm run build
	$(HOME)/yandex-cloud/bin/yc storage s3 cp --recursive web/dist/ s3://sberindex-amik-am/
