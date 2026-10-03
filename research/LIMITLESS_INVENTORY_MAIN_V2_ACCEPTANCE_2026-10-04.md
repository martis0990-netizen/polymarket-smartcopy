# Limitless inventory-v2: приёмка основных checkpoint

Срез **3 октября2026,23:53:04UTC /4 октября02:53:04МСК**. Проверенный source main: `9dbc0f22297d32acb90b008825f7d2675f8d795d`. Это фактические основные артефакты, не PR smoke и не локальная миграция. [Машинные результаты, SHA256, отчёты и статусы](evidence/limitless_inventory_main_v2_acceptance_2026-10-04.json).

**Базовая приёмка переноса: PASS / `BASE_CHECKPOINT_ACCEPTED_PAPER_ONLY`. Экономический результат: `INSUFFICIENT_DATA`.** Подтверждены новый старт v2, точное сохранение старой истории, отсутствие импорта legacy ledger и восстановление следующего пустого v2 ledger. Перенос непустых observations/positions и торговый цикл пока PENDING.

Документ дополняет исторический [runtime срез20:16UTC](LIMITLESS_INVENTORY_RUNTIME_2026-10-03.md) и [закрытие шести замечаний](LIMITLESS_INVENTORY_V2_FIXES.md). Старые timestamped результаты не переписываются.

## Проверенные архивы

| Назначение | Main run | Artifact ID | Capture UTC |
|---|---|---|---|
| Legacy predecessor | [37147962215](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37147962215) | 11284416014 | 19:27:48.286455–20:22:48.431447 |
| Первый v2 | [37151327629](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37151327629) | 11284699716 | 20:23:04.920280–21:18:05.057714 |
| Следующий v2 | [37154622571](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37154622571) | 11286179317 | 21:18:21.132165–22:13:21.270357 |

Все три runs: main, workflow_dispatch, completed success. Версия проверена в state: predecessor=v1, следующие два=v2. ZIP SHA256 совпали с digest GitHub artifact metadata:

- 11284416014: `b455e07df0644fc2c83e5f3ed2fee671bf7c2e934d083ec9fd9277cebc33d145`.
- 11284699716: `519fefe7a5d971f6d3022add94e53f5c725308f84b3a164245f5758ea0e2d7af`.
- 11286179317: `c6198d3e755c2a378ba1e6cd1c9fd865d60e8165b6ee7d009dd1432c8c218c41`.

Гап между predecessor и первым v2:16.488833с; между двумя v2:16.074451с. Это отсутствующие наблюдения. Cancelled pending runs37148551108/37150325487 и PR smoke не включены.

## Миграция и восстановление

Первый v2 имеет `started_at=1791058984.920855`, то есть **20:23:04.920855UTC**, внутри первого capture и позже legacy старта. На следующем checkpoint started_at тот же. Оба v2 state совпадают полностью; canonical digest: `adcc673b38f5ba77ec6ed4a6ef149b7f970852bb827325e5aa43fa45215ac557`.

`inventory_paper_history` в обоих checkpoint содержит точный predecessor state под `cdd8166e55c911a26062daa3af94ea7acd5734eed01dfb9fc4eca1f6a7b21629`. Сверено полное JSON equality, не только ключ. Legacy cash84.083584041, realizedPnL−8.383503568, две позиции остаются только в этой unverified истории. Они не включены в v2 позиции, cash или PnL.

В jobs111285678201 и111295370711 Restore unresolved market checkpoint и остальные steps завершились success. Логи не печатают выбранный artifact ID; фактическая родословная подтверждена точным совпадением сохранённого predecessor state, затем v2 state/history. SHA256 полученных job logs сохранены в machine evidence. Inventory/capture source blobs одинаковы на обоих проверенных heads; frozen hourly SHA256 также совпал с зафиксированным.

## Ledger, raw evidence и отчёты

| Проверка | Первый v2 | Следующий v2 |
|---|---|---|
| Cash / realized PnL | 100 /0USDC | 100 /0USDC |
| Positions / entry_attempts / admission_skips | 0 /0 /0 | 0 /0 /0 |
| Raw inventory evidence rows | 0 | 0 |
| Saved report = новый InventoryPaper(state).report() | PASS | PASS |
| archive_report только этого ZIP, aware as-of | RECONCILED_PAPER_ONLY | RECONCILED_PAPER_ONLY |

`archive_report` пары также RECONCILED_PAPER_ONLY, errors=[], последний report совпадает с отдельно пересчитанным вторым checkpoint. Cumulative reports не складывались. Непустое event history отсутствует; cash100 здесь подтверждён нулевым ledger, а не требованием всегда сохранять100 после допустимых сделок.

Распакованные последовательности source fingerprints пусты: математический prefix check проходит, но **это не доказывает перенос непустых sources**. Поэтому nonempty evidence transfer, перенос непустых entry/position histories и entry→management→settlement остаются PENDING. Immutable legacy history проверена на реально непустом старом state.

В raw capture появились четыре новые model decisions: BTC/ETH20:30UTC и BTC/ETH21:30UTC. Все четыре — NO_TRADE/NO_EXECUTABLE_EDGE. Новых v2 entry/management/settlement нет. События paper_execution относятся к отдельному constant50 benchmark и не превращены в v2 fills. Paper_settlement старого benchmark также не является выплатой v2. Discovery и holdout v2 имеют0 admitted/settled positions и INSUFFICIENT_DATA.

## Воспроизведение

Скачать ZIP из указанных runs, сверить SHA256 и использовать source на проверенном ref. Каждый v2 ZIP проверить отдельно, затем пару:

```bash
python research/limitless_inventory_paper.py accept-11284699716.zip \
  --as-of 2026-10-03T23:53:04+00:00 --out first.json
python research/limitless_inventory_paper.py accept-11286179317.zip \
  --as-of 2026-10-03T23:53:04+00:00 --out second.json
python research/limitless_inventory_paper.py accept-11284699716.zip accept-11286179317.zip \
  --as-of 2026-10-03T23:53:04+00:00 --out pair.json
```

Для saved report equality загрузить `state.json`, передать `inventory_paper` в текущий InventoryPaper и сравнить `.report()` с `inventory_paper_report.json`. Для истории загрузить predecessor state и сравнить его целиком с history обоих v2. `digest()` — SHA256 canonical JSON с sort_keys и compact separators. Для source prefix распаковать `inventory_evidence.jsonl.gz`, проверить каждый source_sha256 через digest(source) и сравнить порядок, включая дубликаты; здесь обе последовательности пусты.

Выполнен один read-only проход приёмки с assertions и повторным расчётом. Ошибок и fix cycles нет; production code/параметры/fees/holdout/workflow concurrency/график не менялись. Уже пройденные88 regression tests повторно не запускались.

Базовая техническая задача закрыта. Далее существующий сбор должен дать реальные допустимые v2 attempts и фактическое непустое продолжение evidence; без них нельзя подтвердить исполнение торгового цикла или прибыльность. Текущий срез не меняет правила стратегии и не открывает live/maker execution.
