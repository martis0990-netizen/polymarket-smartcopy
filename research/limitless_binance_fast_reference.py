"""Public Binance 1-second price reference for the independent Limitless capture.

This is observation data for maker diagnostics, never a trade signal or fill.
The existing hourly paper model continues to use its frozen 1-minute REST input.
"""
import asyncio
from decimal import Decimal, InvalidOperation
import json
import time


URL = ("wss://data-stream.binance.vision/stream?streams="
       "btcusdt@kline_1s/ethusdt@kline_1s")
STREAMS = {"BTCUSDT": "btcusdt@kline_1s", "ETHUSDT": "ethusdt@kline_1s"}


def decode(message):
    """Accept only public BTC/ETH spot one-second kline envelopes."""
    if not isinstance(message, dict) or not isinstance(message.get("data"), dict):
        return None
    data = message["data"]
    symbol = data.get("s")
    if message.get("stream") != STREAMS.get(symbol) or data.get("e") != "kline":
        return None
    k = data.get("k")
    if not isinstance(k, dict) or k.get("s") != symbol or k.get("i") != "1s":
        return None
    start, finish, event = k.get("t"), k.get("T"), data.get("E")
    if (not all(type(x) is int for x in (start, finish, event))
            or start % 1000 or finish != start + 999 or event < start
            or type(k.get("x")) is not bool):
        return None
    try:
        price = Decimal(str(k["c"]))
    except (KeyError, InvalidOperation, ValueError, TypeError):
        return None
    if not price.is_finite() or price <= 0:
        return None
    return symbol, start, data


def record(recorder, message, previous):
    """A missing second is an observation gap, not proof of a lost trade."""
    decoded = decode(message)
    if decoded is None:
        recorder.write("binance_fast_invalid", stream=message.get("stream") if isinstance(message, dict) else None)
        return False
    symbol, start, data = decoded
    prior = previous.get(symbol)
    if prior is not None and start > prior + 1000:
        recorder.write("binance_fast_gap", symbol=symbol, from_open_ms=prior,
                       to_open_ms=start, unobserved_seconds=(start - prior) // 1000 - 1)
    elif prior is not None and start < prior:
        recorder.write("binance_fast_out_of_order", symbol=symbol, open_ms=start,
                       previous_open_ms=prior)
        return False
    previous[symbol] = start
    # Recorder stamps local receipt at write time. E/k.t are publisher times only.
    recorder.write("binance_fast_reference", stream=STREAMS[symbol], raw=data)
    return True


async def capture(recorder, end):
    """Independent bounded stream; a failure cannot change hourly decisions."""
    previous = {}
    delay = 2
    while time.monotonic() < end and not recorder.capped:
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.ws_connect(URL, heartbeat=20, timeout=8) as ws:
                    recorder.write("binance_fast_connect", streams=list(STREAMS.values()))
                    delay = 2
                    while time.monotonic() < end and not recorder.capped:
                        try:
                            msg = await asyncio.wait_for(ws.receive(),
                                timeout=min(5, max(.01, end - time.monotonic())))
                        except asyncio.TimeoutError:
                            continue
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                payload = json.loads(msg.data)
                            except (TypeError, ValueError):
                                recorder.write("binance_fast_invalid", stream=None)
                                continue
                            if isinstance(payload, dict) and payload.get("stream") == "!serverShutdown":
                                recorder.write("binance_fast_server_shutdown")
                                break
                            record(recorder, payload, previous)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE,
                                          aiohttp.WSMsgType.ERROR):
                            break
            recorder.write("binance_fast_disconnect")
        except asyncio.CancelledError:
            raise
        except Exception as error:
            recorder.write("binance_fast_error", error=type(error).__name__, detail=str(error)[:300])
        if time.monotonic() < end and not recorder.capped:
            await asyncio.sleep(min(delay, max(0, end - time.monotonic())))
            delay = min(15, delay * 2)
