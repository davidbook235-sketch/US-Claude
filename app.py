import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from core import DEFAULT_PARAMS, get_universe, download_prices, scan, backtest, add_signals, regime_series
from notify import format_message, send_telegram

st.set_page_config(page_title="US Swing Scanner", page_icon="📈", layout="centered",
                   initial_sidebar_state="collapsed")


@st.cache_data(ttl=3600, show_spinner=False)
def cached_universe(sp, nq, extra):
    return get_universe(sp, nq, extra)


@st.cache_data(ttl=1800, show_spinner=False)
def cached_prices(tickers, period):
    return download_prices(list(tickers), period=period)


st.title("📈 US Swing Scanner")
st.caption("S&P 500 + Nasdaq-100 | Pullback + Breakout | Backtest included")

# ---------------- settings (inside an expander: mobile friendly)
with st.expander("⚙️ Settings", expanded=False):
    c1, c2 = st.columns(2)
    sp = c1.checkbox("S&P 500", True)
    nq = c2.checkbox("Nasdaq-100", True)
    extra = st.text_input("Extra tickers (space se alag)", "")
    max_n = st.slider("Max stocks to scan (speed ke liye)", 50, 600, 600, 50)
    c1, c2 = st.columns(2)
    capital = c1.number_input("Capital ($)", 1000, 10_000_000, 10000, 1000)
    risk_pct = c2.number_input("Risk per trade (%)", 0.1, 5.0, 1.0, 0.1)
    st.markdown("**Strategy**")
    c1, c2 = st.columns(2)
    use_pb = c1.checkbox("Pullback setup", True)
    use_bo = c2.checkbox("Breakout setup", True)
    use_rg = st.checkbox("Market filter (SPY > 200 SMA)", True)
    c1, c2 = st.columns(2)
    stop_atr = c1.number_input("Stop = x ATR", 1.0, 5.0, DEFAULT_PARAMS["stop_atr"], 0.25)
    rr = c2.number_input("Reward : Risk", 1.0, 5.0, DEFAULT_PARAMS["rr"], 0.25)
    c1, c2 = st.columns(2)
    max_hold = c1.number_input("Max hold (days)", 5, 60, DEFAULT_PARAMS["max_hold"], 1)
    rs_min = c2.number_input("Min RS vs SPY (%)", -10.0, 30.0, 0.0, 1.0)
    min_dv = st.number_input("Min avg $ volume (million)", 1, 500, 20, 5)

params = dict(use_pullback=use_pb, use_breakout=use_bo, use_regime=use_rg, stop_atr=stop_atr, rr=rr,
              max_hold=int(max_hold), rs_min=rs_min / 100, min_dollar_vol=min_dv * 1e6)

tickers, notes = cached_universe(sp, nq, extra)
tickers = tickers[:max_n]
for n in notes:
    st.warning(n)
st.caption(f"Universe: {len(tickers)} stocks")

tab_scan, tab_bt, tab_help = st.tabs(["🔍 Live Scan", "🧪 Backtest", "ℹ️ Guide"])

# ---------------- live scan
with tab_scan:
    if st.button("🚀 Scan Now", use_container_width=True, type="primary"):
        with st.spinner("Data download + scan ho raha hai (1-3 min)..."):
            prices = cached_prices(tuple(tickers + ["SPY"]), "2y")
            spy = prices.get("SPY")
            if spy is None:
                st.error("SPY data nahi aaya. Thodi der baad try karo.")
            else:
                res, ok = scan(prices, spy, params, capital, risk_pct)
                st.session_state.update(scan_res=res, scan_ok=ok, scan_prices=prices, scan_spy=spy)

    res = st.session_state.get("scan_res")
    if res is not None:
        ok = st.session_state["scan_ok"]
        if ok:
            st.success("🟢 Market OK: SPY 200 SMA ke upar")
        else:
            st.error("🔴 Market weak: SPY 200 SMA ke neeche (Settings me Market filter band karke bhi dekh sakte ho)")
        st.caption(f"{len(st.session_state['scan_prices']) - 1} stocks ka data aaya aur scan hua")
        if res.empty:
            st.info("Aaj in rules par koi setup nahi mila. Settings me 'Min RS vs SPY' ghatao ya 'Min avg $ volume' kam karo.")
        else:
            st.subheader(f"{len(res)} suggestions")
            for r in res.head(15).itertuples():
                icon = "🚀" if r.Setup == "Breakout" else "🔄"
                with st.expander(f"{icon} {r.Ticker} · {r.Setup} · Score {r.Score:.0f}"):
                    a, b, c = st.columns(3)
                    a.metric("Buy ~", f"${r.Price}")
                    b.metric("Stop", f"${r.Stop}", f"-{r.StopPct}%", delta_color="inverse")
                    c.metric("Target", f"${r.Target}")
                    st.write(f"**Qty:** {r.Shares} (≈ ${r.PosValue:,.0f}) · RSI {r.RSI:.0f} · "
                             f"RS vs SPY {r.RS63}% · Volume x{r.VolX}")
            with st.expander("📋 Full table"):
                st.dataframe(res, use_container_width=True, hide_index=True)

            sel = st.selectbox("Chart dekho", res["Ticker"].tolist())
            d = add_signals(st.session_state["scan_prices"][sel], st.session_state["scan_spy"]["Close"],
                            regime_series(st.session_state["scan_spy"]), params).tail(130)
            fig = go.Figure(go.Candlestick(x=d.index, open=d["Open"], high=d["High"], low=d["Low"],
                                           close=d["Close"], name=sel))
            for col, nm in (("ema20", "EMA20"), ("sma50", "SMA50"), ("sma200", "SMA200")):
                fig.add_trace(go.Scatter(x=d.index, y=d[col], name=nm, line=dict(width=1)))
            row = res[res["Ticker"] == sel].iloc[0]
            fig.add_hline(y=row["Stop"], line_dash="dot", line_color="red")
            fig.add_hline(y=row["Target"], line_dash="dot", line_color="green")
            fig.update_layout(height=420, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0),
                              legend=dict(orientation="h"))
            st.plotly_chart(fig, use_container_width=True)

        if st.button("📨 Telegram par bhejo", use_container_width=True):
            okk, msg = send_telegram(format_message(res, ok))
            if okk:
                st.success(msg)
            else:
                st.error(msg)

