"""
US Swing Scanner - core engine
Universe : S&P 500 + Nasdaq-100 (+ your extra tickers)
Setups   : 1) Trend Pullback   2) Volume Breakout
Same signal code is used for LIVE scan and BACKTEST (no mismatch).
"""
import io
import os
import numpy as np
import pandas as pd
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SwingScanner/1.0)"}

DEFAULT_PARAMS = dict(
    min_price=10.0,            # penny stocks out
    min_dollar_vol=20e6,       # avg 20d $ volume filter (liquidity)
    use_pullback=True,
    use_breakout=True,
    breakout_lookback=55,      # Donchian breakout days
    vol_mult=1.5,              # breakout volume vs 20d avg
    rs_min=0.0,                # stock 63d return must beat SPY by this (0.0 = 0%)
    use_regime=True,           # only buy when SPY > 200 SMA
    stop_atr=2.0,              # stop = entry - stop_atr * ATR
    rr=2.0,                    # target = entry + rr * risk
    max_hold=20,               # max days in trade (backtest)
    cost_pct=0.10,             # round-trip slippage+fees in % (backtest)
)

# ---------------------------------------------------------------- universe
FALLBACK = (
    "AAPL MSFT NVDA AMZN GOOGL META AVGO TSLA COST NFLX AMD ADBE PEP CSCO TMUS "
    "INTU QCOM TXN AMGN AMAT ISRG BKNG HON VRTX PANW ADP GILD MU LRCX SBUX ADI "
    "MELI KLAC SNPS CDNS CRWD MRVL ORLY ABNB FTNT ASML REGN MDLZ PYPL CTAS "
    "JPM V MA UNH XOM LLY WMT PG HD JNJ ABBV BAC KO MRK CVX CRM ORCL ACN MCD "
    "LIN ABT DIS WFC GE CAT IBM NOW UBER GS MS RTX AXP BLK SPGI LOW DE PLD "
    "UNP PFE MMM NKE T VZ COP BA TJX SCHW MDT ELV LMT C"
).split()


def _clean(sym):
    return str(sym).strip().upper().replace(".", "-")


