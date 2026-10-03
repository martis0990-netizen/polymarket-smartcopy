# Limitless: план алгоритма стоимости и инвентаря v1

Фиксация: 2026-10-03. Цель — проверить, улучшает ли управление позицией результат собственной hourly probability model после расходов. Результат не гарантирован. Полный селективный maker-алгоритм — цель следующих этапов; эта версия запускает независимый funded paper-вариант HOLD / SELL / COMPLETE_PAIR. Это не копия закрытого алгоритма Bonereaper.

## Этапы и критерии перехода

| Этап | Работа | Статус / критерий |
|---|---|---|
| 1 | Инвентарь, собственный cash ledger, сравнение трёх действий, задержка и первый execution attempt, settlement, checkpoint | Реализован в limitless_inventory_paper.py, интегрирован в capture |
| 2 | Проверить калибровку вероятности и преимущество управления на новых условиях | Сбор. Нет допуска по одному удачному merge или synthetic test |
| 3 | Селективные maker-котировки вокруг fair value, inventory skew, отмена устаревших заявок | До реализации fill/PnL нужны tick rules, order-event semantics, модель очереди, cancel latency и условное adverse selection |
| 4 | Проверить реальное исполнение минимальным объёмом | Вне текущего разрешения: отдельное решение после прохождения исследовательских gates |

Исходный limitless-hourly-v1, его сигналы, размер, контроль constant50 и окна discovery/holdout не меняются. Wallet SmartCopy — отдельное исследование. Новый inventory_paper имеет свою version, started_at, cash, positions и report; не перезаписывает hourly paper state. Дополнительных HTTP-запросов нет.

## Алгоритм этапа 1

1. Скопировать в независимый виртуальный ledger только новый model paper fill, чьи decision_at и fill_at не раньше started_at новой версии. Старые позиции из checkpoint не импортируются. Подтвердить single CLOB, Binance-settled hourly spec, токены и Base USDC. Входы constant50 не используются.
2. Списать стоимость из cash; исходный cash=100 USDC, вход <=10 USDC, никаких займов. Это заданный исследовательский капитал, не пользовательский депозит. При нехватке денег условие окончательно SKIP.
3. На первом последующем book attempt получить текущую вероятность из неизменённой hourly._inputs: одинаковые oracle/open-price/time/freshness правила. Отсутствующие inputs/book → SKIP управления, позиция удерживается до settlement. Нельзя искать поздний удачный момент.
4. Оценить HOLD, SELL непарного остатка и COMPLETE_PAIR. Для портфеля YES=y, NO=n использовать минимальное `p*y + (1-p)*n` на двух концах диапазона p±0.03, clipped[0,1]. Пара не теряет свою выплату из-за двойного независимого дисконта двух сторон. ±0.03 — инженерный stress, не confidence interval и не измеренная точность модели.
5. SELL: полный видимый bid-depth для непарного остатка, sell fee1.5% от USDC. COMPLETE_PAIR: gross buy quantity округляется вверх до 1e-6 так, чтобы после buy fee3% хватило net shares. Покупка противоположной стороны допускается только при положительном locked profit после исходной себестоимости и merge reserve, запасе >=2% от стоимости пары, cash >= cost+reserve и cumulative condition spend <=20 USDC. Не усреднять исходную сторону.
6. Выбрать действие с максимальным conservative value; улучшение менее0.02 USDC → HOLD. Сохраняются все альтернативы, p, observed/reference times, quantity и худшая допустимая цена. Исходная себестоимость — отдельное ограничение locked profit, не замена сравнения будущих денежных потоков.
7. SELL/COMPLETE_PAIR исполняются только на первом последующем запросе после takerDelayMs+1s, receipt <=decision+30s и до expiry. Проверить YES token, depth и неизменную price bound. Первый error/bad depth/bad price остаётся SKIP; повторных поисков котировки нет. Не более одного решения управления на условие.
8. В paper COMPLETE_PAIR списать стоимость покупки, обновить net inventory, затем предположить успешный merge общей части с резервом0.01USDC. Этот резерв не измеренная chain fee. Дробный излишек после округления остаётся в инвентаре, не исчезает. SELL списывает cost basis проданного остатка. Записывать cash, cost basis и realized PnL по балансовому тождеству.
9. Применять только наблюдаемое RESOLVED после expiry: binary winner или проверенные неотрицательные payoutNumerators. Unresolved остаток остаётся открытым. Считать managed и seed-hold итог на одинаковых admitted settled условиях; отдельно показывать interim realized PnL и открытый cost basis.

