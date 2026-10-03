# Limitless inventory v2: закрытие ревью

Дата: 2026-10-03. Основание: [6 замечаний v1](LIMITLESS_INVENTORY_REVIEW_2026-10-03.md), проверенный source `bd67203`, сохранённый review PR #34. Новая политика: `limitless-inventory-paper-v2`, отдельный prospective started_at и виртуальный капитал100USDC. Production orders/подписей/средств нет.

| Замечание | Исправление | Проверка |
|---|---|---|
| R1: одинаковая худшая цена скрывала рост VWAP и убыточную пару | `execution_economics()` пересчитывает locked profit,2% hurdle и улучшение HOLD >=0.02 до debit по новой полной котировке и сохранённому p. SELL также проверяет суммарную выручку. Первый отказ окончательный | Исходный сценарий убыточной пары SKIP, cash/PnL/quantity/basis сохранены. SELL с тем же min price и исчезнувшими дорогими bids SKIP. Прежние прибыльные pair/sale tests проходят |
| R2: произвольные cash/PnL и переписанный PENDING проходили audit | `rebuild()` выводит balances/spent/PnL из first entry, execution и settlement sources. Проверены quote, immutable decision, event funding, времена. Архив сопоставляет source SHA256 с raw evidence и проверяет неизменность pending/terminal/entry history | Поддельные +5USDC, quantity/basis/spend и changed pending order отвергаются; missing raw sources, same-time conflicts дают report=null; restart и обычные переходы проходят |
| R3: pooled PnL скрывал отрицательный holdout | В phases отдельные managed/seed-hold/delta, matched conditions, settled cost, interim realized, open basis/positions и hour clusters | Discovery+14.25/holdout−10/total+4.25 показаны раздельно; shared cash не разбит на вымышленные независимые счета |
| R4: watch удалялся по status до верификации payout | Retirement требует проверенной выплаты и закрытия обязанностей hourly/v2. Open v2 watches rehydrated из entry source при restart | Полный async capture: старый prematurely retired watch восстановлен, partial RESOLVED не закрывает его, через следующий metadata check валидная выплата начислена один раз; накопительное raw evidence перенесено |
| R5: NaN settlement time проходил expiry | Finite numeric time gate до mutation, temporal validation при restore/audit, сверка identity и согласованности winner/payoutNumerators | NaN/±Inf/bool/string/до expiry оставляют state неизменным; NaN в persisted settlement rejected |
| R6: пропущенный первый запрос позволял поздний baseline fill | `process_book_attempt()` сохраняет первый допустимый entry attempt перед frozen hourly callback. None/error/backoff/invalid quote окончательно исключают поздний fill из v2 | Полный async capture с HTTP timeout: baseline позднее FILLED, v2 positions=0/cash100/first-attempt skip. Ошибка до eligibility не исключает нормальный первый fill |

## Область и сохранённые параметры

Entry<=10,condition cumulative<=20,capital100,fees3%/1.5%,merge reserve0.01,probability stress±0.03,2% pair hurdle,0.02 incremental hurdle,delay/deadline/one-management decision и discovery/holdout boundary6Oct остаются фиксированными. Исправление execution меняет множество допустимых действий, поэтому это новая inventory version; прибыль v1 и v2 нельзя объединять.

`limitless_hourly_paper.py` побайтно сохранён (SHA256 `ebeb91ee28e0b9f3f19edc7c788acf8eb808287d02c625f894c1df36303cfcde`). Его legacy missing-frame retry остаётся ограничением исходного frozen benchmark. Inventory-v2 самостоятельно проверяет source entry и исключает affected fills. Отдельная новая hourly policy потребует отдельного протокола; здесь она не создана.

При первом main v2 запуске `restore_inventory()` сохраняет старый v1 state в `inventory_paper_history`, создаёт новый v2 cash100 и не импортирует старые позиции. Следующий v2 запуск восстанавливает started_at, first-attempt history и ledger. Неизвестная/corrupt v2 schema вызывает отказ, а не тихий reset. Legacy v1 остаётся raw/unverified history; его report не включается в v2 final audit. Open obligations текущего v2 восстанавливаются даже при отсутствующем/неверно помеченном watched.

## Evidence и финальный аудит

`inventory_evidence.jsonl.gz` содержит только нужные raw BOOK/MARKET observations с numeric requested/received times, market metadata и SHA256. Запись предшествует переходам ledger. Workflow переносит этот небольшой накопительный файл вместе со state; дополнительного HTTP нет. Source fingerprints не являются криптографическим удостоверением API: они позволяют сверить сохранённые observations и state и обнаружить их несовпадение.

`archive_report()` проверяет v2 arithmetic/event history, funding, matching source quotes/payouts, immutable pending decisions, неубывание entry/skip history и same-time conflicts. Берёт последний checkpoint, не сумму отчётов. При пропущенном evidence или противоречии — `UNRECONCILED_CHECKPOINTS`, `report=null`; v1 явно исключён. `--as-of` требует timezone и исключает future checkpoints. Без v2 — `NO_V2_CHECKPOINTS`, а не выдуманный результат.

Ledger tolerates только Decimal arithmetic residue<=1e-18USDC; исходное cash+basis identity также проверяется. Это не допуск финансовых расхождений размером в микроUSDC.

## Приёмка исправлений

- `python -m unittest discover -s research -p 'test_limitless*.py' -v`: **88 tests PASS**.
- `python research/limitless_market_capture.py --selftest`: **PASS**.
- Limitless workflow YAML parse: **PASS**.
- Два полных collector integration runs используют mocked HTTP/socket/clock, не сеть: first timeout и payout retry/restart/evidence carry.
- [Машинная запись проверки с source hashes](evidence/limitless_inventory_v2_validation_2026-10-03.json).

Готовность software fixes не означает готовности прибыльной стратегии. Следующая приёмка: GitHub CI/PR smoke, фактическое появление v2 в main checkpoint, сохранение started_at/source evidence на следующем сегменте; затем реальные paper entry/management/settlement при появлении сигнала. Нулевое число входов — валидный INSUFFICIENT_DATA, а не повод менять пороги.

Probability calibration, REST depth freshness/matching uncertainty, fee sensitivity и assumed merge cost/latency остаются исследовательскими допущениями. Для edge нужны фиксированный holdout, matched managed-minus-seed-hold по часовым кластерам, coverage и учёт открытого риска. Maker/live stage не открыт.

Фактический статус после merge и проверка реальных архивов: [runtime checkpoint 3 октября, 20:16 UTC](LIMITLESS_INVENTORY_RUNTIME_2026-10-03.md). CI/PR smoke PASS; main v2 ещё ожидает очередь. В старом v1 архиве появилась первая убыточная paper-позиция; она сохранена отдельно и не импортируется в v2. Локальная миграция этого реального checkpoint прошла, но не заменяет приёмку двух последовательных main v2 jobs.
