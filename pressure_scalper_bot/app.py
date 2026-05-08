from __future__ import annotations

import asyncio
from contextlib import suppress
from enum import Enum

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from exchange import ExchangeClient
from risk import RiskManager
from scanner import Scanner
from storage import Storage


class BotState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RISK_PAUSED = "RISK_PAUSED"
    ERROR = "ERROR"


class BotController:
    def __init__(self):
        self.state = BotState.STOPPED
        self.storage = Storage()
        self.exchange = ExchangeClient(settings, self.storage)
        self.risk = RiskManager(settings, self.exchange, self.storage)
        self.scanner = Scanner(settings, self.exchange, self.risk, self.storage)
        self.scanner_task = None
        self.monitor_task = None

    async def start(self):
        if self.state in {BotState.RUNNING, BotState.STARTING}:
            return
        self.state = BotState.STARTING
        await self.storage.init()
        await self.exchange.initialize()
        self.scanner_task = asyncio.create_task(self.scanner.run())
        self.monitor_task = asyncio.create_task(self.risk.monitor(self.scanner.get_candles))
        self.state = BotState.RUNNING

    async def stop(self):
        self.state = BotState.STOPPED
        for task in [self.scanner_task, self.monitor_task]:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        if settings.close_positions_on_stop:
            await self.emergency_close_all()

    async def emergency_close_all(self):
        for symbol, trade in list(self.risk.open_trades.items()):
            await self.exchange.close_position(symbol, trade["side"], trade["quantity"])
            self.risk.open_trades.pop(symbol, None)
        await self.storage.add_log("WARNING", "Emergency close all executed")


bot = BotController()
app = FastAPI(title="Pressure Scalper Bot")
app.mount("/static", StaticFiles(directory="pressure_scalper_bot/static"), name="static")
templates = Jinja2Templates(directory="pressure_scalper_bot/templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    balance = 0.0
    if bot.exchange.exchange:
        balance = await bot.exchange.fetch_balance()
    daily_pnl = await bot.storage.calculate_daily_pnl() if bot.state != BotState.STOPPED else 0.0
    win_rate = await bot.storage.calculate_win_rate() if bot.state != BotState.STOPPED else 0.0
    trades = await bot.storage.get_trade_history(30) if bot.state != BotState.STOPPED else []
    logs = await bot.storage.get_recent_logs(50) if bot.state != BotState.STOPPED else []
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "state": bot.state.value,
        "mode": settings.binance_mode.upper(),
        "balance": round(balance, 3),
        "daily_pnl": round(daily_pnl, 3),
        "daily_target": settings.daily_target_usdt,
        "open_trades": list(bot.risk.open_trades.values()),
        "open_trades_count": len(bot.risk.open_trades),
        "win_rate": round(win_rate, 2),
        "total_trades": len(trades),
        "candidates": bot.scanner.candidates,
        "history": trades,
        "logs": logs,
    })


@app.post("/start")
async def start_bot():
    await bot.start()
    return RedirectResponse(url="/", status_code=303)


@app.post("/stop")
async def stop_bot():
    await bot.stop()
    return RedirectResponse(url="/", status_code=303)


@app.post("/pause")
async def pause_bot():
    bot.state = BotState.PAUSED
    return RedirectResponse(url="/", status_code=303)


@app.post("/resume")
async def resume_bot():
    bot.state = BotState.RUNNING
    return RedirectResponse(url="/", status_code=303)


@app.post("/emergency-close")
async def emergency_close():
    await bot.emergency_close_all()
    return RedirectResponse(url="/", status_code=303)


@app.post("/close/{symbol}")
async def manual_close(symbol: str):
    t = bot.risk.open_trades.get(symbol)
    if t:
        await bot.exchange.close_position(symbol, t["side"], t["quantity"])
        bot.risk.open_trades.pop(symbol, None)
    return RedirectResponse(url="/", status_code=303)
