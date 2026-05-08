from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from strategy import momentum_fail


class RiskManager:
    def __init__(self, settings, exchange, storage):
        self.settings = settings
        self.exchange = exchange
        self.storage = storage
        self.cooldowns: dict[str, datetime] = {}
        self.open_trades: dict[str, dict] = {}
        self.consecutive_losses = 0
        self.pause_until: datetime | None = None

    async def can_open_trade(self, symbol: str) -> tuple[bool, str]:
        if self.pause_until and datetime.now(timezone.utc) < self.pause_until:
            return False, "risk pause active"
        daily_pnl = await self.storage.calculate_daily_pnl()
        if daily_pnl >= self.settings.daily_target_usdt:
            return False, "daily target reached"
        if daily_pnl <= -abs(self.settings.daily_max_loss_usdt):
            return False, "daily max loss hit"
        if self.consecutive_losses >= self.settings.max_consecutive_losses:
            return False, "max consecutive losses reached"
        if len(self.open_trades) >= self.settings.max_open_trades:
            return False, "max open trades reached"
        if symbol in self.open_trades:
            return False, "duplicate symbol trade"
        cd = self.cooldowns.get(symbol)
        if cd and datetime.now(timezone.utc) < cd:
            return False, "symbol cooldown"
        return True, "ok"

    async def register_open_trade(self, trade: dict) -> None:
        self.open_trades[trade["symbol"]] = trade

    async def monitor(self, get_candles_fn):
        while True:
            await self._btc_protection_check(get_candles_fn)
            for symbol in list(self.open_trades.keys()):
                await self._monitor_one(symbol, get_candles_fn)
            await asyncio.sleep(self.settings.monitor_interval_seconds)

    async def _monitor_one(self, symbol: str, get_candles_fn):
        trade = self.open_trades.get(symbol)
        if not trade:
            return
        price = await self.exchange.fetch_mark_price(symbol)
        side = trade["side"]
        pnl = (price - trade["entry_price"]) * trade["quantity"] if side == "long" else (trade["entry_price"] - price) * trade["quantity"]
        fees = abs(trade["entry_price"] * trade["quantity"] * 0.0004) + abs(price * trade["quantity"] * 0.0004)
        net_pnl = pnl - fees
        elapsed = (datetime.now(timezone.utc) - trade["opened_dt"]).total_seconds()

        exit_reason = None
        if net_pnl >= self.settings.target_profit_usdt:
            exit_reason = "target_profit"
        elif net_pnl <= -abs(self.settings.emergency_sl_usdt):
            exit_reason = "emergency_sl"
        elif elapsed >= self.settings.max_hold_seconds:
            exit_reason = "max_hold_time"
        else:
            c1 = get_candles_fn(symbol, "1m")
            if c1 and momentum_fail(side, c1):
                exit_reason = "momentum_fail"

        if exit_reason:
            await self.exchange.close_position(symbol, side, trade["quantity"])
            update = {
                "exit_price": price,
                "gross_pnl": pnl,
                "fees": fees,
                "net_pnl": net_pnl,
                "result": "WIN" if net_pnl > 0 else "LOSS",
                "closed_at": datetime.now(timezone.utc).isoformat(),
                "exit_reason": exit_reason,
            }
            await self.storage.update_trade_closed(trade["trade_id"], update)
            self.consecutive_losses = 0 if net_pnl > 0 else self.consecutive_losses + 1
            self.cooldowns[symbol] = datetime.now(timezone.utc) + timedelta(seconds=self.settings.symbol_cooldown_seconds)
            self.open_trades.pop(symbol, None)

    async def _btc_protection_check(self, get_candles_fn):
        c5 = get_candles_fn("BTC/USDT:USDT", "5m")
        if not c5 or len(c5) < 2:
            return
        prev = c5[-2][4]
        last = c5[-1][4]
        move = abs(last - prev) / max(prev, 1e-9)
        if move >= 0.01:
            self.pause_until = datetime.now(timezone.utc) + timedelta(minutes=self.settings.btc_pause_minutes)
            for sym in list(self.open_trades.keys()):
                t = self.open_trades[sym]
                await self.exchange.close_position(sym, t["side"], t["quantity"])
            await self.storage.add_log("WARNING", "BTC volatility protection triggered; bot paused.")
            self.open_trades.clear()
