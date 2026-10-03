# Ревью алгоритма Limitless inventory v1

Замечания ниже относятся к pinned v1. Их исправление и regression/mocked capture приёмка в v2 описаны отдельно: [LIMITLESS_INVENTORY_V2_FIXES.md](LIMITLESS_INVENTORY_V2_FIXES.md). Это не переписывает исторический verdict и не подтверждает edge новой версии.

Дата: 2026-10-03. Проверенный commit: [`bd67203e8d35eb8768e85eb4e6a1ec30c8c81df0`](https://github.com/martis0990-netizen/polymarket-smartcopy/commit/bd67203e8d35eb8768e85eb4e6a1ec30c8c81df0), PR #33. Область: inventory policy, frozen hourly probability/entry dependency, capture/checkpoint/settlement integration. Wallet SmartCopy и Polymarket не входят в эту проверку.

**Вердикт: CHANGES_REQUIRED.** Есть подтверждённые ошибки торгового ограничения, первого входа и проверки/отчётности. Сбор исходных наблюдений полезно продолжать; inventory v1 нельзя использовать для вывода о прибыльности до исправлений и повторной проверки. Реальное исполнение не реализовано и не разрешено. Это отдельная исследовательская стратегия, а не подтверждённый алгоритм Bonereaper.

## Подтверждённые замечания

Приоритет P1 означает блокер достоверной приёмки/анализа; P2 — исправить до дальнейшего расширения. Все примеры ниже синтетические, без сети, средств или ордеров. Это доказательства поведения кода, а не измеренные убытки биржевой торговли. Дефекты checkpoint и settlement пока не обнаружены в реальных артефактах.

### R1 — P1: исполнение пары не сохраняет требуемую прибыль

Место: `research/limitless_inventory_paper.py`, `alternatives()` строки 163–175 и `execute()` строки 223–258.

На решении `locked_profit` и требование 2% рассчитаны по суммарной стоимости обхода текущей глубины. На исполнении проверяются `price_bound`, cash и condition cap. Прибыль и минимальное улучшение HOLD не пересчитываются. Одинаковая худшая цена не означает одинаковую среднюю цену: дешёвые уровни могут исчезнуть, а весь объём останется доступен на дорогом последнем уровне.

Воспроизведение использует настоящий `HourlyPaper.book()` для решения и delayed entry fill, затем `InventoryPaper.book()` для управления. Вероятности задаются тестовым источником, чтобы изолировать execution policy.

| Показатель | Значение |
|---|---:|
| Исходная стоимость YES | 9.98775090 USDC |
| Исходные net YES | 16.99669890 |
| Решение | COMPLETE_PAIR |
| Стоимость покупки NO на решении | 1.07061677 USDC |
| Расчётная locked profit на решении | +5.92833123 USDC |
| Худшая допустимая цена NO | 0.42 |
| Стоимость NO на первом допустимом execution book | 7.35939540 USDC |
| Худшая цена NO на исполнении | 0.42 |
| Статус | PAPER_EXECUTED |
| Реализованный paper merge PnL | **−0.36044740 USDC** |

Cash, delay, expiry, depth и price bound проходят; отрицательная пара нарушает обещанное ограничение положительного locked profit. Отрицательный итог здесь честно записан в ledger: ошибка в допуске действия, не в сокрытии потери.

Исправление: до любого списания восстановить последствия фиксированного действия по новой котировке и проверить положительный locked profit, 2% hurdle и минимальное улучшение HOLD по сохранённой decision probability. Если проверка не проходит — окончательный SKIP первого execution attempt. Не менять сторону, объём, вероятность и не искать последующий удачный стакан. Аналогично проверить SELL относительно сохранённой альтернативы HOLD: цена последнего уровня не защищает суммарную выручку. Альтернатива — заранее вывести лимит цены, обеспечивающий эти ограничения даже при исполнении всего объёма по лимиту.

Критерий приёмки: воспроизведённый сценарий SKIP без изменения cash/quantity/basis; допустимая прибыльная пара исполняется; исчезновение дешёвых уровней и несколько уровней SELL покрыты регрессионными тестами.

### R2 — P1: RECONCILED_CHECKPOINTS не доказывает финансовую непрерывность

Место: `research/limitless_inventory_paper.py`, `validate()` строки 82–94 и `archive_report()` строки 369–382.

Проверка `cash+basis=100+realized_pnl` необходима, но не связывает cash/PnL с событиями. Между двумя одинаковыми позициями можно увеличить cash с 90 до 95 и realized_pnl с 0 до 5 без продажи, merge или settlement. Архивный отчёт объявляет `RECONCILED_PAPER_ONLY` и показывает придуманные +5 USDC. Отдельный пример меняет quantity и price_bound уже сохранённого PENDING-решения; он также проходит reconciliation.

Это проверенный пробел детектора конфликтов, не свидетельство повреждения текущих main-данных. Для ошибочного или изменённого checkpoint финальный аудит способен выдать ложный результат.

Исправление: зафиксировать неизменность всех полей решения при переходе PENDING → исполнение/отказ; разрешать только документированные переходы статусов. Выводить cash, realized PnL, quantities/bases/spent_total из seed и сохранённых sale/merge/settlement событий и сверять полученный ledger. Для подтверждения исполнения сверять события с raw observations, а не только с соседним checkpoint. При несовпадении — `UNRECONCILED_CHECKPOINTS`, `report=null`.

Критерий приёмки: оба примера отклоняются; корректные переходы entry → PENDING → execution → settlement и повтор одинакового checkpoint проходят без удвоения результата. Совпадающее ended_at с разными состояниями должно давать явный конфликт.

### R3 — P1: PnL discovery и holdout объединён

Место: `research/limitless_inventory_paper.py`, `report()` строки 317–339.

В `phases` есть только counts/feasibility; `managed_settled_pnl`, `seed_hold_settled_pnl` и realized PnL представлены общей суммой. Пример с discovery +14.25 и holdout −10 выдаёт общий settled +4.25. Отчёт не содержит отдельного holdout PnL, поэтому общий плюс способен скрыть отрицательную проверочную выборку. Данные фазы сохранены в позициях: результат можно восстановить, но штатный final report этого не делает.

Исправление: по каждой фазе публиковать managed settled PnL, matched seed-hold PnL, разницу этих двух результатов, количество пар сравнения, стоимость входов, открытые позиции/basis и реализованный промежуточный PnL. Общую сумму оставить только как совокупный учёт. Отдельно сохранить результат по часовым кластерам для оценки концентрации. Cash общий для портфеля; нельзя придумывать независимые cash счета фаз без отдельной модели финансирования.

Критерий приёмки: пример показывает holdout −10, discovery +14.25 и общий +4.25; парные сравнения используют одинаковые admitted settled conditions. Вывод об edge опирается на holdout, покрытие и разброс, а не на pooled PnL.

### R4 — P1: market watch удаляется до подтверждённого settlement

Место: `research/limitless_market_capture.py`, строки 209–215 и 264; `research/limitless_inventory_paper.py`, `market()` строки 287–309.

Capture отмечает `resolved=true` сразу по `status=RESOLVED`, прекращает последующие metadata checks и исключает рынок из carried watched. Однако inventory settlement может отказать из-за отсутствующего/невалидного payout или непройденного spec. При `RESOLVED` без winner/payoutNumerators модель остаётся с cash 90 и open basis 10, а carried watched уже пуст. Когда такой рынок перестаёт входить в active discovery, следующей проверки выплаты не будет. Последствия — зависший капитал и неполная settled выборка.

Воспроизведение напрямую исполняет inventory settlement и точные retirement/persistence expressions из collector; полный async capture с поддельным HTTP в этом ревью не запускался. Случай неполного payload проверен синтетически; его частота в публичном API не установлена.

Исправление: отделить venue status от подтверждённой обработки выплаты. Сохранять и повторно проверять обязательства открытого paper inventory до валидного settlement либо явного unresolved/data-quality результата на cutoff. Не списывать open risk и не заполнять выплату предположением.

Критерий приёмки: интеграционный тест partial RESOLVED → restart → valid payout подтверждает перенос watched, последующий settlement и отсутствие двойного начисления; baseline hourly semantics остаются фиксированными.

### R5 — P2: settlement принимает нечисловое время наблюдения

Место: `research/limitless_inventory_paper.py`, `market()` строка 289.

`observed=NaN` делает проверку `observed < expiry` ложной, и позиция получает settled_at=NaN и выплату. `validate()` не проверяет это поле; report считает позицию закрытой. Текущий collector передаёт `time.time()`, поэтому это дефект границы состояния/replay, без свидетельства NaN в текущем main-потоке.

Исправление: проверять конечность и порядок settlement observation time до изменения состояния; проверять временные поля восстановленного checkpoint. Критерий: NaN/Inf/время до expiry не меняют cash и settlement state.

### R6 — P1: entry source повторяет попытку после первого отсутствующего стакана

Место: `research/limitless_market_capture.py`, строки 195–201; `research/limitless_hourly_paper.py`, строки 233–247; `research/limitless_inventory_paper.py`, `admit()` строки 100–108.

При HTTP error/timeout/backoff `raw=None` collector вызывает только `inventory.unavailable_book()`. До inventory admission позиции ещё нет, поэтому этот вызов ничего не закрывает. Ожидающий hourly model entry остаётся PENDING: `HourlyPaper.book()` не получает отсутствующий book. Следующий успешный запрос внутри 30 секунд может исполнить вход; inventory доверяет статусу FILLED и принимает его.

Воспроизведение: decision в MID, первый допустимый запрос неуспешен в MID+2, следующий успешный запрос с более дешёвым ask в MID+18. Hourly проходит PENDING → FILLED, inventory создаёт позицию. Это не соответствует правилу первого execution attempt и может выборочно улучшать бумажные входы после ошибок данных. Контрактный deadline соблюдён, поэтому он не предотвращает повторную попытку.

Исправление: новой inventory версии независимо подтверждать, что seed возник на первом допустимом entry attempt; сохранять окончательный отказ этого attempt даже до admission. Старые model fills без такой проверки не считать подтверждёнными входами новой политики. Исходный frozen hourly benchmark не менять молча: его legacy поведение отметить как limitation, а исправление entry semantics вынести в отдельную версию/исследование. Для v1 анализа нужна сверка initial fill с raw attempts и отдельный учёт affected/missing условий.

Критерий приёмки: HTTP error, raw=None и backoff после entry eligibility исключают более поздний fill из нового inventory; ошибка до eligibility не закрывает ещё не наступившую попытку. Для теста использовать полный collector hook sequence, затем интеграционный mocked-HTTP capture. Здесь воспроизведён именно hook sequence; полный async collector не подменялся.

## Оценка торговой модели

Корректные части: парный payoff не дисконтируется дважды, YES/NO depth инвертируется согласованно, gross/net buy units и sell fee разнесены, entry и management не исполняются в одном snapshot, funding cap проверяется, cost basis пропорционально списывается, исходный hourly benchmark отделён от inventory ledger. Положительный merge не объявлен доказательством преимущества над удержанием выигрышной стороны.

Пока нет основания ожидать положительную доходность. Probability — zero-drift log diffusion по 120 минутным returns с постоянной оценкой volatility до expiry. Формула сама по себе не подтверждает calibration на BTC/ETH и режимах движения. Диапазон ±0.03 не является измеренной ошибкой модели. Требуются holdout Brier/calibration, результаты по стороне/часовым кластерам и matched managed-minus-seed-hold distribution. Порог 60 conditions/60 hours — достаточность для начала анализа, не гарантия статистической независимости или edge.

REST receipt depth остаётся предположением исполнения: официальная документация не обещает границы freshness, а snapshot не доказывает доступность объёма при matching. Buy 3% и sell 1.5% — верхние paper assumptions для CLOB; реальные fees зависят от цены. Эти допущения консервативны по величине комиссии, но способны менять ранжирование SELL/COMPLETE_PAIR. Paper merge мгновенно освобождает cash за предполагаемые 0.01 USDC; это не измеренная стоимость/задержка и может завысить оборот капитала. До оценки edge нужны заранее заданные сценарии cost/latency/unavailable liquidity без подбора по прибыли.

Это одно решение управления на первом следующем book attempt, примерно через очередной snapshot collector, а не непрерывный market making. HOLD/отказ означает сохранение риска до settlement. Отсутствие многократной переоценки — явный дизайн первого этапа, а не найденная ошибка. Полный maker с очередью/отменами добавлять до приёмки этой модели не следует.

Микроскопический остаток после net fee может иметь меньше 1e-6 контракта. Его влияние ничтожно для текущего бюджета, но перед execution bridge необходимы проверенные правила округления token/USDC units. В бумажной модели не выдавать такую дробь за реально доступный токен.

Официальные источники, проверенные 2026-10-03:

- [CLOB fees и units комиссий](https://docs.limitless.exchange/user-guide/fees).
- [YES/NO book, 6-decimal units, snapshot freshness](https://docs.limitless.exchange/api-reference/trading/orderbook).
- [Pair merge и способы выполнения](https://docs.limitless.exchange/user-guide/merge-split).

## Проверка и воспроизводимость

1. Существующий suite: `python -m unittest discover -s research -p 'test_limitless*.py' -v` — **73 tests PASS**. Эти тесты не покрывают перечисленные дефекты.
2. Диагностические примеры: `python research/review_limitless_inventory_v1.py --out review.json` — **6/6 findings reproduced** на проверенном commit. Это не acceptance suite: воспроизведение дефекта не означает корректность стратегии. После исправления пробу следует преобразовать в отрицательный regression test новой версии.
3. [Машинный результат с SHA256 исходников](evidence/limitless_inventory_review_2026-10-03.json). SHA256 позволяют проверить соответствие кода pinned commit.
4. Ранее проверенный PR smoke artifact `11282000610` содержал 0 inventory positions и cash 100; исторический integration replay — 0 model fills. Эти проверки подтверждали интеграцию, но не работу торговых ограничений на реальном входе/settlement. В данном ревью новый main action/settlement не подтверждался.

В этом review change производственный код, параметры, collector и frozen hourly experiment не изменены. Добавлены только документ, диагностический script и synthetic evidence.

## Порядок исправлений

1. R1 и R6: execution economics gate и независимая проверка первого entry attempt + regression tests. Исправление меняет допускаемые действия: назвать новую inventory policy version, сохранить v1 artifacts, не сшивать её PnL с исправленной версией. Запуск после изменений — с отдельным prospective started_at; старые fills не импортировать. Исходный hourly holdout не менять.
2. R2 и R5: строгая проверка состояния и объяснимый ledger; отрицательные checkpoint tests. Старые артефакты перепроверять без переисполнения истории и без придумывания отсутствующих событий.
3. R4: перенос неподтверждённых settlement obligations через restart. Недостающие observations явно учитывать в coverage.
4. R3: фазовый matched report. Выводить holdout отдельно, фиксировать coverage/открытый риск. При lineage/version конфликте результат каждой линии отдельно либо INSUFFICIENT_DATA, а не общая сумма.
5. Один обязательный verification pass: имеющиеся тесты + новые meaningful regressions + capture integration + main checkpoint continuity. Затем PASS → STOP. Анализ calibration/результатов вести по фиксированному протоколу; live/maker gate остаётся закрытым.

Сначала достоверность исполнения и измерения, затем проверка преимущества управления. Если после расходов holdout не лучше seed-hold/no-trade или выборка недостаточна, сохранить отрицательный/неопределённый результат без добавления стратегий для его маскировки.
