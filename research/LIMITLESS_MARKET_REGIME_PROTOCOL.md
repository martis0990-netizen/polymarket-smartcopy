# Состояния рынка и структура старших ТФ: diagnostic v1

Статус: **FROZEN_DEFINITIONS_DIAGNOSTIC_ONLY**. Определения зафиксированы 4 октября 2026 до расчёта новой разметки. Уже просмотренные 37 discovery forecasts остаются discovery. Это отдельное исследование, а не изменение hourly-v1, inventory-v2 или [прежнего M1 протокола](LIMITLESS_STRUCTURE_VALIDATION_PROTOCOL.md).

## Вопрос и границы

Связаны ли ошибки замороженной вероятностной модели с состоянием рынка и вложенной структурой H4 → H1 → M15 → M5/M1? Геометрия графика и вероятность закрытия относительно открытия часа — разные задачи. Ни одно состояние само по себе не создаёт BUY/SELL/SKIP или новый p.

Только уже сохранённые main Limitless independent market capture ZIP и публичные Binance BTCUSDT/ETHUSDT M1. Нет API запросов, новых workflows, изменения сбора, fees, sizing, holdout или торгового исполнения. Verified Binance hourly decisions, включая NO_TRADE; Chainlink TWAP60 15m остаются вне модели.

## Данные и причинность

1. Manifest содержит artifact id, GitHub ZIP digest и проверенный run: main, non-pull_request, completed success, правильное имя workflow и head SHA. Каждый ZIP сверяется с digest. State ZIP обязан принадлежать этому manifest. Читается один cumulative state; отчёты сегментов не суммируются.
2. Валидируется OHLC, положительные конечные цены, M1 open/close boundaries, request/receipt с timezone, Binance source, symbol/interval. Незакрытая на request-start свеча исключается даже при более позднем receipt. При ошибке response целиком отклоняется; top-level report=null/UNRECONCILED.
3. Для каждой закрытой минуты сохраняется самое раннее receipt исходного response. Поздний конфликт OHLC видим только после своего receipt. На decision используются только уже полученные свечи. Конфликт делает состояния UNKNOWN; позднее исправление не заменяет прежний снимок.
4. M5/M15/H1/H4 собираются по UTC только из полного набора M1. Пробел разрывает warmup. Последний ожидаемый закрытый бар должен присутствовать. OHLC completeness не доказывает непрерывность биржевого наблюдателя: пропуск job может позже покрываться историей в response.
5. Availability старшего бара — max receipt его минут. Availability события — max availability исторического префикса до его подтверждения. Бар времени события и время, когда мы смогли узнать о нём, хранятся отдельно. Это восстановленная геометрия доступного price path; не утверждение, что в прошлом был исполнен сигнал.

## Зафиксированные определения

Это наши операционные определения, а не единственная трактовка ICT/Smart Money или механическое воспроизведение Wyckoff. Параметры не выбирались по PnL и не будут перебираться на этом evaluation окне.

- Каждый ТФ: минимум **16** непрерывных полных баров. Это минимальный барьер данных, не гарантия достаточности swings или устойчивости состояния. Истории с подтверждёнными swings может требоваться больше.
- Pivot: **2 слева / 2 справа**, strict left/non-strict right. Известен только после закрытия и получения правых баров. Dual high+low исключается. Последовательные same-kind pivots нормализуются в более крайний; raw pivot/event history остаётся неизменной.
- UP swing geometry: последние два highs и lows повышаются; DOWN — понижаются. Mixed/equal не превращается автоматически в консолидацию или разворот.
- **TREND_UP / TREND_DOWN:** согласованные swings и последующее строгое пересечение закрытием уже подтверждённого high/low в том же направлении. Защищённый anchor копируется из последнего противоположного confirmed swing при подтверждении/BOS; новый локальный pivot сам его не переносит. Противоположный micro break не переписывает сохранённый тренд.
- **TRANSITION:** закрытие нарушило protected anchor или вышло из confirmed range. Это кандидат смены режима. Wick без outside close его не создаёт. Новый тренд подтверждается только после образования новой согласованной последовательности из двух highs и двух lows с pivot times после исходного break и последующего aligned close break. Может восстановиться прежнее направление; переход не обязательно заканчивается разворотом.
- **UNKNOWN:** недостаточный warmup/swings, missing latest bar, конфликт источника или ещё нет подтверждённого режима. UNKNOWN сохраняется в denominator.

