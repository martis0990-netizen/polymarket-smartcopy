# Limitless: проверка данных после inventory-v2

Срез GitHub: **3 октября 2026, 20:16:58 UTC (23:16:58 МСК)**. Проверенный main: `57bd27700dfb64f75ebbe5af9ad642e72bc840e2`, исправления [PR #35](https://github.com/martis0990-netizen/polymarket-smartcopy/pull/35). [Машинная запись: архивы, SHA256, расчёты и статусы](evidence/limitless_inventory_runtime_2026-10-03.json).

**Статус: MAIN_V2_CHECKPOINT_PENDING / INSUFFICIENT_DATA.** Исправления присутствуют в main, CI и PR smoke прошли. Основной checkpoint v2 пока не опубликован. Изменений торговых правил в этой проверке нет.

## Основные запуски

- [37147962215](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37147962215): текущий 55-минутный сегмент на старом `751526f` (inventory-v1), старт job около 19:27 UTC; capture step ещё выполняется.
- [37150325487](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37150325487): новый main `57bd277`, schedule, ожидает общую очередь.
- [37148551108](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37148551108): ожидавший push v2 отменён при появлении нового ожидающего schedule. Это замена pending в сериализованной очереди; выполненной main-проверки v2 здесь нет.

Не прерываем текущий raw capture и не запускаем параллельные main collectors. Очередь может снова заменить ожидающий run при automatic continuation; для приёмки нужен фактический завершённый main artifact с версией v2, а не конкретный queued ID.

## Что уже произошло в v1

Проверены main artifacts **11282611940** ([run 37144414604](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37144414604), 18:30:13–19:25:14 UTC) и **11282392465** ([run 37146330445](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37146330445), 19:25:31–19:27:31 UTC). SHA256 ZIP совпали с GitHub artifact metadata. Cumulative hourly/inventory state в двух checkpoints одинаков; их результаты не складывались.

Последний cumulative hourly state содержит **14 условий / 7 часовых кластеров**: 2 MISSED_DECISION_WINDOW, 11 model NO_TRADE/NO_EXECUTABLE_EDGE, 1 model SETTLED. Это сведения об исходном benchmark; для всех 14 решений в этой проверке не исследовалась полная raw history. Подробно проверены два новых решения сегмента 18:30 UTC.

| Наблюдение | BTC | ETH |
|---|---:|---:|
| Модельная вероятность YES | 0.4217614 | 0.2509627 |
| Возраст Binance reference при решении | 1.486 с | 0.938 с |
| Лучшие цены покупки YES / NO | 0.441 / 0.600 | 0.225 / 0.834 |
| Действие модели | NO_TRADE | BUY YES |
| Первая допустимая попытка | — | 18:30:41.058 запрос, 18:30:41.333 receipt UTC |

ETH paper fill: 42.311292 gross shares, после assumed buy fee 3% — 41.04195324 shares; стоимость **8.383503568 USDC**, VWAP 0.1981386805. Receipt через 18.244 с после решения, внутри фиксированного 30-секундного deadline. В сегменте нет request_error для orderbook; первая допустимая записанная попытка совпадает с fill. Это проверка сохранённой симуляции глубины, не подтверждение исполнения биржей.

Следующий management snapshot дал **HOLD**: conservative value 6.910806 против SELL proceeds 4.326312 USDC. COMPLETE_PAIR требовал ещё 37.792163 USDC, не проходил лимит и имел отрицательный locked profit −5.143713. Поэтому наблюдаемое HOLD соответствует опубликованной политике; проигрыш события сам по себе не доказывает ошибку реализации.

В 19:17:37 UTC записан payout `[0,1]`: ETH YES обнулился. В старом v1 ledger **realized PnL −8.383503568 USDC**, cash 91.616496432; managed-minus-seed-hold = 0. Это **UNVERIFIED_V1_NO_EDGE**, отдельно от v2: обнаруженные ранее дефекты v1 не позволяют выдавать его ledger за прошедший новый evidence audit. Утверждение «входов ещё нет» относилось к более раннему архиву и теперь устарело для v1.

Constant50 benchmark: 10 settled trades, reported PnL +3.631804063 USDC, ещё одна открытая позиция стоимостью 5.782933075. Это не funded inventory-v2 и не доказательство превосходства контроля: результаты несопоставимы по набору сделок, остался открытый риск, выборка мала. Источник ещё не подтвердил выплату открытой позиции; watch остаётся активным. Не закрываем её по последней цене.

## Доступность данных

55-минутный сегмент: **704 REST books**, 54 754 WebSocket envelopes, 15 metadata markets, из них 5 проходят frozen hourly spec (включая carried рынки); лимит размера не достигнут. Между последовательными REST receipt одного подходящего hourly slug: n=352, median 18.015 с, p95 21.648 с, max 26.173 с. Перцентили — nearest rank, только внутри сегмента; межзапусковые разрывы не включены. Между двумя проверенными сегментами зазор примерно 17.132 с.

Две HTTP400 ошибки относятся к `/oracle-candles` на Binance-settled hourly рынках: API сообщает, что источник не Chainlink. Эти ответы не используются как Binance reference. Самих binance_1m/1h запросов без raw результата в этом сегменте не зарегистрировано. Ошибки сохранены; переводить этот факт в «потери данных отсутствуют» нельзя. Полнота общего рынка, cache freshness, очередь биржи и executable liquidity этим не доказаны.

Наблюдаемая частота подходит для проверки заданной delayed REST paper-политики. Оценки микросекундного арбитража и maker queue из этих данных не следуют. 54 754 stream envelopes не являются 54 754 независимыми возможностями.

## Миграция и техническая приёмка

На **реальном v1 checkpoint 11282392465** локально вызван `restore_inventory()` из текущего main. Старый state сохранён без изменений под SHA256 `681e41b3454868bb434bf7051cd3c20e7eada26f361fd6a75ec5451b92acc00f`; новый v2 имеет cash100, PnL0, positions0. Повторный restore сохраняет v2 started_at и legacy history; старые model fills не импортируются. Время нового старта в этой пробе искусственное: **PASS_NOT_MAIN_RUNTIME**, это не prospective checkpoint.

PR smoke artifact **11282723753** ([run 37148198037](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37148198037)) содержит v2 и `inventory_evidence.jsonl.gz`. Saved report равен пересчитанному, archive audit — RECONCILED_PAPER_ONLY, cash100, positions0, raw_sources0. Пустой evidence подтверждает создание файла; сохранение непустого evidence между main jobs ещё не проверено.

Оба старых main ZIP при аудите текущим `archive_report()` дают NO_V2_CHECKPOINTS, report=null и legacy_v1_checkpoints_excluded=2. Их loss не скрывается и не зачисляется в новую версию.

Проверки этого среза PASS: SHA256 трёх ZIP, raw counts против summary, повторный расчёт hourly reports, повторный расчёт v2 smoke report, равенство двух cumulative checkpoints, v1 exclusion, offline migration/restart/no-backfill, сопоставление ETH fill с первой допустимой записью book. Код и frozen параметры не менялись; ранее пройденные 88 regression tests не запускались заново без новой причины.

## Следующие ворота

1. Первый завершённый **main v2**: новый started_at, исходные 100 USDC, v1 history сохранена; report и archive audit согласованы. Новые допустимые входы после started_at могут уже изменить cash — сравнивать с ledger, не требовать cash100 после сделки.
2. Следующий **main v2**: тот же started_at, предыдущие entry_attempts/positions сохранены, evidence накоплено, audit пары checkpoints проходит. Если evidence пусто, перенос непустых источников остаётся отдельным открытым критерием.
3. Первые prospective entry/management/settlement: raw source, первая попытка, лимиты, execution economics и payout; пропуски сохраняются. При отсутствии сигнала фиксируем ноль, не меняем пороги.
4. Discovery / holdout с границей **6 октября 00:00 UTC**, cutoff **10 октября 09:00 UTC** остаются неизменными. Прибыльность оценивается позже по независимым часовым кластерам, matched seed-hold, открытым позициям и coverage. Сейчас итог — INSUFFICIENT_DATA.

Для повторения archive gate скачать указанные GitHub ZIP и выполнить на main `57bd277`:

```bash
python research/limitless_inventory_paper.py main-11282611940.zip main-11282392465.zip --out legacy-check.json --as-of 2026-10-03T20:16:58Z
python research/limitless_inventory_paper.py pr-11282723753.zip --out smoke-check.json --as-of 2026-10-03T20:16:58Z
```

Первый результат должен быть NO_V2_CHECKPOINTS; второй — RECONCILED_PAPER_ONLY. Не объединять PR smoke и prospective main в один ledger lineage.
