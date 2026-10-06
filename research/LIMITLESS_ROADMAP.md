# SmartCopy на Limitless: роадмап после ревью

> **Текущий статус (2026-10-06):** этот документ сохраняет исторический план от 3 октября. [Новый измеренный статус и пересмотр приоритетов](LIMITLESS_STATUS_2026-10-06.md) имеют приоритет для дальнейшей работы. Текущий 15m paper replay показал −98.909305129 USDC из отдельного счёта 100 USDC; положительный forecast-only Brier не отменяет убыток.

Версия 3 октября 2026; исходная база `a99662781d93a7cca44619f9d99da6ac9fb6d677`. Этот документ задаёт последовательность исследовательских работ; не подтверждает, что они уже реализованы. [Ревью и находки](LIMITLESS_REVIEW_2026-10-03.md), [описание текущей системы](LIMITLESS_ENTRY_PIPELINE.md).

Цель: определить, остаётся ли воспроизводимое net advantage у конкретных действий после их обнаружения. Исходный исход — либо узкая обоснованная стратегия для следующей paper-проверки, либо отрицательный результат и остановка. Достичь торговли любой ценой не является критерием успеха.

## Порядок работ

| Этап | Работа | Критерий завершения | Зависимость |
|---|---|---|---|
| 0. Операционная цепочка | Подтвердить updated-main upload → explicit audit dispatch → aggregate | Успешные steps и сводка с новым artifact ID/SHA; gaps сохранены | Следующий обновлённый основной job |
| 1. Корректность данных | Закрыть R1/R2/R4 отдельным небольшим PR | Conflict/identity/time ошибки карантинируются; good rows остаются; earliest detection не меняется | Ревью |
| 2. Единые метрики | Уточнить R3/R5; разделить whole/timing-known denominators и market families | Legacy screen не выдаётся за fill gate; все 326 записи объяснимы статусами | Этап1 |
| 3. Полнота наблюдения | Оценить R6: payload/schema, page saturation, overlap IDs, gaps | Опубликованы измеренные потери/unknown coverage; версия collector отмечена | Можно параллельно анализировать уже записанное |
| 4. Независимые действия | Связать observed actions с forward data и metadata | Есть проверяемые episode IDs, происхождение и время доступности каждого признака; unknown → SKIP | Этапы1–3 |
| 5. Экономический paper contract | Задать fair value/max price, size, fees, settlement/exit и controls | Спецификация заморожена до оценки новых данных; отсутствует lookahead | Этап4 |
| 6. Prospective evaluation | Сравнить BlindCopy, SmartCopy и no-follow при одинаковом исполнении | Достаточная независимая выборка/coverage; net outcome и концентрация; все SKIP сохранены | Этап5 и новые данные |
| 7. Решение | Продолжить узкую гипотезу, признать отсутствие edge либо недостаточность данных | Публично воспроизводимый итог с raw provenance | Этап6 или провал gate |

## Ближайший PR: проверки, а не новый бот

R1: добавить audit conflict/provenance между feed/history. Forward decision остаётся неизменным; позднее противоречие отдельно исключает запись из проверенной ретроспективной оценки. Тесты: разные YES/NO одного UUID; конфликт с поздним timestamp; одинаковые источники не увеличивают sample.

R2: проверить equality observation/book slug и доступные market/token/collateral identifiers. При неизвестной полной привязке — отдельный UNVERIFIED status, без предполагаемых fills. Для новых наблюдений сохранить metadata с временем receipt; не выполнять позже исторический book fetch для исправления старой цены. Тесты: чужой slug/token, non-USDC или неизвестные decimals, корректный YES/NO.

R4: валидировать обязательные времена до сравнений; malformed row не должна уронить хорошие записи. Тесты: missing/malformed/timezone cases, source future, request до observation, receipt до request. Все исключения объясняются в отчёте.

Один обязательный проход проверки, не более двух циклов исправления по конкретным ошибкам, PASS → STOP. Не расширять работу до framework или общего рефакторинга.

## Метрики следующей версии

- Whole observed denominator, timing-known denominator, rejected/unknown/error counts — отдельно по cohort/discovery и 5m/15m/hourly.
- На buy record: source/request/receipt times, max-price capacity, размер, gross/net fee basis, identity validation и причина SKIP.
- Delay p50/p90/p95 с sample count; интервалы интерпретируются как publication+polling+network, пока компоненты не измерены.
- Budget10 остаётся основным диагностическим бюджетом. Дополнительный size sensitivity возможен только как заранее объявленный диагностический анализ, не выбор прибыльного размера задним числом.
- Никакая доля поддержанных котировок не называется вероятностью фактического исполнения.

