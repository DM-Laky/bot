from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


load_dotenv()


@dataclass(slots=True)
class Settings:
    binance_api_key: str = os.getenv("BINANCE_API_KEY", "")
    binance_secret: str = os.getenv("BINANCE_SECRET", "")
    binance_mode: str = os.getenv("BINANCE_MODE", "testnet").lower()

    margin_per_trade: float = float(os.getenv("MARGIN_PER_TRADE", "5"))
    leverage: int = int(os.getenv("LEVERAGE", "15"))
    target_profit_usdt: float = float(os.getenv("TARGET_PROFIT_USDT", "0.30"))
    emergency_sl_usdt: float = float(os.getenv("EMERGENCY_SL_USDT", "0.60"))

    max_open_trades: int = int(os.getenv("MAX_OPEN_TRADES", "2"))
    daily_target_usdt: float = float(os.getenv("DAILY_TARGET_USDT", "10"))
    daily_max_loss_usdt: float = float(os.getenv("DAILY_MAX_LOSS_USDT", "5"))
    max_consecutive_losses: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    symbol_cooldown_seconds: int = int(os.getenv("SYMBOL_COOLDOWN_SECONDS", "600"))

    min_score_to_trade: int = int(os.getenv("MIN_SCORE_TO_TRADE", "80"))
    candle_limit: int = int(os.getenv("CANDLE_LIMIT", "50"))

    bot_host: str = os.getenv("BOT_HOST", "0.0.0.0")
    bot_port: int = int(os.getenv("BOT_PORT", "8000"))

    max_hold_seconds: int = int(os.getenv("MAX_HOLD_SECONDS", "180"))
    min_hold_seconds: int = int(os.getenv("MIN_HOLD_SECONDS", "60"))
    monitor_interval_seconds: float = float(os.getenv("MONITOR_INTERVAL_SECONDS", "0.35"))
    btc_pause_minutes: int = int(os.getenv("BTC_PAUSE_MINUTES", "45"))

    close_positions_on_stop: bool = os.getenv("CLOSE_POSITIONS_ON_STOP", "false").lower() == "true"

    def validate(self) -> None:
        if self.binance_mode not in {"testnet", "live"}:
            raise ValueError("BINANCE_MODE must be 'testnet' or 'live'.")
        if self.binance_mode == "live":
            print("⚠️ LIVE MODE ENABLED: REAL MONEY TRADING IS ACTIVE.")


settings = Settings()
settings.validate()