## Диапазон: три точки и дополнительное подтверждение

После снижения: prior low → более низкая точка1 LOW → отскок HIGH2 → повторный LOW3. Для зеркального сценария направления меняются. Это конечная геометрия, не доказательство институциональной ликвидности или accumulation/distribution.

На подтверждении точки3 вычисляется простая средняя true range последних 14 баров этого ТФ (**ATR14 SMA**, не Wilder). Минимальная ширина точки1–2 = **1 ATR**; допустимое отличие точки3 от точки1 = **0.25 ATR**. От точки1 до текущего подтверждения все closes должны оставаться внутри исходных границ. Эти значения — исходная спецификация diagnostic v1, не оценка оптимального торгового фильтра.

Три точки дают **RANGE_CANDIDATE**, а не confirmed consolidation. Границы точки1–2 и tolerance замораживаются. Следующий противоположный confirmed pivot у второй границы (в той же tolerance) подтверждает **RANGE**: четыре чередующиеся реакции. Любое последующее outside close отменяет candidate либо переводит confirmed range в TRANSITION. Границы не расширяются задним числом. Candidate может оставаться неподтверждённым; мы не называем его диапазоном. Sweep/возвраты — отдельные события, их наличие не доказывает stop hunting или fill.

## Иерархия и фаза

- H4 и H1: отдельные состояния/защищённые уровни/границы. Оба должны быть известны, чтобы top_down_context=READY. При UNKNOWN H4 нельзя назвать M15 полной разметкой старшего контекста.
- H1/M15: совпадение направленных trends = ALIGNED_TRENDS; противоположные trends = CORRECTION_CANDIDATE, а не доказанный откат; H1 RANGE/TRANSITION выделяются отдельно. Несогласованный/неизвестный контекст остаётся UNKNOWN_OR_OTHER. Это связь, не голосование таймфреймов.
- M5/M1: локальные подтверждения и события. Они не переопределяют H4/H1.
- Limitless: сохраняются original p_up, opening, reference, расстояние до opening и время до конца часа. В рамках v1 никаких новых probability weights или контрактных покупок нет.

## Проверка и этапы

**Сейчас:** аудит доступности, причинная разметка 37 уже просмотренных discovery decisions, counts всех состояний и UNKNOWN, отдельные примеры. Не ищем выгодную комбинацию и не сравниваем выдуманный trade PnL. Модуль offline: `limitless_market_regime.py`; целевые тесты включают every-prefix invariance, protected anchor, wick vs close, 3/4 points, gaps, earliest receipt и future conflicts.

**Новые данные:** только ещё не просмотренные outcomes 6 октября 00:00 UTC — существующий cutoff 10 октября 09:00 UTC. Это secondary descriptive diagnostic, не замена primary mixed-M1 contrast прежнего протокола. Показывать по H1 состояниям (и отдельно HTF-ready subset) n, UTC hour clusters, Brier, confidence и favourite accuracy; UNKNOWN и неполные hierarchy не удалять. Единица зависимости — UTC hour cluster. Не выбирать лучший TF, окно, tolerance, asset или cutoff по результату. H4 warmup может не покрыть начало окна; считать фактическую полноту до любых выводов. Никаких новых автоматизаций или cron в этом PR.

**После:** если связь воспроизводится и данных достаточно — отдельная новая версия probability model/filter, зафиксированная до нового untouched evaluation периода. Те же outcomes после настройки не считаются независимым holdout. Технический PASS причинности не является доказательством прибыльности.

## Источники и пределы переноса

- [Binance market data / klines](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market): schema, времена и UTC aggregation.
- [FXOpen: ICT concepts](https://fxopen.com/blog/en/what-are-the-inner-circle-trading-concepts/): объяснение top-down context и различия локальной/старшей структуры; это образовательная трактовка автора.
- [Wyckoff Analytics: Anatomy of a Trading Range](https://www.wyckoffanalytics.com/wp-content/uploads/2019/08/AnatomyofaTradingRange.pdf): stopping action, automatic reaction, secondary test. Наш 3/4-point classifier не является полной Wyckoff phase/volume model.

Источники проверены 4 октября 2026. Конкретные 16 bars, 2/2, ATR1 и tolerance0.25 — решения нашего протокола; источники не доказывают их эффективность.
