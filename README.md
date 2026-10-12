# NBS AI Trading — starter dashboard

Responsive web dashboard for Android/desktop. Uses CoinGecko public BTC/USD data and a basic paper-trading demo only.

## Deploy online (Render)
1. Upload this folder to a new GitHub repository.
2. In Render, create a new Web Service from that repository.
3. Render can use `render.yaml`, or set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
4. Open the generated HTTPS URL on your phone.
5. Optional environment variables:
   - `NBS_START_BALANCE=1000`
   - `NBS_POLL_SECONDS=60`

## Local run
`pip install -r requirements.txt`
`python app.py`
Open `http://127.0.0.1:5000`.

## Important limitations
- This is a prototype, not a validated AI trading system.
- Entry logic is a deliberately simple momentum demo, not EMA/RSI multi-timeframe analysis yet.
- The state file may not persist on free ephemeral hosting; add persistent storage before relying on long-running statistics.
- No exchange orders, API keys, leverage, or real-money trading are implemented.
- Public CoinGecko endpoints can rate-limit; dashboard will show an error if data cannot be fetched.
