#!/usr/bin/env python3
"""Free Binance USD-M proxy + Hyperliquid native funding/candle collector.

No trading, keys, or paid services. UTC timestamps are *availability* timestamps.
"""
from __future__ import annotations
import argparse
import io
import json
import logging
import os
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

LOG = logging.getLogger("collector")
HL = "https://api.hyperliquid.xyz/info"
BVS = "https://data.binance.vision/data/futures/um/daily"
BINANCE = "https://fapi.binance.com/fapi/v1/exchangeInfo"
MS = 1000
METRICS_LABEL_CHANGE = pd.Timestamp("2026-06-25", tz="UTC")
ALIASES = {"PEPE": "1000PEPE", "BONK": "1000BONK", "SHIB": "1000SHIB",
           "FLOKI": "1000FLOKI", "RATS": "1000RATS"}
KLINE_FIELDS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
                "quote_volume", "trades", "taker_buy_base_volume",
                "taker_buy_quote_volume", "ignore"]
METRIC_FIELDS = ["create_time", "symbol", "sum_open_interest",
                 "sum_open_interest_value", "count_toptrader_long_short_ratio",
                 "sum_toptrader_long_short_ratio", "count_long_short_ratio",
                 "sum_taker_long_short_vol_ratio"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def request(method: str, url: str, **kwargs: Any) -> requests.Response:
    for attempt in range(6):
        try:
            r = requests.request(method, url, timeout=55, **kwargs)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"retryable {r.status_code}", response=r)
            return r
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError):
            if attempt == 5:
                raise
            time.sleep(min(2 ** attempt, 25))
    raise RuntimeError("retry exhausted")


def info(payload: dict[str, Any]) -> Any:
    r = request("POST", HL, json=payload)
    r.raise_for_status()
    return r.json()


def get_binance_symbols() -> set[str]:
    r = request("GET", BINANCE)
    r.raise_for_status()
    return {x["symbol"] for x in r.json()["symbols"]
            if x.get("contractType") == "PERPETUAL"
            and x.get("status") == "TRADING"
            and x.get("quoteAsset") == "USDT"}


def choose_universe(n: int, out: Path) -> list[dict[str, Any]]:
    meta, ctx = info({"type": "metaAndAssetCtxs"})
    available = get_binance_symbols()
    result = []
    for asset, c in zip(meta["universe"], ctx, strict=True):
        coin = asset["name"]
        if asset.get("isDelisted") or c is None:
            continue
        candidate = f"{coin}USDT"
        aliases = [candidate, f"{ALIASES.get(coin, coin)}USDT"]
        symbol = next((a for a in aliases if a in available), None)
        if symbol is None:
            continue
        try:
            volume = float(c.get("dayNtlVlm") or 0)
        except (TypeError, ValueError):
            continue
        if volume <= 0:
            continue
        result.append({"coin": coin, "symbol": symbol, "hl_day_notional_usd": volume})
    result.sort(key=lambda x: x["hl_day_notional_usd"], reverse=True)
    chosen = []
    used = set()
    for row in result:
        if row["symbol"] not in used:
            chosen.append(row)
            used.add(row["symbol"])
        if len(chosen) >= n:
            break
    out.mkdir(parents=True, exist_ok=True)
    (out / "universe.json").write_text(json.dumps({
        "selected_at_utc": utcnow().isoformat(), "requested": n,
        "selected": chosen, "selection_rule": "Hyperliquid 24h notional desc, Binance USD-M active"
    }, indent=2))
    if len(chosen) < n:
        LOG.warning("Only %s qualifying pairs found (requested %s)", len(chosen), n)
    return chosen


def download_csv_zip(url: str) -> pd.DataFrame | None:
    r = request("GET", url)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        csvs = [name for name in z.namelist() if name.endswith(".csv")]
        if len(csvs) != 1:
            raise ValueError(f"Unexpected archive structure: {url}")
        with z.open(csvs[0]) as raw:
            return pd.read_csv(raw, header=None if "/klines/" in url else "infer",
                               low_memory=False)


