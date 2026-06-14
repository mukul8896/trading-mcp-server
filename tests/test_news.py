"""News parsing, filtering, and market-sentiment aggregation (network-free)."""
import pytest

from trading_mcp_server.services import data_provider_service as data


def _article(symbol, name, sentiment, sub_category, title="t", text="x", sector="Healthcare"):
    return {
        "news_object": {"overall_sentiment": sentiment, "title": title, "text": text},
        "category": "companies",
        "sub_category": sub_category,
        "stock_name": name,
        "sm_symbol": symbol,
        "publish_date": 1781416678117,
        "metadata": {"sector_name": sector},
    }


SAMPLE = [
    _article("RELIANCE", "RELIANCE INDUSTRIES LTD", "positive", "earnings-financial-results"),
    _article("INVICTA", "INVICTA DIAGNOSTIC LTD", "neutral", "corporate-actions"),
    _article("WOL3D", "WOL 3D INDIA LIMITED", "negative", "legal-compliance"),
]


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def mock_feed(monkeypatch):
    payload = {"data": {"latest_news": SAMPLE, "next_news": []}, "status": 200}
    monkeypatch.setattr(data.requests, "get", lambda *a, **k: _Resp(payload))


def test_fetch_all_returns_flattened_items(mock_feed):
    items = data.fetch_market_news()
    assert len(items) == 3
    first = items[0]
    assert first["symbol"] == "RELIANCE"
    assert first["sector"] == "Healthcare"
    assert set(first) >= {"symbol", "stock_name", "title", "text", "sentiment",
                          "category", "sub_category", "sector", "publish_date"}


def test_sentiment_filter(mock_feed):
    assert {i["symbol"] for i in data.fetch_market_news(sentiment="positive")} == {"RELIANCE"}
    assert data.fetch_market_news(sentiment="positive")[0]["sentiment"] == "positive"


def test_category_matches_subcategory(mock_feed):
    # the real feed only ever has category == "companies"; sub_category is the
    # useful dimension and must match through the same param.
    hits = data.fetch_market_news(category="legal-compliance")
    assert [i["symbol"] for i in hits] == ["WOL3D"]
    assert data.fetch_market_news(category="companies")  # category still works


def test_symbol_matches_exact_and_name_substring(mock_feed):
    assert data.fetch_market_news(symbol="WOL3D")[0]["symbol"] == "WOL3D"
    # substring of company name also hits
    assert data.fetch_market_news(symbol="INVICTA")[0]["symbol"] == "INVICTA"
    assert data.fetch_market_news(symbol="NOTLISTED") == []


def test_summarize_market_sentiment(mock_feed):
    summary = data.summarize_market_sentiment()
    assert summary["total_items"] == 3
    assert summary["tally"] == {"positive": 1, "negative": 1, "neutral": 1}
    assert summary["overall_mood"] == "neutral"
    assert summary["percent"]["positive"] == pytest.approx(33.3)
    assert summary["top_positive"][0]["symbol"] == "RELIANCE"
    assert summary["top_negative"][0]["symbol"] == "WOL3D"


def test_summarize_handles_empty_feed(monkeypatch):
    payload = {"data": {"latest_news": [], "next_news": []}}
    monkeypatch.setattr(data.requests, "get", lambda *a, **k: _Resp(payload))
    summary = data.summarize_market_sentiment()
    assert summary["total_items"] == 0
    assert summary["overall_mood"] == "no_news"
    assert summary["percent"]["positive"] == 0.0


def test_bullish_and_bearish_moods(monkeypatch):
    bullish = [_article(f"P{i}", f"name {i}", "positive", "operational-updates") for i in range(4)]
    payload = {"data": {"latest_news": bullish}}
    monkeypatch.setattr(data.requests, "get", lambda *a, **k: _Resp(payload))
    assert data.summarize_market_sentiment()["overall_mood"] == "bullish"


def test_sector_sentiment_groups_and_sorts(monkeypatch):
    feed = [
        _article("A", "A LTD", "positive", "earnings-financial-results", sector="Banking"),
        _article("B", "B LTD", "positive", "operational-updates", sector="Banking"),
        _article("C", "C LTD", "negative", "legal-compliance", sector="IT"),
    ]
    monkeypatch.setattr(data.requests, "get", lambda *a, **k: _Resp({"data": {"latest_news": feed}}))
    result = data.summarize_sector_sentiment()
    assert result["total_items"] == 3
    # Banking has the most items -> sorted first
    assert result["sectors"][0]["sector"] == "Banking"
    assert result["sectors"][0]["mood"] == "bullish"
    it = next(s for s in result["sectors"] if s["sector"] == "IT")
    assert it["mood"] == "bearish"


# ---------------- NewsAPI (newsapi.org) ----------------

class _NewsApiResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_newsapi_requires_key(temp_env, monkeypatch):
    # temp_env resets config singleton with an empty NEWS_API_KEY
    with pytest.raises(ValueError, match="NEWS_API_KEY"):
        data.fetch_newsapi_articles(query="reliance")


def test_newsapi_parses_articles(temp_env, monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "test-key-123")
    payload = {
        "status": "ok",
        "articles": [
            {
                "title": "Reliance posts record profit",
                "description": "Q1 beat",
                "url": "https://example.com/a",
                "source": {"name": "ET"},
                "publishedAt": "2026-06-13T10:00:00Z",
            }
        ],
    }
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _NewsApiResp(payload)

    monkeypatch.setattr(data.requests, "get", fake_get)
    out = data.fetch_newsapi_articles(query="reliance", full_text=False)
    assert len(out) == 1
    assert out[0]["source"] == "ET"
    assert out[0]["article_text"] == ""  # full_text=False -> no body fetch
    # the key flows into the request params but never into our returned data
    assert captured["params"]["apiKey"] == "test-key-123"
    assert all("apiKey" not in a for a in out)
    # indian_only (default) restricts to Indian domains
    assert "economictimes.indiatimes.com" in captured["params"]["domains"]


def test_newsapi_default_query_uses_broad_indian_terms(temp_env, monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "test-key-123")
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _NewsApiResp({"status": "ok", "articles": []})

    monkeypatch.setattr(data.requests, "get", fake_get)
    data.fetch_newsapi_articles()  # no query
    assert captured["params"]["q"] == data.INDIAN_MARKET_QUERY
    assert "NSE" in captured["params"]["q"]


def test_newsapi_global_omits_domains(temp_env, monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "test-key-123")
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _NewsApiResp({"status": "ok", "articles": []})

    monkeypatch.setattr(data.requests, "get", fake_get)
    data.fetch_newsapi_articles(query="apple", indian_only=False)
    assert "domains" not in captured["params"]


def test_newsapi_error_status_raises(temp_env, monkeypatch):
    monkeypatch.setenv("NEWS_API_KEY", "test-key-123")
    payload = {"status": "error", "code": "rateLimited", "message": "Too many requests"}
    monkeypatch.setattr(data.requests, "get", lambda *a, **k: _NewsApiResp(payload))
    with pytest.raises(RuntimeError, match="Too many requests"):
        data.fetch_newsapi_articles(query="reliance")
