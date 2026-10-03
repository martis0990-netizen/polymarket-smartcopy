# Limitless: наблюдение, диагностика входа и сводка

Документ описывает реализацию после PR29, commit `a99662781d93a7cca44619f9d99da6ac9fb6d677`. Открытые дефекты и неподтверждённые свойства перечислены в [ревью](LIMITLESS_REVIEW_2026-10-03.md); следующие работы — в [роадмапе](LIMITLESS_ROADMAP.md).

## Цель и границы

SmartCopy исследует остаточное преимущество после обнаружения сделки. Наличие успешного кошелька или видимой ликвидности само по себе не является основанием для COPY. Эта часть собирает публичные наблюдения и показывает, какую котировку можно рассчитать по полученному стакану на условный бюджет 10 USDC. Она не создаёт ордеров, не подписывает транзакции, не держит приватных ключей и не рассчитывает прибыль follower.

Источник — Limitless. Polymarket в эту работу не входит. Отдельный независимый market capture/hourly paper эксперимент описан в [LIMITLESS_STRATEGY_STUDY.md](LIMITLESS_STRATEGY_STUDY.md); его сигналы и PnL нельзя приписывать копированию кошельков.

Окно сбора: 3 октября 2026 09:00 UTC / 12:00 МСК → 10 октября 2026 09:00 UTC / 12:00 МСК. GitHub schedules и dispatch могут опаздывать. Гарантии непрерывной работы нет; реальные gaps учитываются.

## Компоненты

| Компонент | Вход | Выход | Назначение |
|---|---|---|---|
| `limitless_smartcopy_probe.py` | public feed, истории трёх кошельков, REST books | observations/books JSONL, summary | Первичные наблюдения и времена |
| `limitless_entry_availability.py` | сегмент или observer ZIP archives | entry availability / aggregate JSON и Markdown | Первая попытка, глубина и ценовые различия |
| `limitless_probe_audit.py` | ZIP archives | feasibility audit | Старый full-week poll/proxy screen; не строгий fill gate |
| `limitless_wallet_profile.py` | ограниченная public history | profiles | Ретроспективная диагностика активности |
| `limitless_wallet_intents.py` | уже сохранённые profile requests | action traces | Последовательности действий с UNKNOWN inventory/strategy |
| observer workflow | schedule/push/manual; PR smoke | observer artifact, следующая работа | Ограниченный forward capture |
| final audit workflow | push/manual; observer explicit dispatch; cutoff schedule | manifest, aggregate, audit artifacts | Общая сводка и итоговое закрытие |

Никакой модуль здесь не превращает traces в подтверждённые ENTER/ADD/EXIT. Эта интеграция ещё не реализована.

## Сбор

Каждый цикл запрашивает `/feed/trading?audience=all&limit=30` и `/portfolio/{account}/history?limit=30` для фиксированной когорты. Запросы и связанные book fetches выполняются последовательно. Интервал 30 s — целевой интервал начала циклов; длинный цикл может занять больше. Public feed — discovery channel; его кошельки не добавляются в исходную когорту.

Для crypto buy с source time не раньше начала сегмента, известным slug и не закрытым market вызывается `/markets/{slug}/orderbook`. Family filter сейчас основан на title BTC/ETH/Bitcoin/Ethereum и 5 Min/15 Min/Hourly. Это кандидатный filter, а не полная проверка market identity, collateral или oracle.

Первый poll содержит и исторические события. Они остаются raw evidence, но entry aggregate не превращает historical first detection в fresh entry. Покупки, пришедшие после gap с source time до начала нового сегмента, также не получают задним числом доступность входа. Следовательно, fresh buy count не равен всем сделкам биржи за окно.

## Временные поля

| Поле | Значение |
|---|---|
| `occurred_at` / `source_time` | Время события, указанное источником |
| `first_seen_at` | Локальное время receipt ответа, содержащего событие |
| `request_started_at` | Локальное время начала запроса стакана |
| `fetched_at` книги | Локальное время receipt стакана |
| `detection_delay_s` | first_seen − source_time |
| `detection_to_request_s` | request_start − first_seen |
| `book_http_latency_s` | book_receipt − request_start |
| `source_to_book_receipt_s` | book_receipt − source_time |

Последний timestamp не является временем matching engine. API не гарантирует верхнюю границу свежести REST book. Detection delay включает публикацию источником, polling и network; компоненты пока не разделены. Несколько событий одного feed ответа получают одно receipt time, а их книги могут запрашиваться позже в разном порядке.

## Идентичность и сторона

Raw `id` сохраняет источник. Канонический ключ — wallet+UUID только для проверенного feed `clob:<UUID>:<profileId>` с совпадающим profileId и BOUGHT/SOLD; он совпадает с history tradeEventId. Другие идентификаторы не объединяются предположительно. Несколько fills одного order не становятся одним независимым намерением автоматически.

YES/NO labels используются напрямую. Up/Down переводятся в YES/NO только для Up or Down title. Numeric index0/1 используется только для BUY/SELL, двух outcomeTokenAmounts и non-group Up/Down. Claim, некорректный индекс и неоднозначный group остаются unknown. Межисточниковый конфликт в entry report пока не проверяется — открытый R1.

## Диагностическая котировка

Первый book attempt определяется среди полученных ответов после earliest detection. Ошибка первой попытки сохраняется. При последовательном текущем collector порядок receipt соответствует порядку попыток; будущий параллельный collector потребовал бы явного attempt ordinal.

