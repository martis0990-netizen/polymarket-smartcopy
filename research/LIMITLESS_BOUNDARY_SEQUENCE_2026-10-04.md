# Limitless: причинная последовательность касаний, выходов и возвратов

4 октября2026. Тот же fixed discovery slice37scored conditions /19hour clusters, as-of08:27UTC. Pinned main `7f47981efa0db769b984e5448e857ead719e6af0`. [Raw-derived machine evidence](evidence/limitless_boundary_sequence_2026-10-04.json). Этот документ завершает доступную raw-часть предыдущего [range-location разбора](LIMITLESS_RANGE_LOCATION_2026-10-04.md), без изменения trading policy.

**CAUSAL_RAW_ENVELOPE_SEQUENCE_NOT_CONFIRMED_CONSOLIDATION_NOT_STRATEGY.** Локальная среда снова доступна. Повторно прочитаны22digest-verified main capture ZIPs и contemporaneous Binance responses всех37conditions. Это новая raw replay проверка, не только арифметика saved fields. PR smoke исключены.

## Почему границы заморожены до проверяемого движения

Previous15 extrema в момент решения нельзя перенести назад и использовать как якобы известные уровни первых свечей. Поэтому для sequence diagnostic взяты15closedM1 **перед**30closedM1 probe; их min/max зафиксированы на весь последующий probe. Существующие15/30descriptive horizons не перебирались. Это отдельная operational разметка post-hoc discovery, не новая стратегия или ранее утверждённые stable range boundaries.

Отдельно заново пересчитан previous15envelope **у решения**, исключая last signal candle. Он совпадает с прежними saved values для всех37. Две системы границ не смешиваются: early frozen envelope отвечает на вопрос о последовательности, decision envelope — о текущем положении.

## Что именно наблюдается

- Boundary contact: уровень находится между low/high закрытого бара, без ценового tolerance. Касания не независимые trades.
- Wick excursion with close inside: high строго выше upper либо low строго ниже lower, но close внутри frozen window. Это OHLC факт, не доказательство stop/liquidation sweep.
- First close outside начинает continuous outside episode. Subsequent closes с той же стороны увеличивают outside_closes.
- Первый later close внутри заканчивает episode RETURN_CLOSE_INSIDE. Если close перескочил к противоположной стороне без inside close, это отдельный terminal, не придуманный возврат.
- OPEN_AT_LAST_OBSERVATION означает отсутствие inside close до decision; acceptance threshold не задан, поэтому это не подтверждённый accepted breakout.

Все события доступны по закрытию бара. Их порядок внутри одного бара UNKNOWN; перечисление contact/wick/return на одном timestamp не является восстановленным tick-path. Future terminal episode известен только по ending/as-of, early event не переписан задним числом.

## Результат37условий

26conditions имели wick excursion с close внутри;35 — хотя бы один close снаружи;22 — episode с последующим close внутри;25 — открытый outside episode к решению. Категории пересекаются.63outside episodes:34return-inside,25open,4cross-opposite-without-inside. Это описание движения относительно окон, не63independent trades и не статистика прибыльности.

У большинства условий был выход: сам presence такого события не доказывает edge. Frozen extrema всегда определены даже в тренде; stable_consolidation остаётся UNVERIFIED. Устойчивая граница, значимость зоны, цена исполнения и вероятность итогового hourly payout из этой разметки не следуют.

## ETH проигрыш: точная хронология до входа

Границы formation08:45–08:59МСК: **2694.73–2697.90**; доступны после08:59:59.999, probe09:00–09:29. Это НЕ previous15decisionwindow2691.54–2697.42 из предыдущего отчёта.

| Закрытие МСК | Наблюдение относительно frozen bounds |
|---|---|
|09:03:59,2694.72|Первый close ниже нижней границы|
|09:05:59,2694.99|Возврат внутрь после2outside closes|
|09:11:59,2694.21|Новый close ниже|
|09:15:59,2694.94|Возврат внутрь после4outside closes|
|09:22:59,2694.03|Третий outside episode вниз|
|09:22–09:29|8последовательных close ниже2694.73, без inside return до решения|
|09:30:16|DecisionNO; future candles не использованы|

Следовательно, были два наблюдаемых возврата, а затем продолжающийся выход вниз. К решению нельзя описать ситуацию как спокойную консолидацию внутри этого frozen window. Но bearish outside sequence тоже не гарантировала outcome: всё ещё важны openingH1=2694.74, remaining time и цена контракта. Более поздний разворот/проигрыш не добавлен в pre-entry features.

Независимый структурный разбор уже показал, что прежняя bearish тройка потеряла point3 и point1 до входа. Это отдельная система опорных pivots, не противоречие: уровень старой formation boundary и актуальная подтверждённая swing structure могут давать разный контекст.

## Проверка и оставшиеся ограничения

SHA256 всех22ZIP совпали с artifact digest;121closedM1 для каждого snapshot непрерывны; formation закончилась до probe; все30prefixes каждого condition воспроизвели ровно те же ранние события без будущего. Outside episode count независимо сверён с contiguous runs close-location. Decision previous15bounds/close/reference и source fingerprints совпали с предыдущими37saved diagnostic records. Embedded losing-case45candles и per-condition events/provenance сохранены; full raw остальных — в cited immutable ZIPs.

**Technical scoped verification PASS. Economic result INSUFFICIENT_DATA.** Нет изменённых model/fees/thresholds/holdout/cohort/workflows/concurrency/schedules, новых executions или PnL simulation. Только Limitless/public Binance offline sources.

Оставшийся вопрос — **формальное определение устойчивой консолидации и переходного режима**, а не доступ к данным. Для stable range нужно отдельно заранее описать formation, допустимость границ, stability/invalidation и UNKNOWN. Не выбирать хороший tolerance/число касаний/acceptance count по этой потере и затем выдавать тот же набор за независимый тест. Текущий mixed-structure prospective protocol не расширяется; новая trading version требует нового untouched evaluation.