## Что это проверяет и что не доказывает

Парная прибыль может уступить удержанию победившей стороны. Реализованный плюс по merge не означает положительный общий результат: открытая направленная позиция может потерять всю себестоимость. Поэтому отчет содержит cash, open_cost_basis, realized_pnl, managed_settled_pnl и seed_hold_settled_pnl. Каждый report накопительный; отчёты сегментов нельзя суммировать.

Базовый fill — уже бумажное предположение hourly benchmark о доступности REST depth. Новый ledger не превращает его в подтверждённое реальное исполнение. SELL/COMPLETE_PAIR также предполагают доступность depth после задержки. Нет реальных orders, транзакций merge, подписей, wallet funds, rewards/rebates и maker queue fills. Комиссии — консервативные заданные paper assumptions; точные execution fees неизвестны.

При гипотетическом merge прибыль учитывается после assumed successful merge. Приёмка этапа2 требует чувствительности к chain cost/latency; нельзя выдавать0.01 резерв за гарантированный потолок расходов.

Discovery начинается только с first main started_at новой версии; до6 октября UTC — discovery, с6 октября — prospective holdout фиксированной версии. Исторический replay этой новой политики всегда retrospective, даже если timestamps попадают в календарное holdout. Перенос checkpoint сохраняет started_at; несовместимая version или нарушение cash+basis =100+realized_pnl вызывают явный отказ.

## Приёмка и следующий шаг

Проверить: net/gross fees, inversion YES/NO, funding cap, pair payoff, stale/future inputs, no same-snapshot management, delay/deadline/token/first-failure, split settlement, restart/idempotence, cash/basis identity. Проверить GitHub PR capture и фактическое появление inventory_paper_report.json и inventory_paper в state.json. PR данные исключить из основной выборки. Первое main действие/settlement остаётся отдельной приёмкой, если за smoke окно сигналов нет.

Этап2: не менее60 новых admitted resolved conditions и60 разных hourly clusters, >=90% релевантного покрытия и анализ концентрации/пропусков; это порог возможности анализа, не доказательство edge. Если fill rate модели нулевой или выборка мала, INSUFFICIENT_DATA; не снижать пороги по прибыли. Сравнить managed vs seed-hold на совпадающих условиях, NO_TRADE и отдельный frozen constant50 контроль, не смешивать разные admitted subsets. Оценить разброс по часовым кластерам и возможную ошибку вероятности. Сохранить исходный holdout.

Для этапа3 измерять вероятность исполнения и ухудшение справедливой цены после предполагаемых maker fills; собственный стакан не показывает место в очереди. Даже закрытая прибыльная пара не должна скрывать убытки всех непарных позиций. Не запускать touch-fill simulator с оптимистичным PnL.

Официальные механики (проверено2026-10-03):
- https://docs.limitless.exchange/user-guide/fees
- https://docs.limitless.exchange/user-guide/merge-split
- https://docs.limitless.exchange/api-reference/trading/orderbook

Итоговый final audit дополнительно публикует limitless_inventory_final_report.json: берётся последний накопительный checkpoint, проверяются lineage/неисчезновение позиций/immutable entry и terminal management. При конфликте report=null и UNRECONCILED_CHECKPOINTS; суммы сегментов не используются.
