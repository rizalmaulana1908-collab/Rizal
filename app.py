import os, json, time, threading
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template
import requests

app = Flask(__name__)
DATA_FILE = os.environ.get("NBS_DATA_FILE", "nbs_state.json")
START_BALANCE = float(os.environ.get("NBS_START_BALANCE", "1000"))
POLL_SECONDS = int(os.environ.get("NBS_POLL_SECONDS", "60"))
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"

lock = threading.Lock()
state = {
    "balance": START_BALANCE, "start_balance": START_BALANCE, "realized_pnl": 0.0,
    "trades": [], "open_trade": None, "last_price": None, "previous_price": None,
    "last_signal": "WAIT", "last_update": None, "price_error": None
}

def load_state():
    global state
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        state.update(saved)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

def save_state():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass

def get_btc_price():
    r = requests.get(COINGECKO_URL, params={"ids":"bitcoin", "vs_currencies":"usd", "include_24hr_change":"true"}, timeout=12)
    r.raise_for_status()
    data = r.json()["bitcoin"]
    return float(data["usd"]), float(data.get("usd_24h_change", 0.0))

def decide_signal(price, previous, change24):
    # Demo rules only: simple momentum proxy, not a predictive AI model.
    if previous is None:
        return "WAIT"
    short_change = (price / previous - 1) * 100 if previous else 0
    if short_change > 0.08 and change24 > 0:
        return "BUY"
    if short_change < -0.08 and change24 < 0:
        return "SELL"
    return "WAIT"

def close_trade(price, reason):
    trade = state["open_trade"]
    if not trade:
        return
    direction = trade["direction"]
    entry = trade["entry"]
    qty = trade["qty"]
    pnl = (price - entry) * qty if direction == "LONG" else (entry - price) * qty
    state["balance"] += pnl
    state["realized_pnl"] += pnl
    state["trades"].insert(0, {
        "time": datetime.now(timezone.utc).isoformat(),
        "direction": direction, "entry": entry, "exit": price, "qty": qty,
        "pnl": round(pnl, 4), "result": "WIN" if pnl > 0 else "LOSS", "reason": reason
    })
    state["trades"] = state["trades"][:100]
    state["open_trade"] = None

def update_loop():
    while True:
        try:
            price, change24 = get_btc_price()
            with lock:
                previous = state["last_price"]
                state["previous_price"] = previous
                signal = decide_signal(price, previous, change24)
                state["last_price"] = price
                state["last_signal"] = signal
                state["last_update"] = datetime.now(timezone.utc).isoformat()
                state["price_error"] = None

                trade = state["open_trade"]
                if trade:
                    if trade["direction"] == "LONG":
                        if price <= trade["sl"]:
                            close_trade(price, "STOP LOSS")
                        elif price >= trade["tp"]:
                            close_trade(price, "TAKE PROFIT")
                    else:
                        if price >= trade["sl"]:
                            close_trade(price, "STOP LOSS")
                        elif price <= trade["tp"]:
                            close_trade(price, "TAKE PROFIT")

                # Paper-only entries. Use a small virtual allocation and 1% SL / 2% TP.
                if not state["open_trade"] and signal in ("BUY", "SELL") and state["balance"] > 0:
                    direction = "LONG" if signal == "BUY" else "SHORT"
                    allocation = min(state["balance"] * 0.10, state["balance"])
                    qty = allocation / price
                    sl = price * (0.99 if direction == "LONG" else 1.01)
                    tp = price * (1.02 if direction == "LONG" else 0.98)
                    state["open_trade"] = {
                        "direction": direction, "entry": price, "qty": qty,
                        "sl": sl, "tp": tp, "opened_at": datetime.now(timezone.utc).isoformat()
                    }
                save_state()
        except Exception as e:
            with lock:
                state["price_error"] = str(e)[:240]
                state["last_update"] = datetime.now(timezone.utc).isoformat()
        time.sleep(max(15, POLL_SECONDS))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/status")
def api_status():
    with lock:
        trades = state["trades"]
        wins = sum(1 for t in trades if t.get("result") == "WIN")
        losses = sum(1 for t in trades if t.get("result") == "LOSS")
        closed = wins + losses
        price = state["last_price"]
        open_trade = state["open_trade"]
        unrealized = 0.0
        if price is not None and open_trade:
            if open_trade["direction"] == "LONG":
                unrealized = (price - open_trade["entry"]) * open_trade["qty"]
            else:
                unrealized = (open_trade["entry"] - price) * open_trade["qty"]
        return jsonify({
            "balance": round(state["balance"], 2),
            "start_balance": round(state["start_balance"], 2),
            "realized_pnl": round(state["realized_pnl"], 2),
            "total_pnl": round(state["realized_pnl"] + unrealized, 2),
            "unrealized_pnl": round(unrealized, 2),
            "price": price, "signal": state["last_signal"],
            "last_update": state["last_update"], "price_error": state["price_error"],
            "open_trade": open_trade, "trades": trades[:12],
            "wins": wins, "losses": losses, "closed": closed,
            "win_rate": round(wins / closed * 100, 1) if closed else 0
        })

@app.route("/api/reset", methods=["POST"])
def api_reset():
    with lock:
        state.update({
            "balance": START_BALANCE, "start_balance": START_BALANCE, "realized_pnl": 0.0,
            "trades": [], "open_trade": None, "last_signal": "WAIT"
        })
        save_state()
    return jsonify({"ok": True, "message": "Paper trading reset"})

# Start the updater when imported by Gunicorn or run directly.
load_state()
_updater_started = False
_updater_lock = threading.Lock()

def start_updater_once():
    global _updater_started
    with _updater_lock:
        if not _updater_started:
            threading.Thread(target=update_loop, daemon=True, name="nbs-price-updater").start()
            _updater_started = True

start_updater_once()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
