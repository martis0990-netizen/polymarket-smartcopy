# Limitless: геометрия swings и положение внутри ценового окна

Проверка4 октября2026. Фиксированный срез37scored discovery decisions /19UTC hourly clusters до08:23UTC, source as-of08:27UTC. Pinned main `ac7ce6a2166a230bf7aabf6fb2fbe892719b64eb`. [Machine evidence](evidence/limitless_range_location_2026-10-04.json).

**SAVED_FEATURE_RECOMPUTATION_NOT_CONFIRMED_CONSOLIDATION_NOT_STRATEGY.** Это следующий ограниченный разбор после [структуры](LIMITLESS_STRUCTURE_MODEL_ERRORS_2026-10-04.md) и [последовательности1–2–3–4](LIMITLESS_REFERENCE_PATTERN_CHECK_2026-10-04.md). Торговые rules,p,fees,holdout,cohort,workflow/concurrency/schedule не изменены.

## Смешанная структура неоднородна

| Последние две подтверждённые пары swings | Conditions |
|---|---:|
|HH+HL, rising|13|
|LH+LL, falling|13|
|HH+LL, expanding|5|
|LH+HL, contracting|6|

Таким образом11mixed случаев делятся на5расширяющихся и6сужающихся. **Contracting не означает подтверждённую устойчивую консолидацию**; это только понижение последнего high и повышение последнего low. Expanding тоже не является автоматически торговым диапазоном. Для стабильной консолидации нужны заранее заданное правило формирования/фиксации границ и последовательные наблюдения. Здесь такого classifier нет, поэтому stable_consolidation=UNVERIFIED, а не отрицательный или положительный сигнал.

## Границы и положение цены: уже посчитано

На всех37snapshots сохранены:
- lower/upper: min/max предыдущих15closedM1, исключая последний сигнальный бар; прежнее диагностическое окно, без sweep;
- width и width/M1 ATR14;
- position=(price−lower)/(upper−lower) отдельно для last closed M1, decision reference price и hour opening;
- последние две confirmed highs/lows и их envelope;
- WITHIN/ABOVE/BELOW без обрезания позиции до0–100%.

0%=нижняя граница,100%=верхняя. Отрицательное значение означает цену ниже окна, больше100% — выше. Категории «верхние20%» и подобные trading thresholds не введены. Последний закрытый close был внутри previous15envelope в31случае, выше в2, ниже в4. Это **не31консолидация**: extrema существуют у любого окна даже в тренде.

M1 ATR14 измеряет минутные колебания. Width12ATR не означает, что цена исчерпала дневной/часовой ATR. Current partial-bar reference отделён от закрытого close: смена их положения не является подтверждённым close-based breakout.

## Проигрышный ETH

Decision06:30:16UTC /09:30:16МСК. Геометрия последних confirmed swings **EXPANDING**: high2695.00→2697.42, low2694.63→2694.05.

| Previous15closedM1 envelope | Значение |
|---|---:|
|Нижняя граница окна|2691.54|
|Верхняя граница окна|2697.42|
|Ширина|5.88|
|Последний закрытый close|2691.72|
|Положение закрытого close|3.06%|
|Decision reference price|2691.25|
|Положение reference|−4.93%, ниже окна|
|Цена открытияH1|2694.74|
|Положение открытияH1|54.42%|
|Ширина /M1 ATR14|12.26|

В момент решения цена находилась у нижнего края недавнего окна по closedM1, а reference уже ниже него. Нельзя назвать это готовым отбоем от нижней границы: для отбоя требуется наблюдаемое возвращение, а для принятого выхода — отдельное заранее заданное подтверждение. Также last-two-swing envelope2694.05–2697.42 уже был пробит вниз; он не является неповреждённым диапазоном. Эти признаки не дают сами по себе BUY YES/NO.

ОткрытиеH1 внутри previous15window. Даже движение от нижней границы к середине не гарантирует закрытие выше opening, а отбой может быть правильно распознан и всё равно не дать прибыльной цены prediction contract.

## Верификация и точные ограничения

Результат вычислен из двух pinned GitHub machine evidence: indicator_all_forecasts и structure_snapshot.37condition IDs, artifact/run и source fingerprints совпали. Все использованные pivots confirmed до decision; partition13/13/5/6 воспроизводит исходную swing structure. Обратный расчёт position воспроизводит цены; ATR distances совпали с независимо сохранёнными indicator fields. Проверка arithmetic/identity PASS, ошибок0.

**Локальная среда недоступна в этой проверке**, поэтому ZIP/raw candles повторно не читались. Предыдущая raw causal/digest verification сохранена в cited source artifacts; не выдаётся за новую. Ordered touch/sweep/re-entry/acceptance и полный стабильный range classifier НЕ пересчитаны. Boundary touch and rejection sequence=NOT_RECOMPUTED. Экономические преимущества/фильтрованный PnL не оценены.

## Оставшийся следующий шаг

После восстановления доступа к raw replay сначала отдельно зафиксировать определение stable range: как формируются две границы, когда становятся доступными и когда ломаются. Отдельно описать expanding/contracting/transition и missing warmup. Затем причинно разметить ordered touches, wick excursions, close возвращения и выходы; early label не получает future confirmation.

В этом PR устойчивость консолидации оставлена UNKNOWN. Известные37outcomes служат discovery, не independent qualification. Для нового probability/filter потребуется отдельная версия и новый untouched evaluation. Уже зафиксированный mixed-structure protocol и основной holdout не расширяются и не перенастраиваются.

Только saved Limitless/public Binance research data. Нет новых market HTTP запросов, других venues, keys,signing,live orders или production hooks.
