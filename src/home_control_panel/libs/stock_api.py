import logging

import requests

from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()


def api_stock_quotes():
    """Fetch current stock quotes from Finnhub for all configured symbols.

    Returns (error, data) where data is a list of dicts with keys:
    symbol, current, change, percent_change.
    """
    key = config.get("finnhubKey")
    if not key:
        return Exception("finnhubKey not configured"), None

    symbols = config.get("stocks", {}).get("symbols", [])
    if not symbols:
        return None, []

    results = []
    for symbol in symbols:
        try:
            result = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": symbol, "token": key},
                timeout=(3.05, 10),
            )
            if result.status_code != 200:
                logger.warning(
                    "Finnhub API error for %s: HTTP %s", symbol, result.status_code
                )
                continue
            data = result.json()
            current = data.get("c")
            previous = data.get("pc")
            if current is None or previous is None:
                continue
            change = current - previous
            percent = (change / previous) * 100
            results.append(
                {
                    "symbol": symbol,
                    "current": current,
                    "change": change,
                    "percent_change": percent,
                }
            )
        except Exception:
            logger.warning("Finnhub API failed for %s", symbol, exc_info=True)
            continue

    return None, results
