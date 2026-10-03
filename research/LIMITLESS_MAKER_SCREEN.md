# Limitless maker: протокол первичной диагностики

Зафиксирован 2026-10-03 до расчёта метрик; exploratory historical screen, не новый prospective trading experiment. Цель — оценить ширину котировок и скорость их устаревания на уже собранных данных. Прибыль, исполнения и maker eligibility из этих данных не выводятся. Frozen hourly/inventory-v2, их капитал и holdout не меняются.

## Ограниченный протокол

- Только completed successful main capture ZIP, перечисленные в явном manifest с run/artifact/head/SHA256. PR исключены. Одинаковый ZIP учитывается один раз; перекрывающиеся сегменты отклоняются, разрывы не заполняются.
- Только BTC/ETH Binance-settled hourly single CLOB: используем текущую `market_identity`, Base USDC и отдельные YES/NO токены. Metadata должна быть уже записана до WS frame и не старше120с. Активное окно: от start до end−60с. 15m Chainlink исключены.
- Только WS `orderbookUpdate` с точным slug/YES token, числовой версией и aware source/receipt timestamps. Source не позже receipt, возраст <=2с. Receipt не считается временем изменения биржей. Полный book валиден, обе стороны непустые, 0<bid<ask<1. Цены/размеры конечные, размеры /1e6.
- Одинаковая версия/одинаковый book повторно не учитывается. Одинаковая версия с другим book — ошибка, condition исключается из отчёта. Уменьшение версии/времени источника разрывает цепочку; поздний старый frame не используется. Restart publisher без подтверждённого нового epoch не восстанавливается догадкой. Пропуски значений version не считаются потерянными событиями.
- Disconnect, повторная subscription, невалидный frame и gap>2с разрывают цепочку. Между ZIP цепочки не сшиваются. Это намеренно строгий предел доступности наблюдений, не SLA биржи.
- Anchor: первый пригодный frame в каждом UTC30s bucket на condition. Во всех anchors рассматриваются одни и те же hypothetical bids: YES=bestYesBid, NO=1−bestYesAsk; размер по10 shares на сторону, без заявки/списания cash. Записывается глубина уже стоящих заявок на этих ценах; это не подтверждённое место нашей заявки в очереди.
- Горизонты1/5/15/30с фиксированы. Берётся первый frame не раньше anchor+horizon, максимум horizon+2с, только в той же непрерывной цепочке. Если его нет — UNKNOWN, без forward fill. Все четыре горизонта публикуются, лучший не выбирается.
- Диагностика: spread; source-to-receipt lag; время до первого наблюдаемого изменения BBO (цен) в пределах30с; signed midpoint movement и `min(futureMid−bid, ask−futureMid)`. Последнее — запас двух старых котировок относительно будущего midpoint, не cash PnL, не fair value и не результат условно исполненной заявки. Положительное значение не доказывает прибыльность maker: реальные исполнения могут происходить именно в плохих состояниях.
- Binance reference: только ранее полученная public1m candle, request<=receipt<=anchor, возраст<=10с, текущая candle покрывает anchor. Сравнение цены на доступных anchor/follow-up timestamps — изменение базового актива, не прибыль бинарного контракта. Нехватка reference отражается отдельным знаменателем.
- minSize учитывается только как минимальный размер для LP rewards: размер10shares может быть меньше. Maker rebates и LP rewards разные программы; доход ни по одной не рассчитывается.
- Сводка содержит sample counts, distinct conditions/hour clusters, отдельные строки по каждому condition; anchors/WS frames не считаются независимыми сделками. Все snapshots одного часа зависимы.

## Решение после screen

Результат всегда `DIAGNOSTIC_ONLY_NO_FILL_MODEL`, либо `INVALID_INPUT` при ошибке manifest/archive/identity conflict. PnL и fill probability=null. Нельзя выдать GO_LIVE или положительное ожидание по благоприятным midpoints. Отрицательное движение помогает установить требования к отмене/перекотированию, но без conditional-on-fill данных не доказывает убыточность всех maker-стратегий.

Следующий шаг возможен только как отдельная заранее зафиксированная shadow-policy с ценой/размером, задержками и причинами отмен. До оценки её PnL нужны фактические order lifecycle/fill evidence либо проверенная модель очереди. Текущий public coalesced stream этого не даёт. Не добавлять индикаторы или оптимизировать горизонты по этому срезу.

Источники механики, прочитаны2026-10-03:
- https://docs.limitless.exchange/developers/websocket/market-data — full coalesced book, version, replay snapshots, отсутствие общего WS trade feed.
- https://docs.limitless.exchange/api-reference/trading/orderbook — YES/NO inversion, units, reward minSize, отсутствие гарантии freshness.
- https://docs.limitless.exchange/user-guide/fees — maker/taker fees.
- https://docs.limitless.exchange/user-guide/maker-rebates — отдельно от LP size eligibility.
