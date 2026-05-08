from __future__ import annotations

import asyncio

from strategy import score_signal


class Scanner:
    def __init__(self, settings, exchange, risk, storage):
        self.settings = settings
        self.exchange = exchange
        self.risk = risk
        self.storage = storage
        self.candles: dict[str, dict[str, list]] = {}
        self.candidates: list[dict] = []

    def get_candles(self, symbol: str, tf: str):
        return self.candles.get(symbol, {}).get(tf)

    async def run(self):
        symbols = self.exchange.usdt_perp_symbols()
        while True:
            try:
                tickers = await self.exchange.exchange.watch_tickers(symbols)
                shortlist = self._stage_one(tickers)
                await self._stage_two(shortlist)
            except Exception as exc:
                await self.storage.add_log("ERROR", f"Scanner error: {exc}")
                await asyncio.sleep(1)

    def _stage_one(self, tickers: dict) -> list[str]:
        ranked = []
        for symbol, t in tickers.items():
            qv = float(t.get("quoteVolume") or 0)
            bid = float(t.get("bid") or 0)
            ask = float(t.get("ask") or 0)
            last = float(t.get("last") or 0)
            pct = abs(float(t.get("percentage") or 0))
            if qv < 3_000_000 or last <= 0 or bid <= 0 or ask <= 0:
                continue
            spread_bps = ((ask - bid) / last) * 10000
            if spread_bps > 15:
                continue
            ranked.append((symbol, pct, spread_bps))
        ranked.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in ranked[:12]]

    async def _stage_two(self, shortlist: list[str]):
        out = []
        for symbol in shortlist:
            if symbol in self.risk.open_trades:
                continue
            ok, _ = await self.risk.can_open_trade(symbol)
            if not ok:
                continue
            c15 = await self.exchange.exchange.fetch_ohlcv(symbol, "15m", limit=self.settings.candle_limit)
            c5 = await self.exchange.exchange.fetch_ohlcv(symbol, "5m", limit=self.settings.candle_limit)
            c1 = await self.exchange.exchange.fetch_ohlcv(symbol, "1m", limit=self.settings.candle_limit)
            ticker = await self.exchange.exchange.fetch_ticker(symbol)
            spread_bps = ((ticker["ask"] - ticker["bid"]) / ticker["last"]) * 10000
            self.candles.setdefault(symbol, {})["15m"] = c15
            self.candles.setdefault(symbol, {})["5m"] = c5
            self.candles.setdefault(symbol, {})["1m"] = c1

            sig = score_signal(symbol, c15, c5, c1, spread_bps)
            candidate = {"symbol": symbol, "score": sig["score"] if sig else 0, "direction": sig["side"] if sig else "-", "status": "ready" if sig else "watch"}
            out.append(candidate)
            if sig and sig["score"] >= self.settings.min_score_to_trade:
                await self.execute_trade(sig, ticker["last"])
        self.candidates = out

    async def execute_trade(self, sig: dict, price: float):
        ok, reason = await self.risk.can_open_trade(sig["symbol"])
        if not ok:
            return
        balance = await self.exchange.fetch_balance()
        if balance < self.settings.margin_per_trade:
            await self.storage.add_log("WARNING", "Insufficient balance")
            return
        await self.exchange.set_leverage(sig["symbol"], self.settings.leverage)
        qty = self.exchange.calc_qty(sig["symbol"], self.settings.margin_per_trade, self.settings.leverage, price)
        order = await self.exchange.safe_retry(lambda: self.exchange.place_entry_order(sig["symbol"], sig["side"], qty))
        trade = {
            **sig,
            "entry_price": price,
            "quantity": qty,
            "margin": self.settings.margin_per_trade,
            "leverage": self.settings.leverage,
            "target_profit_usdt": self.settings.target_profit_usdt,
            "emergency_sl_usdt": self.settings.emergency_sl_usdt,
            "opened_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "opened_dt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "order_id": order.get("id"),
        }
        trade_id = await self.storage.save_trade_open(trade)
        trade["trade_id"] = trade_id
        await self.risk.register_open_trade(trade)
        await self.storage.add_log("INFO", f"Opened {sig['side']} {sig['symbol']} qty={qty}")