Не уменьшать polling interval просто потому, что задержка высока. Сначала выяснить, какую её часть можно сократить и есть ли достаточный остаточный edge. Existing independent WebSocket capture можно использовать для prospective schema/freshness checks при совпадающем рынке и времени; поздний snapshot не заменяет первоначальный entry attempt.

## Действия и выбор кошельков

Исходная тройка не меняется внутри её исследования. Discovery candidates — отдельная exploratory выборка. Отбор не должен зависеть только от PnL, нескольких удачных quotes или hindsight результата события. Зафиксировать правила отбора до будущей оценки.

Fill group по orderId/condition/side не равен ENTER. Нужно понять контекст inventory, SELL, paired purchases, Split/Merge/Convert и transfers. Если полного начального состояния нет, действие остаётся неизвестным; не придумывать позицию с нуля. Одновременные события не упорядочиваются по UUID. Поздние opposing buys не превращаются в доступный раньше hedge filter.

На выходе этапа4: ограниченный набор подтверждаемых классов действий или честный вывод, что публичных данных недостаточно. Не требуется реализовать все классы, если доказуем только один.

## Экономика и критерии остановки

Перед новым сравнением определить maximum acceptable buy price и size cap на основе доступного в момент решения residual value, а не просто цены лидера. Подтвердить maker/taker fees конкретного режима, contract deduction, округление, settlement rules и lockup капитала. При unknown fees/settlement не публиковать net PnL как подтверждённый.

Исполнение paper: первая допустимая попытка, наблюдаемая глубина, одинаковые правила у controls, без favorable retries и midpoint fills. No-follow=0, BlindCopy и SmartCopy получают одинаковые episode/execution assumptions. Partial/skipped entries и неподтверждённые результаты сохраняются.

Замороженный исходный feasibility screen 90%/60 не снижается для получения PASS. Его 60s proxy не заменяет независимые намерения: перед статистическим выводом нужна независимость по condition и временным кластерам. Discovery-wallet исследование требует собственной заранее объявленной выборки/gate и prospective split; переносить их удачные сделки в исходную когорту нельзя.

Hourly paper experiment имеет свой уже установленный discovery/holdout. Его правила не меняются этим roadmap, его PnL не считается SmartCopy PnL. Для wallet SmartCopy новый filter и evaluation period объявляются отдельно до анализа будущих outcome.

Итоги: `INSUFFICIENT_DATA` при нехватке наблюдений/независимости; `NO_EDGE_STOP` при отсутствии положительного net advantage или улучшения относительно BlindCopy на новых данных; продолжение paper — только при воспроизводимом положительном результате, без концентрации на одной сделке/кошельке. Размер нового prospective sample и метод оценки неопределённости фиксируются в этапе5, не после просмотра результата.

## Календарь текущего сбора

- До 10 октября 12:00 МСК: сохранить raw evidence, закрыть проверки данных и подтвердить цепочку; не обещать успеть доказать edge, если выборка мала.
- В ходе сбора: отделять версии/временные границы исправлений, сохранять manifests, следить за retention14d. Старые данные не пересоздаются.
- После cutoff: итоговая сводка с provenance, неизвестными данными, покрытиями и frozen gate. Если возник timeout/потеря archive — PARTIAL/INSUFFICIENT_DATA, не автоматический PASS.
- При положительной исследовательской гипотезе: отдельное решение о следующем prospective paper run. Live execution в текущий roadmap реализации не включён.

Ближайший полезный результат — небольшой PR с R1/R2/R4 и ясные знаменатели. Расширение списка стратегий, AI decision engine и торговый исполнитель сейчас не закрывают найденные пробелы.

## Статус первого исправления

Diagnostics-v2: R1 (retrospective conflict/provenance) и R4 (required-time quarantine) реализованы и прошли regression. R2: envelope slug и известные token/collateral/group identifiers проверяются; полная prospective metadata binding остаётся открытой и явно UNKNOWN. Добавление metadata-запросов не выполнено этой правкой. 28 тестов PASS; показатели реального main сегмента совпадают с исходными, invalid data=0.

Следующая ограниченная работа: сохранить точную market metadata с наблюдаемым временем для новых source events, подтвердить YES-token/USDC/decimals и active single CLOB semantics; затем объединить строгую eligibility с объяснимыми знаменателями (R3/R5). До этого не выдавать supported depth quotes за квалифицированные COPY. Историческое ревью не переписывается; улучшения имеют новую schema version и commit provenance.


## Дополнение 2026-10-03: подготовка к завершению сбора

