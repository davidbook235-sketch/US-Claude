# US Swing Scanner (S&P 500 + Nasdaq-100)

Files: app.py, core.py, notify.py, run_scan.py, requirements.txt, extra_tickers.txt, .github/workflows/scan.yml

## Mobile setup (Hinglish)
1. GitHub app/browser me naya repo banao -> saari files upload karo (ye zip ke andar sab ready hai).
2. Agar `.github/workflows/scan.yml` upload na ho paaye: GitHub me "Add file > Create new file" -> naam me `.github/workflows/scan.yml` likho -> `scan.yml.txt` ka content paste karo.
3. share.streamlit.io -> New app -> repo select -> Main file: `app.py` -> Deploy.
4. Telegram (optional): Streamlit app Settings > Secrets me:
   TELEGRAM_BOT_TOKEN = "xxxx"
   TELEGRAM_CHAT_ID = "xxxx"
   Auto daily alert ke liye GitHub repo > Settings > Secrets and variables > Actions me wahi 2 secrets daalo.
5. Auto scan roz US close ke baad chalega (Actions tab se manual bhi run kar sakte ho).

Nasdaq ka official "250" index nahi hota, isliye Nasdaq-100 liya hai. Extra stocks `extra_tickers.txt` ya app ke Settings me daal sakte ho.
