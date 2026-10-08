"""Headless scan for GitHub Actions -> Telegram."""
from core import get_universe, download_prices, scan
from notify import format_message, send_telegram


def main():
    tickers, notes = get_universe(True, True)
    print(f"Universe: {len(tickers)} tickers", notes)
    prices = download_prices(tickers + ["SPY"], period="2y")
    spy = prices.pop("SPY", None)
    if spy is None:
        print("SPY data nahi mila"); return
    df, ok = scan(prices, spy)
    msg = format_message(df, ok)
    print(msg)
    print(send_telegram(msg))


if __name__ == "__main__":
    main()