Реализованы prospective metadata до первого book request (один GET на точный slug, максимум 30 за сегмент, ошибка не ретраится), SHA256/raw rules и проверки binary token pair/Base USDC/expiry. Старые записи не обогащаются поздней metadata. Параметры исходного эксперимента не меняются; новый capture_protocol отмечает фазу с дополнительной задержкой.

Единая функция entry_eligibility используется сегментными и aggregate diagnostics, а legacy audit содержит companion entry_diagnostics. Старый full-week feasibility gate сохранён. Data-qualified quote не становится COPY: unknown intent/fee/fair value остаются SKIP, fill/PnL — null.

Добавлены page_ids/overlap/saturation и возможные page-gap warnings, poll gap/error counters; неизвестная схема страницы теперь request_error. Старые страницы имеют completeness unknown. Disjoint pages не доказывают число потерянных событий, global feed не покрывает всю биржу.

Ретроспективные action categories отделяют обе стороны, Split/Merge и одиночные наблюдаемые покупки с неизвестным исходным инвентарём. Подтверждённых directional entries эти категории не создают. Экономический контракт и блокеры: [LIMITLESS_SMARTCOPY_PAPER_CONTRACT.md](LIMITLESS_SMARTCOPY_PAPER_CONTRACT.md).

Новые raw artifacts retention=90 дней; для старых архивов подготовлен отдельный snapshot с manifest и SHA256. R2 закрыт для будущей identity binding; проверка settlement semantics остаётся открытой. R3 закрыт как единая companion diagnostic, а старый gate сохранён. R5: контракт описан, экономический тест блокирован до квалификации intent/fee/model. R6: telemetry реализована, размер реальных потерь пока неизвестен. Следующая приёмка — main artifact с новым capture_protocol и его попадание в progress audit.


## Собственный алгоритм управления инвентарём, 2026-10-03

План и фиксированные правила: [LIMITLESS_INVENTORY_PLAN.md](LIMITLESS_INVENTORY_PLAN.md). Реализован независимый funded paper-контроллер HOLD/SELL/COMPLETE_PAIR с лимитом100USDC, отдельным cash/cost-basis ledger, первым delayed execution attempt, settlement и переносом state. Он использует только новые входы frozen hourly model; старые позиции не импортирует, benchmark не меняет. Полный maker-алгоритм остаётся следующим этапом после проверки вероятностей и исполнения; touch-fill PnL запрещён. Приёмка main fresh entry/management/settlement будет по реально наблюдаемым артефактам, а не по прохождению synthetic tests.

Ревью inventory-v1 выявило6 дефектов. Исправленная inventory-v2 закрывает execution economics, first-entry retry exclusion, ledger/raw evidence reconciliation, фазовый PnL, settlement watch/restart и невалидные времена. 88tests/selftest PASS; старые результаты не сшиваются. [Закрытие и следующий main gate](LIMITLESS_INVENTORY_V2_FIXES.md). Вердикт edge остаётся INSUFFICIENT_DATA до перспективной приёмки и анализа holdout.

[Runtime checkpoint 3 октября, 20:16 UTC](LIMITLESS_INVENTORY_RUNTIME_2026-10-03.md): main v2 ожидает завершения старого сегмента; PR smoke и локальная миграция реального v1 state прошли. Legacy v1: одна settled model-позиция, −8.383503568USDC; это unverified history, не v2 outcome. Ближайшая работа — проверить первый main v2 artifact, затем непрерывность started_at/ledger/raw evidence на следующем, после этого фактическую цепочку entry/management/settlement. Порогов и дат исследования этот срез не меняет.

## Первичная maker-диагностика, 2026-10-03

[Протокол](LIMITLESS_MAKER_SCREEN.md) и [результаты](LIMITLESS_MAKER_RESULTS_2026-10-03.md) добавлены отдельно от frozen экспериментов. Три main архива дали422 зависимых anchors,6 conditions и3 частичных часовых кластера. Медианный спред4¢; время до первого наблюдаемого изменения BBO —0.60с только среди261 uncensored наблюдения. Fill probability и PnL неизвестны. На1/5с нет новых Binance reference pairs, поэтому защита от устаревшей котировки пока не оценена.

Следующая ограниченная работа: отдельный частый публичный Binance reference с причинными timestamps/coverage, затем заранее зафиксированная shadow-policy и сравнение на новых данных. Live executor и rewards-PnL не входят в этот этап. До разработки следующей policy установить её sample/stop rule; не выбирать параметры по текущим favourable midpoint margins. 12 focused tests анализатора PASS; полный source/provenance manifest опубликован с результатами.
