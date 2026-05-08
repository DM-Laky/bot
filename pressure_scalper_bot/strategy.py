from __future__ import annotations

import pandas as pd


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def score_signal(symbol: str, c15: list, c5: list, c1: list, spread_bps: float) -> dict | None:
    df15 = pd.DataFrame(c15, columns=["ts", "o", "h", "l", "c", "v"])
    df5 = pd.DataFrame(c5, columns=["ts", "o", "h", "l", "c", "v"])
    df1 = pd.DataFrame(c1, columns=["ts", "o", "h", "l", "c", "v"])
    if min(len(df15), len(df5), len(df1)) < 20:
        return None

    score = 0
    reasons = []

    df15["ema20"] = _ema(df15["c"], 20)
    df15["ema50"] = _ema(df15["c"], 50)
    last15 = df15.iloc[-1]
    long_bias = last15.c > last15.ema20 >= last15.ema50
    short_bias = last15.c < last15.ema20 <= last15.ema50

    side = None
    if long_bias:
        score += 20
        reasons.append("15m bullish bias")
        side = "long"
    elif short_bias:
        score += 20
        reasons.append("15m bearish bias")
        side = "short"

    last5 = df5.iloc[-1]
    avg5vol = df5["v"].tail(20).mean()
    if side == "long" and last5.c > last5.o and last5.v > avg5vol:
        score += 25
        reasons.append("5m bullish momentum + volume")
    elif side == "short" and last5.c < last5.o and last5.v > avg5vol:
        score += 25
        reasons.append("5m bearish momentum + volume")

    recent1 = df1.tail(4)
    last1 = df1.iloc[-1]
    avg1vol = df1["v"].tail(20).mean()
    if side == "long":
        micro_high = recent1["h"].iloc[:-1].max()
        if last1.c > last1.o and last1.c > micro_high:
            score += 30
            reasons.append("1m micro high break")
    elif side == "short":
        micro_low = recent1["l"].iloc[:-1].min()
        if last1.c < last1.o and last1.c < micro_low:
            score += 30
            reasons.append("1m micro low break")

    if last1.v > avg1vol * 1.15:
        score += 10
        reasons.append("volume spike")

    if spread_bps <= 8:
        score += 10
        reasons.append("spread acceptable")

    body_pct = abs(last1.c - last1.o) / max(last1.o, 1e-9)
    if body_pct < 0.006:
        score += 5
        reasons.append("not overextended")

    if side and score >= 80:
        return {
            "symbol": symbol,
            "side": side,
            "score": score,
            "entry_type": "market",
            "reason": reasons,
            "risk_notes": [],
        }
    return None


def momentum_fail(side: str, c1: list) -> bool:
    df = pd.DataFrame(c1, columns=["ts", "o", "h", "l", "c", "v"])
    if len(df) < 6:
        return False
    last = df.iloc[-1]
    prev = df.iloc[-2]
    avg_vol = df["v"].tail(10).mean()
    if side == "long":
        return (last.c < prev.l) or (last.c < last.o and last.v > avg_vol * 1.2) or (last.v < avg_vol * 0.5)
    return (last.c > prev.h) or (last.c > last.o and last.v > avg_vol * 1.2) or (last.v < avg_vol * 0.5)