def _wiki_tables(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return pd.read_html(io.StringIO(r.text))


def get_sp500():
    t = _wiki_tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    return [_clean(x) for x in t[0]["Symbol"].tolist()]


NASDAQ100_BACKUP = (
    "AAPL MSFT NVDA AMZN GOOGL GOOG META AVGO TSLA COST NFLX AMD ADBE PEP CSCO TMUS INTU QCOM TXN AMGN "
    "AMAT ISRG BKNG HON VRTX PANW ADP GILD MU LRCX SBUX ADI MELI KLAC SNPS CDNS CRWD MRVL ORLY ABNB FTNT "
    "ASML REGN MDLZ PYPL CTAS CEG DASH WDAY ADSK PDD CHTR MAR CPRT PCAR NXPI MNST ROP AEP FANG PAYX AZN "
    "KDP ODFL FAST ROST KHC EA VRSK CTSH GEHC DDOG XEL EXC LULU CCEP IDXX TTWO BKR ON CSGP DXCM BIIB TEAM "
    "ZS GFS MDB CDW WBD ARM APP PLTR TRI AXON SHOP LIN MSTR TTD CSX CMCSA INTC ADSK DLTR CTAS"
).split()


def get_nasdaq100():
    for t in _wiki_tables("https://en.wikipedia.org/wiki/Nasdaq-100"):
        t = t.copy()
        if isinstance(t.columns, pd.MultiIndex):
            t.columns = [" ".join(map(str, c)).strip() for c in t.columns]
        for col in t.columns:
            if str(col).strip().lower() in ("ticker", "symbol") and len(t) >= 90:
                syms = [_clean(x) for x in t[col].tolist() if isinstance(x, str)]
                if len(syms) >= 90:
                    return syms
    raise ValueError("Nasdaq-100 table not found")


def get_extra():
    syms = []
    if os.path.exists("extra_tickers.txt"):
        with open("extra_tickers.txt") as f:
            for line in f:
                line = line.split("#")[0]
                syms += [_clean(x) for x in line.replace(",", " ").split() if x.strip()]
    return syms


def get_universe(include_sp500=True, include_nasdaq=True, extra=""):
    out, notes = [], []
    if include_sp500:
        try:
            out += get_sp500()
        except Exception as e:
            notes.append("S&P500 live list nahi mili; chhoti backup list use hui")
            out += FALLBACK
    if include_nasdaq:
        try:
            out += get_nasdaq100()
        except Exception as e:
            notes.append("Nasdaq-100 live list nahi mili; built-in Nasdaq-100 list use hui")
            out += NASDAQ100_BACKUP
    out += get_extra()
    out += [_clean(x) for x in extra.replace(",", " ").split() if x.strip()]
    seen, uniq = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq, notes


# ---------------------------------------------------------------- data
def download_prices(tickers, period="2y", chunk=80):
    import yfinance as yf
    out = {}
    cols = ["Open", "High", "Low", "Close", "Volume"]
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        try:
            raw = yf.download(part, period=period, interval="1d", group_by="ticker",
                              auto_adjust=True, threads=True, progress=False)
        except Exception:
            continue
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            lvl0 = set(raw.columns.get_level_values(0))
            for t in part:
                if t in lvl0:
                    d = raw[t].dropna(subset=["Close"])
                    if len(d) > 0 and all(c in d.columns for c in cols):
                        out[t] = d[cols].copy()
        else:
            d = raw.dropna(subset=["Close"])
            if len(d) > 0:
                out[part[0]] = d[cols].copy()
    return out


# ---------------------------------------------------------------- indicators
def _rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _atr(df, n=14):
    pc = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def regime_series(spy):
    """True when SPY close > SPY 200 SMA."""
    c = spy["Close"]
    return (c > c.rolling(200).mean())


def add_signals(df, spy_close=None, regime=None, p=None):
    p = {**DEFAULT_PARAMS, **(p or {})}
    d = df.copy()
    c = d["Close"]
    d["ema20"] = c.ewm(span=20, adjust=False).mean()
    d["sma50"] = c.rolling(50).mean()
    d["sma200"] = c.rolling(200).mean()
    d["rsi"] = _rsi(c)
    d["atr"] = _atr(d)
    d["volavg"] = d["Volume"].rolling(20).mean()
    d["volx"] = d["Volume"] / d["volavg"]
    d["dollarvol"] = (c * d["Volume"]).rolling(20).mean()
    d["hh"] = d["High"].rolling(p["breakout_lookback"]).max().shift(1)
    d["ret63"] = c.pct_change(63)
    if spy_close is not None:
        sc = spy_close.reindex(d.index).ffill()
        d["rs63"] = d["ret63"] - sc.pct_change(63)
    else:
        d["rs63"] = d["ret63"]

    trend = (c > d["sma50"]) & (d["sma50"] > d["sma200"]) & (d["sma200"] > d["sma200"].shift(20))
    liquid = (c >= p["min_price"]) & (d["dollarvol"] >= p["min_dollar_vol"])
    strong = d["rs63"] >= p["rs_min"]

    pullback = (trend & liquid & strong
                & (c <= d["ema20"] * 1.01) & (c >= d["sma50"])
                & d["rsi"].between(35, 52)
                & (c > d["Open"]))                       # bullish reversal candle
    breakout = (trend & liquid & strong
                & (c > d["hh"]) & (d["volx"] >= p["vol_mult"])
                & (d["rsi"] < 80)
                & ((c - d["ema20"]) / d["atr"] < 3.5))   # not over-extended

    if not p["use_pullback"]:
        pullback = pullback & False
    if not p["use_breakout"]:
        breakout = breakout & False

    sig = pullback | breakout
    if p["use_regime"] and regime is not None:
        rg = regime.reindex(d.index).ffill().fillna(False).astype(bool)
        sig = sig & rg
        pullback, breakout = pullback & rg, breakout & rg

    d["pullback"], d["breakout"], d["signal"] = pullback, breakout, sig
    d["setup"] = np.where(d["breakout"], "Breakout", np.where(d["pullback"], "Pullback", ""))

    rs_part = np.clip(d["rs63"] / 0.25, 0, 1) * 35
    tr_part = np.clip((c / d["sma200"] - 1) / 0.30, 0, 1) * 20
    vol_part = np.clip(d["volx"] / 2.5, 0, 1) * 20
    set_part = np.where(d["breakout"], 25, np.where(d["pullback"], 20, 0))
    d["score"] = (rs_part + tr_part + vol_part + set_part).round(1)
    return d


# ---------------------------------------------------------------- live scan
def scan(prices, spy, params=None, capital=10000.0, risk_pct=1.0, max_pos_pct=25.0):
    p = {**DEFAULT_PARAMS, **(params or {})}
    spy_close = spy["Close"]
    regime = regime_series(spy)
    market_ok = bool(regime.iloc[-1]) if len(regime) else False
    last_spy_date = spy.index[-1]
    rows = []
    for t, df in prices.items():
        if len(df) < 210 or t == "SPY":
            continue
        try:
            d = add_signals(df, spy_close, regime, p)
        except Exception:
            continue
        r = d.iloc[-1]
        if not bool(r["signal"]) or (last_spy_date - d.index[-1]).days > 4:
            continue
        entry = float(r["Close"])
        risk = p["stop_atr"] * float(r["atr"])
        stop, target = entry - risk, entry + p["rr"] * risk
        shares = int(min(capital * risk_pct / 100 / risk, capital * max_pos_pct / 100 / entry)) if risk > 0 else 0
        rows.append(dict(
            Ticker=t, Setup=r["setup"], Score=float(r["score"]), Price=round(entry, 2),
            Stop=round(stop, 2), Target=round(target, 2),
            StopPct=round(risk / entry * 100, 1), RSI=round(float(r["rsi"]), 0),
            RS63=round(float(r["rs63"]) * 100, 1), VolX=round(float(r["volx"]), 2),
            Shares=shares, PosValue=round(shares * entry, 0), Date=d.index[-1].strftime("%Y-%m-%d"),
        ))
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("Score", ascending=False).reset_index(drop=True)
    return out, market_ok


# ---------------------------------------------------------------- backtest
def _bt_one(d, p):
    o, h, l, c = (d[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    atr = d["atr"].to_numpy(float)
    sig = d["signal"].to_numpy(bool)
    sc = d["score"].to_numpy(float)
    setup = d["setup"].to_numpy(object)
    idx = d.index
    n = len(d)
    trades = []
    i = 0
    while i < n - 1:
        if not sig[i] or np.isnan(atr[i]):
            i += 1
            continue
        e = i + 1
        entry = o[e]
        risk = p["stop_atr"] * atr[i]
        if not (risk > 0) or np.isnan(entry):
            i += 1
            continue
        stop, target = entry - risk, entry + p["rr"] * risk
        exit_px, exit_i, reason = c[min(e + p["max_hold"], n - 1)], min(e + p["max_hold"], n - 1), "time"
        for j in range(e, min(e + p["max_hold"], n - 1) + 1):
            if o[j] <= stop:
                exit_px, exit_i, reason = o[j], j, "stop"; break
            if l[j] <= stop:
                exit_px, exit_i, reason = stop, j, "stop"; break
            if h[j] >= target:
                exit_px, exit_i, reason = max(target, o[j]) if o[j] >= target else target, j, "target"; break
        r_mult = (exit_px - entry) / risk - (p["cost_pct"] / 100 * entry) / risk
        trades.append(dict(entry_date=idx[e], exit_date=idx[exit_i], setup=setup[i],
                           score=sc[i], R=r_mult, reason=reason, days=exit_i - e))
        i = exit_i + 1
    return trades


def backtest(prices, spy, params=None, capital=10000.0, risk_pct=1.0, max_positions=10, progress=None):
    p = {**DEFAULT_PARAMS, **(params or {})}
    spy_close = spy["Close"]
    regime = regime_series(spy)
    all_tr = []
    items = [(t, df) for t, df in prices.items() if t != "SPY" and len(df) >= 260]
    for k, (t, df) in enumerate(items):
        try:
            d = add_signals(df, spy_close, regime, p)
            for tr in _bt_one(d, p):
                tr["ticker"] = t
                all_tr.append(tr)
        except Exception:
            pass
        if progress and k % 25 == 0:
            progress((k + 1) / max(len(items), 1))
    if not all_tr:
        return None
    tr = pd.DataFrame(all_tr).sort_values(["entry_date", "score"], ascending=[True, False]).reset_index(drop=True)

    # portfolio rule: max N open positions at a time, best score first
    open_exits, keep = [], []
    for row in tr.itertuples():
        open_exits = [x for x in open_exits if x >= row.entry_date]
        if len(open_exits) < max_positions:
            open_exits.append(row.exit_date)
            keep.append(True)
        else:
            keep.append(False)
    tr = tr[keep].reset_index(drop=True)
    if tr.empty:
        return None

    tr["pnl"] = capital * risk_pct / 100 * tr["R"]            # fixed risk per trade (not compounded)
    by_exit = tr.sort_values("exit_date")
    eq = capital + by_exit["pnl"].cumsum()
    eq.index = by_exit["exit_date"].values
    eq = eq.groupby(level=0).last()
    peak = eq.cummax()
    dd = (eq / peak - 1) * 100

    wins, losses = tr[tr["R"] > 0], tr[tr["R"] <= 0]
    pf = wins["R"].sum() / abs(losses["R"].sum()) if len(losses) and losses["R"].sum() != 0 else np.inf
    first, last = tr["entry_date"].min(), tr["exit_date"].max()
    years = max((last - first).days / 365.25, 0.25)
    total_ret = (eq.iloc[-1] / capital - 1) * 100
    spy_slice = spy_close[(spy_close.index >= first) & (spy_close.index <= last)]
    spy_ret = (spy_slice.iloc[-1] / spy_slice.iloc[0] - 1) * 100 if len(spy_slice) > 1 else np.nan

    stats = dict(
        Trades=len(tr), WinRate=round(len(wins) / len(tr) * 100, 1),
        AvgR=round(tr["R"].mean(), 3), ProfitFactor=round(pf, 2) if np.isfinite(pf) else None,
        AvgWinR=round(wins["R"].mean(), 2) if len(wins) else 0, AvgLossR=round(losses["R"].mean(), 2) if len(losses) else 0,
        TotalReturnPct=round(total_ret, 1), CAGRpct=round(((eq.iloc[-1] / capital) ** (1 / years) - 1) * 100, 1),
        MaxDrawdownPct=round(dd.min(), 1), AvgHoldDays=round(tr["days"].mean(), 1),
        SPY_BuyHoldPct=round(spy_ret, 1), Period=f"{first:%Y-%m-%d} to {last:%Y-%m-%d}",
    )
    by_setup = tr.groupby("setup").agg(Trades=("R", "size"), WinRate=("R", lambda x: round((x > 0).mean() * 100, 1)),
                                       AvgR=("R", lambda x: round(x.mean(), 3))).reset_index()
    return dict(stats=stats, trades=tr, equity=eq, drawdown=dd, by_setup=by_setup)
