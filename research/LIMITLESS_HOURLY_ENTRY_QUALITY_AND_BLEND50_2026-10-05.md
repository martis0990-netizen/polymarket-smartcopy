# Limitless hourly: качество входов и один prospective shadow

**Время снимка:** main [run 37356516741](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37356516741), завершён 2026-10-05 19:26:09 UTC; 60 непрерывных успешных main ZIP с проверенными SHA256. Исходные 102 решения воспроизведены по Binance 1m и первой decision book, 19 исходных сделок погашены. Только discovery; это не вывод о будущей доходности.

## Что именно ухудшает результат

[Машинный аудит](LIMITLESS_HOURLY_ENTRY_QUALITY_EVIDENCE_2026-10-05.json) и [код](limitless_hourly_entry_quality.py) проверяют source fingerprint каждой использованной книги. Для Brier брали наблюдаемый YES исход и середину исходной decision book, не последующую цену исполнения.

| Измерение | Модель | Середина Limitless |
| --- | ---: | ---: |
| Brier по тем же 102 решениям, меньше лучше | 0.205101 | 0.207835 |

Разница model − market **−0.002734**, но 95% кластерный bootstrap по 54 UTC-часам **[−0.012442, +0.007411]** включает ноль. Недостаточно данных, чтобы считать прогноз стабильно лучше рынка. BTC: 50 решений, 9 погашенных входов, +29.493114326 USDC; ETH: 52 решения, 10 входов, **−6.407583472**. Особенно заметная *ретроспективно выбранная* группа ETH NO: 5 из 5 проиграли, **−42.708852362 USDC**, хотя сумма их модельных условных EV на фактических первых книгах была +8.791146904 USDC. Это гипотеза о слабой калибровке в хвосте, **не основание отключить ETH NO**. В грубой группе `p(YES)<0.2` всего 15 исходов, средняя оценка 0.129 против фактической доли YES 0.400; выборка мала и часы коррелируют.

Медианный YES спред в решающих книгах 0.048 USDC на контракт; среди 19 сделок медианная разница первой исполнимой VWAP и лучшей decision ask по купленной стороне +0.001892 USDC на контракт, положительная у 10/19. Это совместное влияние задержки, глубины и хода книги, не чистая оценка latency. Действующая модель уже учитывает свои 3% buy fee и 3% hurdle; механически повышать hurdle на 19 сделках нельзя. Позитивные +23.085530854 USDC исходной полной истории зависят от ETH выигрыша +51.071221619; без него −27.985690765. Отдельный funded inventory-v2 по тому же последнему архиву: **−19.602187197 USDC на 17 погашенных позициях**; он стартовал позже и не включает раннюю большую победу.

## Один зафиксированный будущий тест

[Протокол market blend50](LIMITLESS_HOURLY_MARKET_BLEND50_SHADOW_V1.md) был сохранён **до запуска ретроспективного sanity replay**: `p_shadow = 0.5*p_frozen + 0.5*decision_book_mid`, после чего применяются прежняя математика entry, комиссии, задержка и **первая** последующая книга. Отдельные счета frozen/shadow по 100 USDC, без заимствования. Решения для проспективного счёта только с **2026-10-06 00:00 UTC**. Конец первой оценки — после семи полных суток 6–12 октября и наблюдаемой выплаты последнего часа; меньше 30 погашенных shadow сделок → INSUFFICIENT_DATA. Другие веса или пороги не перебираются.

[Код shadow](limitless_hourly_market_blend_shadow.py), [полное доказательство sanity](LIMITLESS_HOURLY_MARKET_BLEND50_SANITY_EVIDENCE_2026-10-05.json) и [prospective WAITING](LIMITLESS_HOURLY_MARKET_BLEND50_PROSPECTIVE_STATUS_2026-10-05.json) сохранены раздельно. Sanity на тех же 102 уже известных решениях: shadow сделал **3** погашенных входа и условно +37.641023606 USDC; один BTC дал +43.914797722, остальные две сделки суммарно −6.273774116. Это **не** forward PnL и не подтверждённое преимущество. Данные после prospective cutoff ещё не наступили на момент снимка; отчёт prospective null.

```bash
PYTHONPATH=research python research/limitless_hourly_entry_quality.py manifest.json full_shadow.json --out entry_quality.json
PYTHONPATH=research python research/limitless_hourly_market_blend_shadow.py manifest.json full_shadow.json --cohort discovery-sanity --out sanity.json
PYTHONPATH=research python research/limitless_hourly_market_blend_shadow.py manifest.json full_shadow.json --cohort prospective --out prospective.json
```

`manifest.json` строится из 60 последовательных main run/artifact/hash в [полном hourly evidence](LIMITLESS_HOURLY_EWMA30_ALL_EVIDENCE_2026-10-05.json), дополненных локальными путями скачанных ZIP. Для следующих завершённых main ZIP сначала тем же [проверенным скриптом](limitless_hourly_ewma_full_shadow.py) пересчитывается новый `full_shadow.json`; ранние решения остаются только для source проверки, в новый счёт не импортируются. Скрипты читают публичные Limitless и Binance артефакты, не меняют работающий state и не размещают ордеров. Проспективная проверка ещё требует новых завершённых main ZIP и наблюдаемых выплат; работающий capture продолжает собирать данные без изменения графика.