def normalize_klines(df: pd.DataFrame) -> pd.DataFrame:
    if df.shape[1] != 12:
        raise ValueError(f"Expected 12 kline columns, got {df.shape[1]}")
    df.columns = KLINE_FIELDS
    # Some Binance archives unexpectedly include a header row.
    df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
    df = df.dropna(subset=["open_time"]).copy()
    for c in ["open", "high", "low", "close", "volume", "quote_volume",
              "taker_buy_base_volume", "taker_buy_quote_volume"]:
        df[c] = pd.to_numeric(df[c], errors="raise")
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    # End of minute is the first safe decision timestamp; do not use exchange close_time+1ms ambiguity.
    df["available_at"] = df["open_time"] + pd.Timedelta(minutes=1)
    df["taker_sell_base_volume"] = df["volume"] - df["taker_buy_base_volume"]
    df["aggressor_imbalance"] = ((2 * df["taker_buy_base_volume"] - df["volume"]) /
                                 df["volume"].where(df["volume"] > 0))
    if (df["taker_sell_base_volume"] < -1e-7).any():
        raise ValueError("Taker buy volume exceeds total volume")
    return df[["open_time", "available_at", "open", "high", "low", "close",
               "volume", "quote_volume", "taker_buy_base_volume",
               "taker_sell_base_volume", "aggressor_imbalance"]].sort_values("open_time")


def normalize_metrics(df: pd.DataFrame, day: str) -> pd.DataFrame:
    # Published archives sometimes contain headers; detect rather than blindly assume.
    if "create_time" not in df.columns:
        if df.shape[1] < len(METRIC_FIELDS):
            raise ValueError(f"Unexpected metrics columns: {list(df.columns)}")
        df.columns = METRIC_FIELDS + [f"extra_{i}" for i in range(df.shape[1] - len(METRIC_FIELDS))]
    df["create_time"] = pd.to_datetime(df["create_time"], utc=True, errors="coerce")
    df = df.dropna(subset=["create_time"]).copy()
    for c in ("sum_open_interest_value", "count_toptrader_long_short_ratio"):
        if c not in df:
            raise ValueError(f"Missing metrics column: {c}")
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Data archive changed create_time from 5m interval END to START on 2026-06-25.
    # Conservative +5m for dates on/after change; previous labels are already end times.
    df["available_at"] = df["create_time"] + (
        pd.Timedelta(minutes=5) if pd.Timestamp(day, tz="UTC") >= METRICS_LABEL_CHANGE
        else pd.Timedelta(0)
    )
    return df[["create_time", "available_at", "sum_open_interest_value",
               "count_toptrader_long_short_ratio"]].sort_values("available_at")


def parquet_save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, compression="zstd", index=False)
    os.replace(tmp, path)


def get_day(symbol: str, day: str, out: Path) -> dict[str, Any]:
    status: dict[str, Any] = {"symbol": symbol, "day": day}
    for typ in ("klines", "metrics"):
        target = out / "binance" / typ / symbol / f"{day}.parquet"
        if target.exists():
            status[typ] = "cached"
            continue
        url = (f"{BVS}/{typ}/{symbol}/" +
               (f"1m/{symbol}-1m-{day}.zip" if typ == "klines"
                else f"{symbol}-metrics-{day}.zip"))
        df = download_csv_zip(url)
        if df is None:
            status[typ] = "missing"
            continue
        parsed = normalize_klines(df) if typ == "klines" else normalize_metrics(df, day)
        if parsed.empty:
            status[typ] = "empty"
            continue
        parquet_save(parsed, target)
        status[typ] = len(parsed)
    return status


def collect_funding(coin: str, start_ms: int, end_ms: int, out: Path) -> int:
    target = out / "hyperliquid" / "funding" / f"{coin}.parquet"
    if target.exists():
        existing = pd.read_parquet(target)
        if not existing.empty:
            start_ms = max(start_ms, int(existing["time"].max().timestamp() * MS) + 1)
    else:
        existing = pd.DataFrame()
    rows: list[dict] = []
    cursor = start_ms
    for _ in range(2000):
        if cursor >= end_ms:
            break
        page = info({"type": "fundingHistory", "coin": coin,
                     "startTime": cursor, "endTime": end_ms})
        if not isinstance(page, list) or not page:
            break
        rows.extend(page)
        last = max(int(x["time"]) for x in page)
        if last < cursor:
            raise ValueError("Funding pagination not progressing")
        cursor = last + 1
        time.sleep(0.15)
    else:
        raise RuntimeError(f"Funding pagination exceeded 2000 pages: {coin}")
    if rows:
        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(pd.to_numeric(df["time"]), unit="ms", utc=True)
        df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="raise")
        df["available_at"] = df["time"]
        df = df[["time", "available_at", "fundingRate"]]
        all_data = pd.concat([existing, df], ignore_index=True)
        all_data = all_data.drop_duplicates("time").sort_values("time")
        parquet_save(all_data, target)
    return len(rows)


