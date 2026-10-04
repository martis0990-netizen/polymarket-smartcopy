# Первичная разметка состояний рынка: 4 октября 2026

**Результат: diagnostic реализован и технически проверен; полная иерархия старших ТФ пока INSUFFICIENT_DATA.** Это не новая торговая модель, не доказательство разворота/прибыльности и не изменение действующего paper-сбора.

Исходная main база: `61d9cbb819725c2296c38af9f6643ac0bcbed5bc`. Данные: фиксированный прежний срез, state artifact **11298028349**, run **37185875778**, до **2026-10-04 08:23:26.608101 UTC / 11:23:26 МСК**. Новые более поздние jobs в этот сравнительный срез не добавлялись. Analysis проведён после просмотра outcomes: весь срез — discovery.

## Что сделано

- [Протокол](LIMITLESS_MARKET_REGIME_PROTOCOL.md): состояния UP/DOWN/RANGE/TRANSITION/UNKNOWN, protected anchors, причинные confirmed pivots, 3-point candidate и fourth-reaction range, H4/H1 → M15 → M5/M1, отдельные availability и event times.
- `limitless_market_regime.py`: самостоятельная offline CLI без сети и production imports/hooks. Использует один cumulative hourly state, проверяет main run metadata и ZIP SHA256, собирает полные старшие свечи из уже полученных минут, сохраняет конфликты и UNKNOWN.
- На каждый decision: состояния всех пяти ТФ, protected levels, range/candidate, последние события, H4/H1 и H1/M15 отношения, непрерывная позиция в подтверждённом диапазоне, original p/open/reference и время до конца часа.
- Целевые тесты включены в **существующий CI** через pytest wrapper; workflow YAML не меняется. Ни текущая модель, ни probability/entry/fees/thresholds/holdout/collection schedule не изменены.

## Источники и полнота

Проверены **22 completed-success main capture ZIP**, non-pull_request. Все ZIP SHA256 совпали с GitHub artifact digest; head SHA/run ids сверены. Содержат **7 419** Binance M1 response. По каждому BTCUSDT/ETHUSDT есть **1 345 уникальных номинально закрытых минут**, от 3 октября **09:58 UTC** до 4 октября **08:22 UTC** — 22 часа 25 минут. Это восстановленные price history данные; длительность не означает отсутствие job/observer gaps.

На времени самих 37 решений максимально доступно **4 полных H4**, **21 H1**, **86 M15**. Минимальный барьер протокола — 16 непрерывных баров плюс необходимые подтверждённые swings/close break. Он не гарантирует, что режим можно установить. Поэтому ни один из этих 37 decisions пока не имеет полной READY H4/H1 иерархии.

## Фактическая разметка

**37 условий, 19 UTC hour clusters, discovery37/holdout0.** Зависимость BTC/ETH в одном часу сохраняется; это не 37 независимых часов. В counts включены и NO_TRADE, и фактические решения с paper entry, без отбора по прибыли.

| ТФ | UP | DOWN | RANGE | TRANSITION | UNKNOWN |
|---|---:|---:|---:|---:|---:|
| H4 | 0 | 0 | 0 | 0 | 37 |
| H1 | 0 | 0 | 0 | 0 | 37 |
| M15 | 0 | 9 | 0 | 2 | 26 |
| M5 | 11 | 2 | 1 | 8 | 15 |
| M1 | 7 | 3 | 0 | 12 | 15 |

H1 причины UNKNOWN: 16 недостаточного warmup, 6 без достаточной подтверждённой структуры, 15 с известным conflict источника. Для H4 дополнительно есть ранние decisions без полного последнего ожидаемого бара. Это консервативная классификация данной версии; UNKNOWN не является утверждением, что визуально отсутствовал тренд.

Единственный RANGE в таблице — **локальный M5 BTC**, decision 3 октября **14:30:16 UTC / 17:30:16 МСК**. Замороженные границы **84 785.50–84 921.66**; reference находится на **29.74%** ширины от нижней границы. Это не H1/H4 консолидация и не торговый сигнал. Остальные mixed/равные swings не были автоматически названы диапазонами.

## Обнаруженные расхождения закрытых свечей

В четырёх ETH M1 ответах OHLC с одинаковым open time отличается только **close на $0.01**:

| Свеча UTC | Первый close | Последующий close | Первое receipt после nominal close | Следующая отличающаяся версия |
|---|---:|---:|---:|---:|
| 3 октября 16:13 | 2679.96 | 2679.95 | 0.886 s | 19.121 s |
| 3 октября 19:26 | 2682.99 | 2683.00 | 1.100 s | 18.369 s |
| 4 октября 01:04 | 2692.59 | 2692.58 | 1.294 s | 18.535 s |
| 4 октября 01:36 | 2692.72 | 2692.73 | 1.003 s | 21.889 s |

