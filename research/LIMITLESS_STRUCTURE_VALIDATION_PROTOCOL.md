# Структурный режим: заранее заданная проверка на новых данных

Статус: **SPECIFIED_DIAGNOSTIC_ONLY_NOT_TRADING_POLICY**. Фиксация4 октября2026 до начала hourly holdout6 октября00:00UTC. Основание — discovery37forecasts; этот набор не становится independent evaluation. Протокол не меняет текущие hourly/inventory версии, p, fees, thresholds, sizing, control, workflow, concurrency или сбор.

## Исследовательский вопрос

Повторяется ли на новых данных повышенная ошибка/избыточная уверенность zero-drift probability model при mixed/equal confirmed M1 swing структуре по сравнению с согласованной HH/HL или LH/LL структурой?

Это проверка признака, не новая торговая стратегия. Цены, ордера и capital не изменяются. Ни один condition не исключается из основного отчёта из-за структуры. Новый p и forward residual-value filter не определены и не должны быть придуманы по результату этой проверки.

## Вход и неизменные определения

- Все independently scored BTCUSDT/ETHUSDT verified Binance hourly decisions, включая NO_TRADE. Chainlink15m исключены. Split payouts не входят в binary calibration, финансовый основной отчёт сохраняет их по действующим правилам.
- Только исходный Binance response, уже received до решения; closed candles отсекаются по min(request_start, decision_time). Послефактум реконструированная свеча не заменяет decision-time источник.
-121закрытая непрерывнаяM1, как в текущем диагностическом срезе. Недостаток/warmup/unknown source остаётся UNKNOWN и отдельно отражается; future/backfill не исправляет ранний snapshot.
- Pivots2left/2right: strict left/non-strict right, available после rightmost close. Same-kind extremes нормализуются; ambiguous dual-pivot bars исключаются. Никаких новых period/lookback sweep.
- Последние два confirmed highs+lows: HH+HL=UP, LH+LL=DOWN, остальные=MIXED_OR_EQUAL; недостаток=INSUFFICIENT_SWINGS. Break direction не переопределяет эту классификацию.
- Original p_up и terminal observed payout остаются исходными. Confidence=max(p_up,1−p_up); correctness относится к предпочтению модели, а не к фактической купленной стороне.

## Выборка и показатели

Independent assessment — ещё не просмотренные outcomes **6 октября00:00UTC до fixed collection cutoff10 октября09:00UTC**. Discovery3–5 октября показывается отдельно, не включается в primary new-data contrast. Период заканчивается по существующему cutoff; это не новая автоматизация и не изменение сбора.

Primary descriptive contrast: mean Brier в mixed/equal минус mean Brier в объединённых HH/HL и LH/LL groups. Положительная разница означает больше ошибки в mixed group на этом окне. Дополнительно заранее показываются n, distinct UTC hours, mean confidence и realized favourite accuracy всех четырёх groups, включая UNKNOWN. Unknown не удаляется из denominator без явного отчёта.

При оценке неопределённости единица зависимости — UTC hourly cluster, а не отдельные BTC/ETH conditions. Показывать uncertainty и концентрацию, не выдавать event count за независимую выборку. Существующие60conditions/60resolved hours и coverage gates не меняются и не заменяются новой выгодной границей. Редкая/пустая group или слабое coverage => INSUFFICIENT_DATA, не искусственный PASS. Не называть difference статистически доказанным без соответствующей кластерной оценки.

Последние breaks/смена их направления за30мин остаются secondary descriptive checks. Нет поиска лучшего периода, порога RSI, ATR-множителя, asset subset, исключения проигрышей или выбора промежуточного момента с красивым результатом.

## Как интерпретировать

- Повторение разницы на новых данных поддерживает дальнейшее исследование regime/calibration, но не подтверждает прибыль фильтра.
- Отсутствие/обращение разницы — отрицательный результат, правила не адаптируются на этом evaluation окне.
- Любой будущий p adjustment или SKIP policy требует отдельной явно заданной версии до **нового** evaluation окна. Проверенные outcomes этого протокола нельзя после настройки вновь считать untouched holdout новой стратегии.
- Фактические paper позиции/PnL остаются из основной frozen ledger. Сравнение «какой PnL вышел бы без mixed» не подменяет контролируемый prospective trade test.

Запуск протокола — offline разметка существующих raw artifacts без новых API запросов или production hooks. В текущем PR сохранены только определения/план и discovery анализ; новый trading executor не реализован. Ключи, подписи, реальные ордера и другие venues отсутствуют.
