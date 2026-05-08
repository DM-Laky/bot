from __future__ import annotations

import asyncio
from typing import Any

import ccxt.pro as ccxtpro


class ExchangeClient:
    def __init__(self, settings, storage) -> None:
        self.settings = settings
        self.storage = storage
        self.exchange = None
        self.markets = {}

    async def initialize(self) -> None:
        opts = {
            "apiKey": self.settings.binance_api_key,
            "secret": self.settings.binance_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        }
        self.exchange = ccxtpro.binance(opts)
        if self.settings.binance_mode == "testnet":
            self.exchange.set_sandbox_mode(True)
        await self.exchange.load_markets()
        self.markets = self.exchange.markets
        await self.storage.add_log("INFO", f"Exchange initialized in {self.settings.binance_mode}")

    def usdt_perp_symbols(self) -> list[str]:
        return [
            s for s, m in self.markets.items()
            if m.get("swap") and m.get("quote") == "USDT" and m.get("active", True)
        ]

    async def fetch_balance(self) -> float:
        bal = await self.exchange.fetch_balance()
        return float(bal.get("USDT", {}).get("free", 0.0))

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        try:
            await self.exchange.set_leverage(leverage, symbol)
        except Exception as exc:
            await self.storage.add_log("WARNING", f"set_leverage failed {symbol}: {exc}")

    async def fetch_mark_price(self, symbol: str) -> float:
        t = await self.exchange.fetch_ticker(symbol)
        return float(t.get("last") or t.get("mark") or t.get("close"))

    def calc_qty(self, symbol: str, margin: float, leverage: int, price: float) -> float:
        market = self.markets[symbol]
        notional = margin * leverage
        qty = notional / price
        precision_qty = float(self.exchange.amount_to_precision(symbol, qty))
        min_qty = (market.get("limits", {}).get("amount", {}) or {}).get("min") or 0
        if precision_qty < min_qty:
            precision_qty = min_qty
        return precision_qty

    async def place_entry_order(self, symbol: str, side: str, amount: float) -> dict[str, Any]:
        order_side = "buy" if side == "long" else "sell"
        return await self.exchange.create_order(symbol, "market", order_side, amount)

    async def close_position(self, symbol: str, side: str, amount: float) -> dict[str, Any]:
        close_side = "sell" if side == "long" else "buy"
        params = {"reduceOnly": True}
        return await self.exchange.create_order(symbol, "market", close_side, amount, None, params)

    async def fetch_positions(self) -> list[dict[str, Any]]:
        return await self.exchange.fetch_positions()

    async def safe_retry(self, coro_factory, retries: int = 3):
        for i in range(retries):
            try:
                return await coro_factory()
            except Exception:
                if i == retries - 1:
                    raise
                await asyncio.sleep(0.5 * (i + 1))
