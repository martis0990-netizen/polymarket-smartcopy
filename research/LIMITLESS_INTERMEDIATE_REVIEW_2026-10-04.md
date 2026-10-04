# Limitless: промежуточная проверка модели и облачных цепочек

Срез market capture: **4 октября2026,09:18UTC /12:18МСК**, aware as-of09:25UTC. Observer aggregate имеет собственный срез08:55:42UTC, discovery profile —02:52:36UTC. Проверенный main source `d805d94e7870ae0f9e1c2a3014d5c33c2b02d5f1`. [Machine evidence, run/artifact/digest и отчёты](evidence/limitless_intermediate_review_2026-10-04.json).

**Техническая сверка: PASS в указанном scope. Экономический вывод: INSUFFICIENT_DATA.** Нет воспроизведённой ошибки, требующей изменения работающего кода. Стратегия, thresholds, fees, cohort, holdout, concurrency и графики не изменены.

## Новый фактический результат

| Система | Закрытые позиции/сделки | Накопительный paper PnL USDC |
|---|---:|---:|
|Independent inventory-v2,100USDC funded|6|**+9.718285584**|
|Frozen hourly model benchmark, без funding ledger|8|+52.406003635|
|Frozen constant50 benchmark, без funding ledger|35|+22.324797045|

V2 cash109.718285584, open positions0, open cost basis0; шесть HOLD, SELL0/COMPLETE_PAIR0. Managed-minus-seed-hold=0. По discovery шесть matched conditions / пять resolved hourly clusters. Последний сегмент добавил одну v2 закрытую позицию с **+8.842479300USDC**. Это новый paper outcome, не доход реального исполнения.

Hourly:42conditions seen /21hour clusters;39scored decisions,31NO_TRADE+8SETTLED,3MISSED_DECISION_WINDOW. Brier0.233189478 против0.25. Holdout0; он начинается6 октября00:00UTC. Старые первые constant50 покупки больше не оставлены как «итог0»: в latest checkpoint их наблюдаемые settlement входят в накопительный результат35settled. Все cumulative отчёты дедуплицированы по condition, не складывались.

Разница между большим hourly PnL и v2 не исчезла: **+42.687718051USDC hourly относится к двум pre-v2 benchmark сделкам**. Legacy inventory v1 исключён. Большая старая сделка+51.071221619 остаётся источником концентрации. Новый положительный v2 outcome не делает выборку достаточной и не подтверждает пользу управления.

## Состояние и источники модели

Main capture [37188767283](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37188767283), artifact11298753953. Его SHA256 совпал с artifact digest. Сверены23 main checkpoint reports текущим HourlyPaper, immutable decision/terminal episode fields между соседними архивами и полный archive_report: конфликтов condition lineage нет. PR smoke не включены.

Последний ZIP отдельно и пара с предыдущим проверены текущим InventoryPaper archive_report с aware as-of: RECONCILED_PAPER_ONLY. Saved hourly/inventory reports точно воспроизведены. Inventory started_at сохраняется, legacy history неизменна, непустая raw source-fingerprint последовательность предыдущего checkpoint — префикс следующей. Ledger cash/cost/quantity/PnL/payout пересчитан existing validator; cumulative raw sources совпадают с fingerprints.

Два новых midpoint решения BTC/ETH08:30UTC восстановлены из raw Binance1m/1h перед book: совпадают hourly open, p_up и допустимые закрытые warmup свечи. Первая допустимая post-delay entry попытка сопоставлена с raw book/request start; не использована выгодная поздняя замена. Older37 inputs уже независимо воспроизведены в [полном диагностическом отчёте](LIMITLESS_INDICATOR_ALL_FORECASTS_2026-10-04.md).

Frozen hourly-v1 сохраняет documented missing-frame retry ограничение, поэтому его собственные fills/PnL не подтверждают eligibility v2. V2 independently first-attempt policy отдельно сверена. Это ожидаемое сохранённое ограничение, не новая исправляемая без версии ошибка. Новые наблюдаемые payouts бинарные; реального split-settlement эпизода эта проверка не доказывает.15m Chainlink TWAP60 остаются collection-only и не оценены Binance spot моделью.

REST depth assumed executable, очередь/кэш/гонки и реальные fees аккаунта не воспроизведены. Buy3% в shares, sell1.5%, hypothetical merge0.01 остаются фиксированными предположениями. SELL/PAIR runtime ещё отсутствуют.39conditions и текущие hours ниже frozen достаточности; прибыльность не объявляется.

## Main observer и progress audit реально работают

Main observer [37187499376](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37187499376), artifact11299395397,08:00:14–08:55:14UTC:191observations,23fresh crypto trades,18book requests,1book error,0other request errors. Capture protocol **prospective-market-metadata-and-page-evidence-v1**; ZIP содержит observations/books/market_metadata/entry_availability.json/md. Текущий report_directory воспроизвёл saved entry report точно. Это main данные с decoder/identity diagnostics, не PR smoke.