Все восемь raw response rows независимо перечитаны из ZIP по artifact/line, fingerprint совпал. Nominal candle close предшествует request-start; receipt следует за запросом. Не делаем вывод, какая внешняя техническая причина объясняет расхождение. Малый размер не даёт права молча выбирать удобную версию.

В **15 decisions** конфликт уже был известен к decision time. Diagnostic v1 консервативно делает все frames UNKNOWN при любом известном conflicting minute в доступной истории; даже старый conflict может заблокировать более свежую геометрию. Это сознательный ограничительный критерий, а не измерение числа испорченных сделок. Других invalid response/envelope errors — **0**. Status RECONCILED_DIAGNOSTIC_ONLY означает, что источники/карантин учтены; не согласованность всех OHLC и не экономический PASS.

Original p_up, opening, reference и model status всех **37** решений совпали с прежним исследованием. Замороженные решения использовали свои исходные archived response; этот новый merge длинной истории не заменяет их источники и не пересчитывает PnL. Для проигрышного ETH нового подтверждённого HTF-вывода нет: top-down UNKNOWN, локальная геометрия не является основанием задним числом исключить вход.

## Проверка и воспроизведение

**10 целевых tests PASS**: earliest receipt, конфликт после его наблюдения, future/partial candle exclusion, valid OHLC/times, missing bars/gaps, protected anchor перенос только при BOS, wick vs close, 3-point candidate/fourth confirmation, mirrored trend, every-prefix invariance. Существующий pytest CI запускает тот же набор. Локально pytest отсутствовал; wrapper дополнительно выполнен напрямую Python, без установки пакетов.

При первоначальном ревью найден и исправлен конкретный lookahead: inside-box проверка могла читать будущие bars. Теперь только `bars[:i+1]`; every-prefix тест подтверждает, что последующий выход не стирает прежний RANGE_CANDIDATE/RANGE. На реальных archived ETH candles независимо проверены **121 M1**, **24 M5**, **8 M15** префиксов; событийные журналы и snapshots не переписались.

Независимый Reviewer: **PASS_DIAGNOSTIC_ONLY**. Повторно воспроизведена R1 fixture, 10 tests PASS, SHA256 реализации совпал с evidence; отдельно подтверждён raw ETH conflict artifact11279146210 lines36736/37105 с обоими fingerprints. Невоспроизведённых претензий не выдаём за закрытые критерии; полная HTF готовность и экономическое преимущество остаются неподтверждёнными.

Основной evidence: [limitless_market_regime_2026-10-04.json](evidence/limitless_market_regime_2026-10-04.json). В нём run/artifact/hash, source as-of, implementation SHA256, все 37 snapshots, state counts и варианты OHLC с provenance. Дополнительная проверка: [limitless_market_regime_validation_2026-10-04.json](evidence/limitless_market_regime_validation_2026-10-04.json): SHA256 основного evidence, восемь raw conflict candles, source fingerprints и real-prefix checks.

```bash
python -m unittest discover -s research -p 'test_limitless_market_regime.py' -v
python research/limitless_market_regime.py \
  --manifest downloaded-main-capture-manifest.json \
  --state-zip downloaded-11298028349.zip \
  --output regime-report.json
```

Manifest — список `{artifact: {id, digest, workflow_run: {id, head_sha}}, run: {id, name, head_branch, head_sha, event, status, conclusion}, file: {path}}`. Paths указывают на скачанные ZIP; metadata/digests опубликованы в evidence. Неправильный digest, PR job или state вне manifest => UNRECONCILED/report=null. Не запускать v1 inventory diagnostic на v2 evidence; этот модуль вовсе не выполняет inventory replay.

## Следующие действия в рамках согласованного сбора

1. Получить достаточно **уже собираемой** истории старших ТФ. Позднее historical backfill может помочь визуальной проверке, но не становится earlier decision-time evidence.
2. Отдельно выяснить finality/версии nominally closed Binance REST candles. В этой версии конфликт сохраняется; нет скрытого выбора final close, задержки или нового warmup по выгодному результату. Любое изменение определения получает новую документированную версию.
3. На ещё не просмотренных outcomes 6–10 октября выполнить описанный secondary diagnostic с явными UNKNOWN/coverage, отдельно от прежнего primary M1 contrast. Не выбирать лучший TF/режим по прибыли. Готовность HTF проверяется фактически.
4. Только при воспроизводимой связи с ошибкой вероятности обсуждать новую probability model и её отдельный untouched test. Passive maker, исполнение, fees/очередь и положительный edge этим исследованием не подтверждены.

Код основной paper-системы, state, существующие workflows/cron и график сбора сохранены. Новых автоматизаций нет.
