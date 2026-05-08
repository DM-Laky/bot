from __future__ import annotations

import aiosqlite
import json
from datetime import datetime, timezone
from typing import Any


class Storage:
    def __init__(self, db_path: str = "pressure_scalper.db") -> None:
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT, side TEXT, status TEXT, score INTEGER, reason TEXT,
                entry_price REAL, exit_price REAL, quantity REAL, margin REAL, leverage INTEGER,
                target_profit_usdt REAL, emergency_sl_usdt REAL,
                gross_pnl REAL DEFAULT 0, fees REAL DEFAULT 0, net_pnl REAL DEFAULT 0,
                result TEXT, opened_at TEXT, closed_at TEXT, exit_reason TEXT
            )""")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY, total_trades INTEGER, wins INTEGER, losses INTEGER,
                win_rate REAL, gross_pnl REAL, fees REAL, net_pnl REAL, max_drawdown REAL
            )""")
            await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT, message TEXT, created_at TEXT
            )""")
            await db.commit()

    async def add_log(self, level: str, message: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO logs(level, message, created_at) VALUES(?,?,?)",
                (level, message, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def save_trade_open(self, trade: dict[str, Any]) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """INSERT INTO trades(symbol, side, status, score, reason, entry_price, quantity, margin, leverage,
                target_profit_usdt, emergency_sl_usdt, opened_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trade["symbol"], trade["side"], "OPEN", trade["score"], json.dumps(trade["reason"]),
                    trade["entry_price"], trade["quantity"], trade["margin"], trade["leverage"],
                    trade["target_profit_usdt"], trade["emergency_sl_usdt"], trade["opened_at"],
                ),
            )
            await db.commit()
            return cur.lastrowid

    async def update_trade_closed(self, trade_id: int, update: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE trades SET status='CLOSED', exit_price=?, gross_pnl=?, fees=?, net_pnl=?,
                result=?, closed_at=?, exit_reason=? WHERE id=?""",
                (
                    update["exit_price"], update["gross_pnl"], update["fees"], update["net_pnl"],
                    update["result"], update["closed_at"], update["exit_reason"], trade_id,
                ),
            )
            await db.commit()

    async def get_open_trades(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM trades WHERE status='OPEN' ORDER BY id DESC")
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_trade_history(self, limit: int = 100) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def calculate_daily_pnl(self) -> float:
        date_prefix = datetime.now(timezone.utc).date().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT COALESCE(SUM(net_pnl),0) FROM trades WHERE closed_at LIKE ?",
                (f"{date_prefix}%",),
            )
            row = await cur.fetchone()
            return float(row[0] if row else 0)

    async def calculate_win_rate(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED'")
            total = (await cur.fetchone())[0]
            if total == 0:
                return 0.0
            cur = await db.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND net_pnl > 0")
            wins = (await cur.fetchone())[0]
            return wins / total * 100.0
