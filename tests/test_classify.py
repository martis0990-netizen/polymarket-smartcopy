from smartcopy.classify import classify_market
from smartcopy.models import MarketFamily


def test_crypto_updown_requires_explicit_horizon() -> None:
    result = classify_market(title="Bitcoin Up or Down - August 25")
    assert result.family is MarketFamily.UNKNOWN
    assert result.confidence < 0.5


def test_crypto_updown_5m_from_slug() -> None:
    result = classify_market(title="Bitcoin Up or Down", slug="btc-updown-5m-123")
    assert result.family is MarketFamily.CRYPTO_UPDOWN_5M
    assert result.confidence == 1.0


def test_crypto_threshold() -> None:
    result = classify_market(title="Will Bitcoin reach $100k this month?")
    assert result.family is MarketFamily.CRYPTO_PRICE_THRESHOLD
