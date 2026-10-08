import os
import requests


def _secret(name):
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:
        return None


def format_message(df, market_ok, top=10):
    head = "🟢 SPY > 200SMA (market OK)" if market_ok else "🔴 SPY < 200SMA (market weak - be careful)"
    if df is None or df.empty:
        return f"📊 US Swing Scan\n{head}\nAaj koi setup nahi mila."
    lines = [f"📊 US Swing Scan ({df['Date'].iloc[0]})", head, ""]
    for r in df.head(top).itertuples():
        lines.append(
            f"{'🚀' if r.Setup == 'Breakout' else '🔄'} {r.Ticker} [{r.Setup}] Score {r.Score:.0f}\n"
            f"   Buy ~${r.Price} | SL ${r.Stop} ({r.StopPct}%) | TP ${r.Target}\n"
            f"   Qty {r.Shares} | RS {r.RS63}% | Vol x{r.VolX}"
        )
    lines.append("\n⚠️ Sirf educational. Apna risk khud manage karo.")
    return "\n".join(lines)


def send_telegram(text):
    tok, chat = _secret("TELEGRAM_BOT_TOKEN"), _secret("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID set nahi hai"
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          json={"chat_id": chat, "text": text[:4000]}, timeout=20)
        return r.ok, ("Sent ✅" if r.ok else r.text)
    except Exception as e:
        return False, str(e)
