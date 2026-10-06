# Limitless maker: стимулы и секундный Binance reference

**Срез официальных страниц:** 2026-10-05 22:20 UTC. Это исследование публичных
BTC/ETH рынков; ни ключей, ни подписей, ни ордеров. Frozen hourly/inventory-v2,
holdout, график основного capture и его workflow concurrency не меняются.

## Подтверждённая экономика

| Компонент | Официальное правило | Статус для нашей диагностики |
| --- | --- | --- |
| Maker trading fee | 0, когда лимитная заявка стоит в книге и исполняется как maker | Можно исключить только для подтверждённого maker fill; `postOnly` понадобится в будущем executor, который здесь отсутствует |
| Maker Rebate | USDC из дневного фонда, пропорционально eligible fee-generating maker fills; невыполненная заявка не получает credit | [Публичная таблица](https://limitless.exchange/rewards?view=rebates) показывает 30% для BTC/ETH 5m/15m. Для hourly по доступному срезу не подтверждено: `UNKNOWN`, не 0% и не доход |
| LP Rewards | Минутная оценка стоящих заявок по размеру и расстоянию от midpoint; условия и бюджет динамичны для каждого рынка | В старом [screen](LIMITLESS_MAKER_RESULTS_2026-10-03.md) 10 shares ниже minSize на 422/422 anchors; 0 подтверждённых выплат, не переносить на иной размер |

Официальные источники: [fees](https://docs.limitless.exchange/user-guide/fees),
[maker rebates](https://docs.limitless.exchange/user-guide/maker-rebates),
[LP rewards](https://docs.limitless.exchange/user-guide/lp-rewards). 30% — доля
eligible taker fee pool с возможными referral/creator deductions и ежедневной
pro-rata выплатой, **не** 30% от цены или PnL наших сделок. У hourly нет проверенного
market-specific rate в этом срезе. Проверять конкретный slug и правила на момент
будущего fill; rewards в paper PnL сейчас равны `null`, а не ожидаемой прибыли.

## Новый независимый reference в существующем capture

`limitless_binance_fast_reference.py` подключается только к публичному
`wss://data-stream.binance.vision/stream?streams=btcusdt@kline_1s/ethusdt@kline_1s`.
Официальная [схема Binance](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md)
описывает 1s kline и время `E`, `k.t`, `k.T`, цену `k.c`, признак завершения `k.x`.
Каждый полученный валидный envelope попадает в уже существующий
`capture.jsonl.gz` как `binance_fast_reference`, с местными `observed_at` и
`monotonic_ns`. Raw Binance payload сохраняется; publisher time не приравнивается
ко времени доступности. `binance_fast_connect/disconnect/error/invalid/gap` и
`out_of_order` показывают разрывы. `gap.unobserved_seconds` — отсутствие полученной
секундной свечи, **не** подсчёт потерянных трейдов. Без точного сопоставления
таймштампов Binance/Limitless нельзя объявлять чистую сетевую задержку.

Поток стартует параллельно текущему collector, только если передан
`--fast-reference`. Workflow включает флаг при том же графике, длительности,
капe 256 MiB и archive retention; `summary.json.maker_reference_protocol`
отделяет новые архивы от старых. Протокол не добавляет цены в HourlyPaper,
InventoryPaper, решение, комиссия, размер или paper ledger не меняются.
Секундные данные впервые доступны только **после первого обновлённого main
артефакта**; исторические 1/5s пары не восстанавливаются из минутных свечей.

Следующий ограниченный анализ: фактическое покрытие raw receipt intervals,
совпадение с одновременными WS book frames, изменение Binance на фиксированных
1/5s горизонтах в независимых часовых кластерах. Нет maker order lifecycle,
очереди или подтверждённого исполнения: `fill_probability=null`, `PnL=null`,
rebates/LP=`null`. Не считать касание цены исполнением, не выбирать прибыльный
горизонт по новым данным, не смешивать 15m Chainlink с hourly Binance outcome.
