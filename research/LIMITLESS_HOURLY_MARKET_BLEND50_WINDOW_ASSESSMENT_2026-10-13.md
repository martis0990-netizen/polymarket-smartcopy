# Limitless hourly market-blend50: оценка окна 6–12 октября 2026

**Срез:** 13 октября 2026, 12:45 UTC. **Решение: INSUFFICIENT_DATA / WAIT.** До закрытия заранее заданного окна нет полного основного ряда и наблюдаемой выплаты последнего часа. Экономический отчёт за неделю — `null`; прибыльность варианта не утверждается.

## Зафиксированное правило

[Протокол v1 в PR #54](https://github.com/martis0990-netizen/polymarket-smartcopy/blob/8b8ede43161906c5ba31df67424d953a574e5294/research/LIMITLESS_HOURLY_MARKET_BLEND50_SHADOW_V1.md) задаёт решения `2026-10-06T00:00Z <= decision_at < 2026-10-13T00:00Z`, веса модели и первой decision book по 0,5, отдельные funded-счета по 100 USDC, старые комиссии/задержку/hurdle и только первую попытку исполнения. Порог оценки: не менее 30 погашенных входов shadow, полные семь суток и наблюдаемая выплата последнего часа. Скрипты `limitless_hourly_ewma_full_shadow.py` и `limitless_hourly_market_blend_shadow.py` находятся в PR #54; в main их нет. Не допускается перенести ретроспективные сделки в проспективный счёт.

## Что доставлено

GitHub Actions проверены постранично, с фильтром `Limitless independent market capture`, `head_branch=main`, `event!=pull_request`, `completed success`. После начала окна есть **35 успешных main запусков с одним архивом каждый** и семь отменённых запусков; отменённые не использованы как данные. Для всех 35 получены metadata артефактов, включая ID и заявленный digest. Последний успешный run [37588187303](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37588187303), artifact 11470560416, окончил capture **7 октября в 08:30:08 UTC**. Следующий run [37594185151](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37594185151) отменён. Успешных main capture за остаток 7–12 октября не найдено.

От последнего доставленного конца до конца зафиксированного окна отсутствуют **135,50 часа**. Даже максимально возможная доля времени от начала окна до последнего capture — только **19,35%**; фактическое покрытие raw receipts здесь не измерено и может быть ниже. Последний час 12 октября не доставлен. Это уже блокирует запланированную семидневную оценку независимо от числа сделок и знака PnL.

[Ранее опубликованный основной checkpoint 6 октября 09:25 UTC](https://github.com/martis0990-netizen/polymarket-smartcopy/blob/main/research/LIMITLESS_HOURLY_BLEND50_EXPANDED_CHECK_2026-10-06.md) проверил первые 14 проспективных решений: blend50 0 входов, frozen comparator 0 входов, оба бумажных PnL 0. Этот checkpoint не включает последующие решения и не заменяет итоговый реплей. Отдельные три прибыльные retrospective sanity сделки до 6 октября исключены из проспективной оценки.

## Проверки, которые нельзя закрыть

Connector вернул ссылку на последний ZIP, но локальный сетевой шлюз отклонил получение бинарного файла (proxy port 8889); прямое DNS-соединение также недоступно. Поэтому **SHA256 всех 35 ZIP в этой проверке независимо не сверен**, текущие `ewma_full_shadow` и `market_blend_shadow --cohort prospective` на полном ряду не запускались. Предыдущее [ревью от 10 октября](https://github.com/martis0990-netizen/polymarket-smartcopy/blob/7d4f980a384248dddf0a391e6abc88499f65ab27/research/LIMITLESS_FINAL_REVIEW_2026-10-10.md) отдельно сверило ZIP последнего run: `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`, что совпадает с текущим GitHub artifact digest. Это ограниченное предыдущее подтверждение, не подмена проверки всей цепи в настоящем отчёте.

Итоговые frozen reproduction, первые Binance 1m/decision/execution proofs, наблюдаемые payout, cash conservation, BTC/ETH, крупнейший выигрыш, drawdown и часовые кластеры остаются **непроверенными для всего prospective ряда**. Полные settled trade count и PnL неизвестны, а не равны нулю. Статус `UNRECONCILED` для ledger не присвоен: конкретного противоречия raw источников не обнаружено, но и полного реплея нет.

Критерий улучшения и прибыльности по версии v1 **не выполнен**. Продолжать этот же семидневный тест задним числом или менять окно на основании уже увиденных результатов нельзя. Рабочие hourly-v1, inventory-v2, комиссии, пороги, расписание и реальные ордера не менялись.

[Машинные доказательства](evidence/limitless_blend50_window_assessment_2026-10-13.json) содержат все 42 main run записи за доступный участок, artifact IDs/digests 35 успешных запусков и границу проверки.