def collect_native_candles(coin: str, interval: str, out: Path, end_ms: int) -> int:
    duration = {"1m": 60_000, "15m": 900_000}[interval]
    start = end_ms - 5000 * duration
    payload = {"type": "candleSnapshot",
               "req": {"coin": coin, "interval": interval,
                       "startTime": start, "endTime": end_ms}}
    rows = info(payload)
    if not isinstance(rows, list) or not rows:
        return 0
    df = pd.DataFrame(rows)
    for c in ("t", "T", "o", "h", "l", "c", "v"):
        if c not in df:
            raise ValueError(f"HL candle missing {c}")
    df["open_time"] = pd.to_datetime(pd.to_numeric(df["t"]), unit="ms", utc=True)
    df["available_at"] = df["open_time"] + pd.Timedelta(milliseconds=duration)
    for c in ("o", "h", "l", "c", "v"):
        df[c] = pd.to_numeric(df[c])
    # Exclude still-open candle; intervals are fully closed before use.
    df = df[df["available_at"] <= pd.to_datetime(end_ms, unit="ms", utc=True)]
    target = out / "hyperliquid" / "candles" / interval / f"{coin}.parquet"
    parquet_save(df[["open_time", "available_at", "o", "h", "l", "c", "v"]]
                 .drop_duplicates("open_time").sort_values("open_time"), target)
    return len(df)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=105)
    p.add_argument("--count", type=int, default=30)
    p.add_argument("--out", type=Path, default=Path("data"))
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--skip-candles", action="store_true")
    a = p.parse_args()
    if not 1 <= a.days <= 365 or not 1 <= a.count <= 30:
        p.error("days must be 1..365, count 1..30")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    end = utcnow()
    # Daily archives may be incomplete / unpublished today. Do not request current UTC date.
    first_day = (end.date() - timedelta(days=a.days)).isoformat()
    days = [(end.date() - timedelta(days=i)).isoformat()
            for i in range(a.days, 0, -1)]
    universe = choose_universe(a.count, a.out)
    if not universe:
        raise RuntimeError("Empty intersected universe")
    tasks = [(row["symbol"], day) for row in universe for day in days]
    results = []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs = {pool.submit(get_day, symbol, day, a.out): (symbol, day)
                for symbol, day in tasks}
        for job in as_completed(jobs):
            symbol, day = jobs[job]
            try:
                results.append(job.result())
            except Exception as exc:
                LOG.error("Archive failed %s %s: %s", symbol, day, exc)
                results.append({"symbol": symbol, "day": day, "error": str(exc)})
    start_ms = int(datetime.fromisoformat(first_day).replace(tzinfo=timezone.utc).timestamp() * MS)
    end_ms = int(end.timestamp() * MS)
    native = {}
    for row in universe:
        coin = row["coin"]
        native[coin] = {}
        try:
            native[coin]["funding_rows_added"] = collect_funding(coin, start_ms, end_ms, a.out)
            if not a.skip_candles:
                for interval in ("1m", "15m"):
                    native[coin][f"candles_{interval}"] = collect_native_candles(
                        coin, interval, a.out, end_ms)
        except Exception as exc:
            native[coin]["error"] = str(exc)
            LOG.error("HL native failed %s: %s", coin, exc)
    manifest = {
        "created_utc": utcnow().isoformat(), "first_day": first_day,
        "last_day": days[-1], "universe_count": len(universe),
        "archive_expected_files": len(tasks) * 2,
        "archives_success": sum(1 for r in results for k in ("klines", "metrics")
                                if isinstance(r.get(k), int) or r.get(k) == "cached"),
        "archives_missing": sum(1 for r in results for k in ("klines", "metrics")
                                if r.get(k) == "missing"),
        "archives_errors": [r for r in results if "error" in r],
        "native": native, "sources": {"price": "binance_um_proxy",
                                     "funding": "hyperliquid_native"},
    }
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    LOG.info("Manifest: %s", json.dumps({k: v for k, v in manifest.items() if k != "native"}))
    if manifest["archives_success"] == 0:
        raise RuntimeError("No archives collected; refusing false success")


if __name__ == "__main__":
    main()