Job111392475054 подтверждает successful Queue progress audit after artifact upload. Следующий [audit37190474028](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37190474028), job111401397919 success, artifact11299011178, manifest действительно содержит11299395397. Explicit observer→audit route принят; старые тексты pending workflow_run не описывают текущий статус. Independent-market final download в interim audit skipped штатно: промежуточный audit содержит wallet aggregate, не окончательный economic market review.

Aggregate08:55:42UTC:26main observer segments, archive/data errors0. Это принятый digest-verified published aggregate; все26 исходных ZIP в этой проверке заново не воспроизводились, independently recomputed только новый observer.

| Scope | Canonical fresh buys | Depth supports10USDC | Цена не выше источника | Data-qualified | Copy-eligible |
|---|---:|---:|---:|---:|---:|
|Fixed cohort|7|7|0|4|0|
|Discovery feed|741|402|83|233|0|

Discovery:204old request-start UNVERIFIED,8failed first attempts,127insufficient depth. Failed/missing observations не заменяются последующими quotes. Медиана discovery detection52.073с, gross quote deterioration5.177¢; fixed cohort34.404с/45.1¢. Это quote gaps, не fills/PnL или чистая стоимость latency. Деноминатор — buys, не independent intents; earliest canonical observation сохраняется, historical first detections исключены.

Elapsed fixed-wallet poll coverage91.15–93.87%, максимальные незачтённые gaps около45.7минут. Это не frozen full-week gate и не доказательство полной истории. Order-side groups и60s proxy episodes не квалифицированные intentions; lost-events count не установлен. Economic wallet comparison по paper contract остаётся **SPECIFIED_BUT_BLOCKED**.

## Discovery, профили и action traces

Последний проверенный completed main discovery [37172274035](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37172274035), eventworkflow_run, artifact11291658917,02:52UTC. Job111347673719 реально выполнил restore/discover/profile/trace/upload success. Это подтверждает исправленную capture-trigger цепочку в том запуске, но **свежий discovery после02:52UTC на момент проверки не подтверждён**. YAML не заменяет runtime acceptance. Collector/capture продолжаются; reset или изменение cron не выполнялись.

Оба leaderboard READY;45requests/0request errors;53candidate wallets,12enriched. Durable first_seen catalog128; предыдущие наблюдения из main discovery37163772294 сохранены с не более поздними временами. Код discovery/profile/intents/hourly локально совпал с актуальными main blobs. Новые candidates discovery-only, фиксированная тройка не менялась.

Четыре sampled crypto profiles:26/17/27/300events,12/17/23/60conditions. Последний достиг300event cap и truncated history; прочие END_OF_AVAILABLE_API_HISTORY тоже не доказывают известный initial inventory. Maker buys15/0/5/142, taker0/17/18/83. У последнего три both-side conditions. Это типы исполнений и действия, не доказанная maker/hedge/arb стратегия.

API1w/1m realised PnL сохранён по12enriched wallets с категориями/окнами в machine evidence; это best-effort historical PnL, не follower ledger, ROI или forward returns. Положительная месячная цифра отдельного кандидата не квалифицирует его для копирования. Cursor/page-cap и incomplete-history статусы сохранены, отсутствующая история не достраивалась.

Текущий offline wallet_intents заново воспроизвёл intent_traces.json из сохранённых raw profile responses. У четырёх профилей12/17/23/60condition traces; three both-side histories у последнего, в этой выборке Merge conditions0. Initial/final inventory UNKNOWN; SELL не квалифицирован как REDUCE/EXIT, Claim не прибыль, одинаковые event timestamps unordered, late opposing buys не меняют ранний label. Если будущие Merge появятся, raw amount semantics всё ещё нужно независимо подтвердить. SKIP_UNQUALIFIED_STRATEGY не является доказанным преимуществом SmartCopy над BlindCopy.

## Что осталось

Продолжить fixed collection и проверить holdout, реальную uncertainty/coverage и концентрацию. До wallet paper comparison нужны verified prospective intent, fee/settlement semantics и заранее frozen fair-value/filter version с новым evaluation window. До продвижения inventory нужны больше независимых clusters и фактические SELL/PAIR cases либо честное признание их отсутствия. Новые индикаторы/структура исследуются отдельно и не меняют текущий эксперимент.

Новых research code fixes нет: конкретной новой ошибки не воспроизведено. Полный88-test regression без новой причины не повторялся; выполнены целевые raw/report/continuity сверки. Только Limitless и публичный Binance, без Polymarket запросов, credentials, signing, orders или капитала.
