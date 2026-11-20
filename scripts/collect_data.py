#!/usr/bin/env python3
"""Full-universe, survivorship-free data collector.

Modes
-----
universe  Build data/universe.json: EVERY Binance USD-M USDT perpetual that has
          ever published a daily archive (delisted ones included), its first/last
          available day, and its Hyperliquid mapping. No volume or popularity
          filter: liquidity filters belong in research code and must be
          point-in-time, never applied at download time with today's data.
binance   Download daily 1m klines + 5m metrics for one shard of that universe.
native    Hyperliquid: funding history, candles (1m..1d, merged with prior
          history), and a snapshot of asset contexts (open interest, funding...).

No trading, no keys, no paid services. All timestamps are UTC and every table
carries `available_at` (the first instant the row could have been known).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

LOG = logging.getLogger("collector")
HL = "https://api.hyperliquid.xyz/info"
BV_HOST = "https://data.binance.vision"
BVS = f"{BV_HOST}/data/futures/um/daily"
S3_LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
MS = 1000
METRICS_LABEL_CHANGE = pd.Timestamp("2026-06-25", tz="UTC")
KLINE_FIELDS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
                "quote_volume", "trades", "taker_buy_base_volume",
                "taker_buy_quote_volume", "ignore"]
METRIC_FIELDS = ["create_time", "symbol", "sum_open_interest",
                 "sum_open_interest_value", "count_toptrader_long_short_ratio",
                 "sum_toptrader_long_short_ratio", "count_long_short_ratio",
                 "sum_taker_long_short_vol_ratio"]
HL_INTERVALS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000,
                "4h": 14_400_000, "1d": 86_400_000}
DAY_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})\.zip$")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def write_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


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


# ----------------------------------------------------------------- Binance listing
def parse_s3_listing(xml_text: str) -> tuple[list[str], list[str], bool, str | None]:
    """Parse an S3 ListObjects (v1) response -> keys, prefixes, truncated, next marker."""
    root = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", xml_text, count=1))
    keys = [e.findtext("Key") or "" for e in root.findall("Contents")]
    prefixes = [e.findtext("Prefix") or "" for e in root.findall("CommonPrefixes")]
    truncated = (root.findtext("IsTruncated") or "").strip().lower() == "true"
    return keys, prefixes, truncated, root.findtext("NextMarker")


def s3_list(prefix: str, delimiter: str | None = None) -> tuple[list[str], list[str]]:
    keys: list[str] = []
    prefixes: list[str] = []
    marker: str | None = None
    for _ in range(500):
        params = {"prefix": prefix, "max-keys": "1000"}
        if delimiter:
            params["delimiter"] = delimiter
        if marker:
            params["marker"] = marker
        r = request("GET", S3_LIST, params=params)
        r.raise_for_status()
        k, p, truncated, nxt = parse_s3_listing(r.text)
        keys += k
        prefixes += p
        if not truncated:
            return keys, prefixes
        marker = nxt or (k[-1] if k else (p[-1] if p else None))
        if marker is None:
            return keys, prefixes
    raise RuntimeError(f"S3 listing did not terminate: {prefix}")


def list_binance_symbols() -> list[str]:
    """Every USDT-margined perpetual folder ever published (delisted included)."""
    _, prefixes = s3_list("data/futures/um/daily/klines/", delimiter="/")
    symbols = []
    for p in prefixes:
        sym = p.rstrip("/").split("/")[-1]
        # Quarterly futures carry a _YYMMDD suffix; perpetuals do not.
        if sym.endswith("USDT") and "_" not in sym and sym.isascii():
            symbols.append(sym)
    return sorted(set(symbols))


def list_days(kind: str, symbol: str) -> list[str]:
    prefix = f"data/futures/um/daily/{kind}/{symbol}/" + ("1m/" if kind == "klines" else "")
    keys, _ = s3_list(prefix)
    return sorted({m.group(1) for k in keys if (m := DAY_RE.search(k))})


def hl_to_binance(coin: str, available: set[str]) -> str | None:
    """Map a Hyperliquid coin to a Binance USDT perp symbol, or None."""
    candidates = [f"{coin}USDT"]
    if len(coin) > 1 and coin[0] == "k" and coin[1].isupper():  # kPEPE -> 1000PEPE
        candidates.append(f"1000{coin[1:]}USDT")
    candidates += [f"1000{coin}USDT", f"1000000{coin}USDT", f"1M{coin}USDT"]
    return next((c for c in candidates if c in available), None)


def in_shard(symbol: str, shard: int, shards: int) -> bool:
    """Stable assignment: unaffected by symbols being listed or delisted later."""
    return int(hashlib.md5(symbol.encode()).hexdigest(), 16) % shards == shard


def hl_universe() -> tuple[list[dict[str, Any]], list[Any]]:
    meta, ctx = info({"type": "metaAndAssetCtxs"})
    return meta["universe"], ctx


def build_universe(out: Path, workers: int = 8) -> dict[str, Any]:
    symbols = list_binance_symbols()
    LOG.info("Binance USDT perpetual folders: %s", len(symbols))
    days: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = {pool.submit(list_days, "klines", s): s for s in symbols}
        for job in as_completed(jobs):
            days[jobs[job]] = job.result()
    hl_assets, _ = hl_universe()
    hl_coins = [a["name"] for a in hl_assets]
    avail = set(symbols)
    mapping = {c: hl_to_binance(c, avail) for c in hl_coins}
    reverse = {v: k for k, v in mapping.items() if v}
    today = utcnow().date()
    rows = []
    for s in symbols:
        d = days[s]
        if not d:
            continue
        last = date.fromisoformat(d[-1])
        rows.append({"symbol": s, "first_day": d[0], "last_day": d[-1], "n_days": len(d),
                     "active": (today - last).days <= 3, "hl_coin": reverse.get(s)})
    universe = {
        "created_utc": utcnow().isoformat(),
        "selection_rule": "ALL Binance USD-M USDT perpetuals with a published 1m archive; "
                          "no volume/survivor filter",
        "symbols": rows,
        "hyperliquid_coins": hl_coins,
        "hyperliquid_without_binance": sorted(c for c, v in mapping.items() if v is None),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "universe.json").write_text(json.dumps(universe, indent=2))
    n_active = sum(r["active"] for r in rows)
    msg = (f"Universe: {len(rows)} Binance perps ({n_active} active, "
           f"{len(rows) - n_active} delisted/inactive); {len(hl_coins)} HL coins, "
           f"{len(universe['hyperliquid_without_binance'])} without Binance match")
    LOG.info(msg)
    write_summary(f"### Universe\n{msg}")
    return universe


# ----------------------------------------------------------------- normalizers
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
    # Archives switched from ms to microsecond timestamps in 2025; normalise.
    unit = "us" if df["open_time"].iloc[0] > 1e14 else "ms"
    df["open_time"] = pd.to_datetime(df["open_time"], unit=unit, utc=True)
    # End of minute is the first safe decision timestamp.
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
    # create_time changed from interval END to START on 2026-06-25; be conservative (+5m).
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


def merge_frames(existing: pd.DataFrame | None, new: pd.DataFrame, key: str) -> pd.DataFrame:
    """Append new rows to history; newest wins on duplicates. Never drops history."""
    if existing is None or existing.empty:
        return new.drop_duplicates(key).sort_values(key)
    both = pd.concat([existing, new], ignore_index=True)
    return both.drop_duplicates(key, keep="last").sort_values(key).reset_index(drop=True)


# ----------------------------------------------------------------- Binance mode
def get_day(kind: str, symbol: str, day: str, out: Path) -> str | int:
    target = out / "binance" / kind / symbol / f"{day}.parquet"
    if target.exists():
        return "cached"
    url = (f"{BVS}/{kind}/{symbol}/" +
           (f"1m/{symbol}-1m-{day}.zip" if kind == "klines" else f"{symbol}-metrics-{day}.zip"))
    df = download_csv_zip(url)
    if df is None:
        return "missing"
    parsed = normalize_klines(df) if kind == "klines" else normalize_metrics(df, day)
    if parsed.empty:
        return "empty"
    parquet_save(parsed, target)
    return len(parsed)


def window(start: str | None, end: str | None) -> tuple[date, date]:
    last = date.fromisoformat(end) if end else utcnow().date() - timedelta(days=1)
    first = date.fromisoformat(start) if start else last - timedelta(days=6)
    if first > last:
        raise ValueError("start after end")
    return first, last


def run_binance(a: argparse.Namespace) -> None:
    first, last = window(a.start, a.end)
    symbols = [s for s in list_binance_symbols() if in_shard(s, a.shard, a.shards)]
    if a.max_symbols:
        symbols = symbols[: a.max_symbols]
    LOG.info("Shard %s/%s: %s symbols, window %s..%s", a.shard, a.shards,
             len(symbols), first, last)
    f, l = first.isoformat(), last.isoformat()
    tasks: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs = {pool.submit(list_days, kind, s): (kind, s)
                for s in symbols for kind in ("klines", "metrics")}
        for job in as_completed(jobs):
            kind, s = jobs[job]
            tasks += [(kind, s, d) for d in job.result() if f <= d <= l]
    LOG.info("Files to fetch or verify: %s", len(tasks))
    counts = {"ok": 0, "cached": 0, "missing": 0, "empty": 0, "error": 0}
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        jobs = {pool.submit(get_day, k, s, d, a.out): (k, s, d) for k, s, d in tasks}
        for job in as_completed(jobs):
            k, s, d = jobs[job]
            try:
                res = job.result()
                counts["ok" if isinstance(res, int) else res] += 1
            except Exception as exc:  # noqa: BLE001 - recorded, not hidden
                counts["error"] += 1
                if len(errors) < 50:
                    errors.append({"kind": k, "symbol": s, "day": d, "error": str(exc)})
                LOG.error("Archive failed %s %s %s: %s", k, s, d, exc)
    manifest = {"created_utc": utcnow().isoformat(), "mode": "binance", "shard": a.shard,
                "shards": a.shards, "window": [f, l], "symbols": len(symbols),
                "tasks": len(tasks), "counts": counts, "errors": errors}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"manifest_binance_{a.shard}.json").write_text(json.dumps(manifest, indent=2))
    write_summary(f"### Binance shard {a.shard}/{a.shards}\n"
                  f"symbols={len(symbols)} files={len(tasks)} counts={counts}")
    LOG.info("Manifest: %s", json.dumps({k: v for k, v in manifest.items() if k != "errors"}))
    if tasks and counts["ok"] + counts["cached"] == 0:
        raise RuntimeError("No archives collected; refusing false success")


# ----------------------------------------------------------------- Hyperliquid mode
def collect_funding(coin: str, start_ms: int, end_ms: int, out: Path) -> int:
    target = out / "hyperliquid" / "funding" / f"{coin}.parquet"
    existing = pd.read_parquet(target) if target.exists() else None
    if existing is not None and not existing.empty:
        start_ms = max(start_ms, int(existing["time"].max().timestamp() * MS) + 1)
    rows: list[dict] = []
    cursor = start_ms
    for _ in range(3000):
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
        time.sleep(0.2)
    else:
        raise RuntimeError(f"Funding pagination exceeded 3000 pages: {coin}")
    if rows:
        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(pd.to_numeric(df["time"]), unit="ms", utc=True)
        df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="raise")
        df["premium"] = pd.to_numeric(df.get("premium"), errors="coerce")
        df["available_at"] = df["time"]
        parquet_save(merge_frames(existing, df[["time", "available_at", "fundingRate",
                                                "premium"]], "time"), target)
    return len(rows)


def collect_native_candles(coin: str, interval: str, out: Path, end_ms: int) -> int:
    duration = HL_INTERVALS[interval]
    rows = info({"type": "candleSnapshot",
                 "req": {"coin": coin, "interval": interval,
                         "startTime": end_ms - 5000 * duration, "endTime": end_ms}})
    if not isinstance(rows, list) or not rows:
        return 0
    df = pd.DataFrame(rows)
    for c in ("t", "o", "h", "l", "c", "v"):
        if c not in df:
            raise ValueError(f"HL candle missing {c}")
    df["open_time"] = pd.to_datetime(pd.to_numeric(df["t"]), unit="ms", utc=True)
    df["available_at"] = df["open_time"] + pd.Timedelta(milliseconds=duration)
    for c in ("o", "h", "l", "c", "v"):
        df[c] = pd.to_numeric(df[c])
    df["n"] = pd.to_numeric(df["n"], errors="coerce") if "n" in df else pd.NA
    df = df[df["available_at"] <= pd.to_datetime(end_ms, unit="ms", utc=True)]  # closed only
    target = out / "hyperliquid" / "candles" / interval / f"{coin}.parquet"
    existing = pd.read_parquet(target) if target.exists() else None
    cols = ["open_time", "available_at", "o", "h", "l", "c", "v", "n"]
    parquet_save(merge_frames(existing, df[cols], "open_time"), target)
    return len(df)


def snapshot_contexts(out: Path) -> int:
    assets, ctx = hl_universe()
    now = utcnow()
    rows = []
    for asset, c in zip(assets, ctx, strict=True):
        if c is None:
            continue
        rows.append({"coin": asset["name"], "captured_at": now,
                     **{k: pd.to_numeric(c.get(k), errors="coerce")
                        for k in ("dayNtlVlm", "funding", "openInterest", "oraclePx",
                                  "markPx", "midPx", "premium", "prevDayPx")}})
    if rows:
        path = out / "hyperliquid" / "ctx" / f"{now:%Y%m%dT%H%M%SZ}.parquet"
        parquet_save(pd.DataFrame(rows), path)
    return len(rows)


def run_native(a: argparse.Namespace) -> None:
    assets, _ = hl_universe()
    coins = [x["name"] for x in assets]
    if a.max_symbols:
        coins = coins[: a.max_symbols]
    end = utcnow()
    end_ms = int(end.timestamp() * MS)
    start_ms = int(datetime.fromisoformat(a.funding_start).replace(tzinfo=timezone.utc)
                   .timestamp() * MS)
    ctx_rows = snapshot_contexts(a.out)
    results: dict[str, Any] = {}
    for coin in coins:
        r: dict[str, Any] = {}
        try:
            r["funding_rows_added"] = collect_funding(coin, start_ms, end_ms, a.out)
            for interval in HL_INTERVALS:
                r[f"candles_{interval}"] = collect_native_candles(coin, interval, a.out, end_ms)
        except Exception as exc:  # noqa: BLE001
            r["error"] = str(exc)
            LOG.error("HL native failed %s: %s", coin, exc)
        results[coin] = r
        time.sleep(0.1)
    failed = [c for c, r in results.items() if "error" in r]
    manifest = {"created_utc": utcnow().isoformat(), "mode": "native", "coins": len(coins),
                "ctx_rows": ctx_rows, "failed": failed, "native": results}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "manifest_native.json").write_text(json.dumps(manifest, indent=2))
    write_summary(f"### Hyperliquid native\ncoins={len(coins)} failed={len(failed)} "
                  f"ctx_rows={ctx_rows}")
    if len(failed) == len(coins):
        raise RuntimeError("All Hyperliquid coins failed; refusing false success")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["universe", "binance", "native"])
    p.add_argument("--out", type=Path, default=Path("data"))
    p.add_argument("--start", default=None, help="YYYY-MM-DD (binance); default last 7 days")
    p.add_argument("--end", default=None, help="YYYY-MM-DD; default yesterday UTC")
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--max-symbols", type=int, default=0, help="smoke tests only")
    p.add_argument("--funding-start", default="2023-06-01")
    a = p.parse_args()
    if not 0 <= a.shard < a.shards:
        p.error("shard must satisfy 0 <= shard < shards")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.mode == "universe":
        build_universe(a.out, a.workers)
    elif a.mode == "binance":
        run_binance(a)
    else:
        run_native(a)


if __name__ == "__main__":
    main()