Для YES читаются asks. Для NO используются YES bids с ценой `1-p`, размер не меняется. `size / 1e6` даёт число shares. Уровни сортируются по возрастанию цены покупки, quantities округляются вниз до 1e-6 share, общий расход ограничен 10. Невалидные/nonfinite значения, отрицательный размер, locked/crossed book исключаются. `tokenId` должен присутствовать; полная привязка к source market ещё не валидируется (R2).

- `VWAP = spent / gross_shares`.
- `gap = VWAP − source_gross_price`.
- `capacity_at_source = Σ(price × shares)` по уровням с price ≤ source_price.
- `ten_usdc_available_at_or_below_source` означает capacity ≥10 при ограничении каждой цены.
- Иллюстрация 3%: `net_shares = gross_shares × 0.97`; `effective_cost = VWAP / 0.97`.

3% не является установленным fee schedule конкретного follower, а source price не содержит подтверждённой одинаковой fee basis. В диагностике нет approved max price или утверждённой fair probability. Поддержка бюджета на дорогих уровнях — это не разрешение торговать.

## Статусы и интерпретация

| Статус | Что известно |
|---|---|
| `DEPTH_SUPPORTS_10_USDC_QUOTE` | Арифметически хватает отображённой глубины; исполнения нет |
| `INSUFFICIENT_VISIBLE_DEPTH` | Видимой глубины на весь бюджет недостаточно |
| `FIRST_BOOK_REQUEST_FAILED` | Первая сохранённая попытка завершилась ошибкой |
| `NO_BOOK_CAPTURED` | Книга не сохранена; причина не превращается в fill |
| `UNKNOWN_OUTCOME` | Сторона не определена |
| `INVALID_SOURCE_OBSERVATION_TIME` | Source time позже observer time |
| `UNVERIFIED_POST_DETECTION_REQUEST` | Нет подтверждённого причинного request-start |
| `INVALID_OR_UNVERIFIED_BOOK` | Не пройдены проверки схемы/значений книги |

R1–R4 показывают, что слово supports относится к текущему ограниченному набору проверок. Оно не означает полную валидацию всех данных.

## Артефакты

| Файл | Содержимое |
|---|---|
| `observations.jsonl` | observation, poll_success, request_error; исходные raw записи |
| `books.jsonl` | event_id, slug, request/receipt, raw book либо error; файл может отсутствовать |
| `summary.json` | Метрики отдельного сегмента; не каноническая сводка всех запусков |
| `entry_availability.json/.md` | Диагностика текущего сегмента |
| `observer_manifest.jsonl` | run ID, commit SHA, event/status и download status основных архивов |
| `limitless_entry_aggregate.json/.md` | Дедупликация между сегментами, wallet/scope metrics, coverage и ошибки |
| `limitless_final_audit.json` | Старый full-week feasibility/proxy screen, отдельно от строгой диагностики |

Workflow сохраняет artifacts на 14 дней. До expiry надо сохранить raw archives, manifest и важные отчёты. Summary/Markdown не заменяют raw evidence. CLI принимает любые переданные ZIP: main-only provenance обеспечивается workflow manifest, а не самой функцией aggregate. Для ручного запуска набор архивов проверяется отдельно.

## Знаменатели и покрытие

Current depth fraction = supported quotes / canonical fresh buys данной scope. Старые unverified records входят в знаменатель. Отдельную долю среди timing-verifiable records нужно указывать вручную вместе с точными status counts; автоматическое поле для неё ещё не добавлено (R5).

Coverage — union `[poll_receipt−30s, poll_receipt]` успешных history polls по каждому из трёх кошельков, обрезанная study start/as-of. Это договорённая оценка poll credit, не доказательство complete event coverage. Interim использует прошедшее окно; legacy gate делит на полную неделю. Нельзя сравнивать их проценты без указания окна. Недоступные и unfinished artifacts не дают credit. Same-market trades, raw fills, snapshots и 60s proxy не являются независимыми наблюдениями стратегии.

## Запуск и диагностика

Наблюдение без ордеров:

```bash
python3 research/limitless_smartcopy_probe.py --minutes 3 --interval 30 --until 2026-10-10T09:00:00Z --out limitless_probe
python3 research/limitless_entry_availability.py --out limitless_probe
```

Общая сводка по проверенным основным ZIP с явным as-of:

```bash
python3 research/limitless_entry_availability.py --archives archives/*.zip --as-of 2026-10-03T16:44:17Z --out limitless_entry_aggregate.json
python3 research/limitless_probe_audit.py archives/*.zip --out limitless_final_audit.json
```

Сначала проверять SHA/run IDs, наличие raw files и download statuses; затем ошибки/unknowns, покрытие и знаменатели; только после этого — quote metrics. Действующий route после PR29: observer upload → explicit main audit dispatch. Его end-to-end acceptance на момент ревью pending. До cutoff dispatch выполняет промежуточный audit; после cutoff workflow также агрегирует независимые captures и при успехе отключает final schedule.

## Что пока отсутствует

Нет подтверждённой стратегии кошелька, полного начального inventory, независимых ENTER/ADD/EXIT, net follower PnL, calibrated residual-edge filter, точной модели queue/funding/cancellations, выполненных реальных заявок или разрешения на live. Ограничения не устраняются более частым polling без измерения причин задержки.
