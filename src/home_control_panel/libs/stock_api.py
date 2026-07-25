import logging

import finnhub

from home_control_panel.libs.utils import load_config

logger = logging.getLogger(__name__)
config = load_config()


def api_stock_quotes(state):
    """Fetch current stock quotes from Finnhub for all configured symbols.

    Returns (error, data) where data is a list of dicts with keys:
    symbol, name, current, change, percent_change.
    """
    key = config.get("finnhubKey")
    if not key:
        return Exception("finnhubKey not configured"), None

    symbols = config.get("stocks", {}).get("symbols", [])
    if not symbols:
        return None, []

    names = state.setdefault("stock_names", {})

    client = finnhub.Client(api_key=key)
    results = []
    for symbol in symbols:
        try:
            data = client.quote(symbol)
            current = data.c
            previous = data.pc
            if current is None or previous is None or previous == 0:
                continue
            change = current - previous
            percent = (change / previous) * 100

            if symbol not in names:
                try:
                    profile = client.company_profile2(symbol=symbol)
                    if profile.name:
                        names[symbol] = profile.name
                except finnhub.FinnhubAPIException:
                    logger.warning("Failed to fetch name for %s", symbol)

            results.append(
                {
                    "symbol": symbol,
                    "name": names.get(symbol, symbol),
                    "current": current,
                    "change": change,
                    "percent_change": percent,
                }
            )
        except finnhub.FinnhubAPIException:
            logger.warning("Finnhub API failed for %s", symbol, exc_info=True)
            continue

    return None, results