# ---------------- backtest
with tab_bt:
    st.write("Same rules ko purane data par chala ke dekho ki strategy kitni chali.")
    c1, c2 = st.columns(2)
    hist = c1.selectbox("History", ["2y", "5y", "10y"], index=1)
    max_pos = c2.number_input("Max open positions", 1, 30, 10, 1)
    bt_n = st.slider("Backtest stocks (zyada = slow)", 50, 600, 150, 50)
    if st.button("▶️ Run Backtest", use_container_width=True, type="primary"):
        with st.spinner("Historical data download ho raha hai..."):
            prices = cached_prices(tuple(tickers[:bt_n] + ["SPY"]), hist)
        spy = prices.get("SPY")
        if spy is None:
            st.error("SPY data nahi aaya.")
        else:
            bar = st.progress(0.0, text="Backtesting...")
            out = backtest(prices, spy, params, capital, risk_pct, int(max_pos), progress=lambda x: bar.progress(min(x, 1.0)))
            bar.empty()
            st.session_state["bt"] = out
            if out is None:
                st.warning("Koi trade nahi bana. Filters dheele karo.")

    out = st.session_state.get("bt")
    if out:
        s = out["stats"]
        st.caption(f"Period: {s['Period']}")
        a, b = st.columns(2)
        a.metric("Win rate", f"{s['WinRate']}%")
        b.metric("Trades", s["Trades"])
        a.metric("Avg R / trade", s["AvgR"])
        b.metric("Profit factor", s["ProfitFactor"])
        a.metric("Strategy return", f"{s['TotalReturnPct']}%")
        b.metric("SPY buy&hold", f"{s['SPY_BuyHoldPct']}%")
        a.metric("CAGR", f"{s['CAGRpct']}%")
        b.metric("Max drawdown", f"{s['MaxDrawdownPct']}%")
        st.caption(f"Avg win {s['AvgWinR']}R · avg loss {s['AvgLossR']}R · avg hold {s['AvgHoldDays']} days")

        f1 = go.Figure(go.Scatter(x=out["equity"].index, y=out["equity"].values, fill="tozeroy"))
        f1.update_layout(title="Equity curve", height=300, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(f1, use_container_width=True)
        f2 = go.Figure(go.Scatter(x=out["drawdown"].index, y=out["drawdown"].values, fill="tozeroy", line=dict(color="red")))
        f2.update_layout(title="Drawdown %", height=240, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(f2, use_container_width=True)
        st.write("**Setup-wise**")
        st.dataframe(out["by_setup"], use_container_width=True, hide_index=True)
        with st.expander("Saare trades"):
            st.dataframe(out["trades"], use_container_width=True, hide_index=True)
        st.download_button("⬇️ Trades CSV", out["trades"].to_csv(index=False), "trades.csv", use_container_width=True)
        st.caption("Note: Aaj ke index members use hote hain (survivorship bias), isliye result thoda zyada achha dikh sakta hai. "
                   "Risk har trade par fixed % hai (compounding nahi).")

# ---------------- guide
with tab_help:
    st.markdown("""
**Setups**
- 🔄 **Pullback**: uptrend (Price > SMA50 > SMA200), price EMA20 tak wapas aaya, RSI 35-52, bullish candle.
- 🚀 **Breakout**: 55-din ke high ke upar close + volume 1.5x+ + over-extended nahi.
- Dono me stock SPY se strong hona chahiye (RS) aur liquid ($20M+ daily volume).

**Trade plan**: Stop = Entry − 2×ATR, Target = 2R. Position size = Risk% ÷ stop distance.

**Score (0-100)**: relative strength + trend strength + volume + setup quality. Upar wale pehle dekho.

**Rules**: Market filter ON rakho. Ek time par 5-10 se zyada positions nahi. Earnings se pehle position check karo.

⚠️ Yeh educational tool hai, financial advice nahi. Pehle paper trade karo.
""")
