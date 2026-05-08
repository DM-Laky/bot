# Binance Futures Pressure Scalper Bot

## What this bot does
Async Binance USDT-M futures pressure scalper with:
- TESTNET/LIVE switch by `.env`
- Two-stage scanner (tickers -> shortlisted OHLCV)
- Score-based entries (15m + 5m + 1m)
- Fast TP/SL/timeout/momentum-fail exits
- Risk controls (daily limits, cooldowns, max losses, max open trades)
- FastAPI dashboard with controls and logs

## Risk warning
This is leveraged derivatives trading software. Losses can exceed expectations. Start on **TESTNET** only.

## Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r pressure_scalper_bot/requirements.txt
```

## Configure
```bash
cp pressure_scalper_bot/.env.example .env
# Fill API key/secret
```

Default is safe:
- `BINANCE_MODE=testnet`

## Run in testnet
```bash
uvicorn pressure_scalper_bot.app:app --host 0.0.0.0 --port 8000 --reload
```
Open: `http://localhost:8000`

## Switch to live
1. Set `BINANCE_MODE=live` in `.env`
2. Use live futures API keys
3. Restart app

Dashboard shows a red **LIVE MODE** warning.

## Settings
Main knobs:
- Position sizing: `MARGIN_PER_TRADE`, `LEVERAGE`
- Exit: `TARGET_PROFIT_USDT`, `EMERGENCY_SL_USDT`, `MAX_HOLD_SECONDS`
- Risk stop: `DAILY_TARGET_USDT`, `DAILY_MAX_LOSS_USDT`, `MAX_CONSECUTIVE_LOSSES`
- Frequency: `MONITOR_INTERVAL_SECONDS`
- Scanner strictness: `MIN_SCORE_TO_TRADE`, `CANDLE_LIMIT`

## TP/SL behavior
- Entry with market order
- Bot monitors net PnL frequently
- Close via reduceOnly market order when:
  - net pnl >= target
  - net pnl <= emergency SL
  - hold time exceeded
  - momentum fail

## Daily target/loss behavior
- No new trades after daily target reached
- No new trades after daily max loss hit
- Also blocked when max consecutive losses hit

## Troubleshooting
- `ccxtpro` install error: ensure licensed package access and correct pip index/account.
- API auth errors: verify futures permission and IP whitelist.
- No trades: lower `MIN_SCORE_TO_TRADE` or relax volume/spread thresholds.
- Frequent disconnects: check internet stability; bot retries transient failures.
