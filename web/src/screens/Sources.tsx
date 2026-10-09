import { Card, Table } from '../components/ui'
import { META } from '../data/real'
import { fmt0 } from '../lib/util'

export const SOURCES_NAV: [string, string][] = [['src-rel', 'Версия модели'], ['src-ext', 'Внешние источники'], ['src-tab', 'Собранные таблицы'], ['src-res', 'Результаты расчётов'], ['src-upd', 'Как обновить']]

// Источники, которые не записаны в манифест загрузок: описаны по таблицам, в которые вошли.
const OTHER = [
  ['Ключевая ставка ЦБ', 'national.parquet', 'Ставка по месяцам с 2018 года — для сценариев'],
  ['Производственный календарь', 'national.parquet', 'Рабочие и выходные дни — для сценария праздников и Chronos-2'],
  ['Погода NASA POWER', 'features.parquet', 'Температура и осадки по муниципалитетам — для проверки реакции на погоду'],
  ['Новости «Интерфакса»', 'news_annotated.parquet', '215 тыс. заголовков с 2022 года: разметка по типу события, муниципалитету и субъекту'],
  ['OpenStreetMap', 'cities.json', 'Контуры районов Москвы и округов Петербурга (© участники OpenStreetMap, ODbL)'],
]
const NAME: Record<string, string> = { sberindex: 'API СберИндекса', hackathon: 'Данные конкурса СберИндекса' }
const kb = (b: number) => (b > 1e6 ? `${fmt0(b / 1e6)} МБ` : `${fmt0(b / 1e3)} КБ`)

export function SourcesBody() {
  const S = META.sources
  const R = META.release
  return (
    <>
      {R && (
        <Card id="src-rel" title="Версия модели" sub="Какой прогноз показывает сервис: единое описание для проверки на истории, прогноза вперёд и интерфейса">
          <Table rows={[
            ['Модель', `${R.model_id}: итоговый прогноз — ансамбль с поправкой общей динамики группы на шагах 4—12; данные следующего месяца не используем`],
            ['Состав ансамбля', `${R.members.join(' + ')} — ${R.how === 'median' ? 'медиана' : R.how === 'mean' ? 'среднее' : 'среднее геометрическое'}${R.force_include.length ? `; обязательная модель: ${R.force_include.join(', ')}` : ''}`],
            ['Периоды проверки', `прогнозируемые месяцы не позже ${R.select_last_target}; итоговая проверка — даты прогноза с ${R.report_from}`],
            ['Последние данные', `${R.data_last}; прогноз вперёд от ${R.forward_origin}: ${R.forward_targets.join(' — ')}`],
            ['Поправки', R.adjustments.join('; ')],
            ['Интервалы', `${R.intervals}; доля фактических значений в интервале 90 % при проверке на истории по шагам 1—6: ${R.coverage90_by_step.map((c) => Math.round(c * 100)).join(' / ')} %`],
            ...(R.adjustment_tested ? [['Где проверено', R.adjustment_tested]] : []),
            ...Object.entries(R.files).map(([f, h]) => [f, `sha256 ${h}`]),
          ].map((r, i) => [r[0], r[1], i] as [string, string, number])} sort={['n', 1]} cols={[
            { key: 'n', title: 'Что', get: (r) => r[2], render: (r) => r[0] },
            { key: 'v', title: 'Значение', get: (r) => r[1], render: (r) => (r[0].includes('/') ? <code>{r[1]}</code> : r[1]) },
          ]} />
        </Card>
      )}
      <Card id="src-ext" title="Внешние источники" sub={`Сведения из списка загрузок; данные для экрана собраны ${S.exported}`}>
        <Table rows={S.external} sort={['n', 1]} cols={[
          { key: 'n', title: 'Источник', get: (r) => NAME[r.name] ?? r.name },
          { key: 'f', title: 'Файлов', num: true, get: (r) => r.files },
          { key: 'b', title: 'Объём', num: true, get: (r) => r.bytes, render: (r) => kb(r.bytes) },
          { key: 'd', title: 'Загружено', get: (r) => r.date },
        ]} />
        <div style={{ height: 12 }} />
        <Table rows={OTHER} sort={['n', 1]} cols={[
          { key: 'n', title: 'Источник', get: (r) => r[0] },
          { key: 't', title: 'Файл', get: (r) => r[1], render: (r) => <code>{r[1]}</code> },
          { key: 'w', title: 'Зачем', get: (r) => r[2] },
        ]} />
      </Card>
      <Card id="src-tab" title="Собранные таблицы" sub="По каким таблицам сервис считает прогноз: панель, справочник, ряды субъектов и РФ, признаки, соседи, новости">
        <Table rows={S.built} sort={['f', 1]} cols={[
          { key: 'f', title: 'Таблица', get: (r) => r.file, render: (r) => <code>{r.file}</code> },
          { key: 'r', title: 'Строк', num: true, get: (r) => r.rows, render: (r) => fmt0(r.rows) },
          { key: 'd', title: 'Собрана', get: (r) => r.date },
        ]} />
      </Card>
      <Card id="src-res" title="Результаты расчётов" sub="Каким шагом расчёта получены прогнозы, сигналы детекторов и результаты проверок реакции и устойчивости">
        <Table rows={S.results} sort={['f', 1]} cols={[
          { key: 'f', title: 'Файл', get: (r) => r.file, render: (r) => <code>{r.file}</code> },
          { key: 'b', title: 'Шаг', get: (r) => r.by, render: (r) => <code>{r.by}</code> },
          { key: 'd', title: 'Посчитан', get: (r) => r.date },
        ]} />
      </Card>
      <Card id="src-upd" title="Как обновить" sub="Из корня репозитория, по порядку">
        <ol className="muted" style={{ margin: 0, paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13.5 }}>
          <li>Загрузить источники: <code>python scripts/01_download.py</code></li>
          <li>Собрать панель и признаки: <code>python scripts/02_build_dataset.py</code>, <code>python scripts/build_features.py</code></li>
          <li>Проверить модели на истории и собрать ансамбль: <code>python scripts/03_backtest.py</code>, <code>python scripts/04_ensemble.py</code></li>
          <li>Запустить детекторы и собрать новости: <code>python scripts/05_detect.py</code>, <code>python scripts/07_news.py</code></li>
          <li>Собрать итоговый прогноз и интервалы: <code>python scripts/37_strict.py</code>; прогноз вперёд: <code>python scripts/17_forward.py</code>, <code>python scripts/37_strict.py --forward</code> (<code>make ahead</code>)</li>
          <li>Проверить реакцию моделей и устойчивость: <code>18_sensitivity.py</code>, <code>19_shock_robustness.py</code></li>
          <li>Выгрузить данные для интерфейса: <code>python web/scripts/export_data.py</code>, затем <code>docker compose up --build</code></li>
        </ol>
      </Card>
    </>
  )
}
