from pathlib import Path
import importlib.util
import pandas as pd

spec = importlib.util.spec_from_file_location(
    "collector", Path(__file__).resolve().parents[1] / "scripts" / "collect_data.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
<Prefix>data/futures/um/daily/klines/</Prefix><IsTruncated>true</IsTruncated>
<NextMarker>data/futures/um/daily/klines/LUNAUSDT/</NextMarker>
<CommonPrefixes><Prefix>data/futures/um/daily/klines/BTCUSDT/</Prefix></CommonPrefixes>
<CommonPrefixes><Prefix>data/futures/um/daily/klines/LUNAUSDT/</Prefix></CommonPrefixes>
<Contents><Key>x/BTCUSDT-1m-2025-01-01.zip</Key></Contents>
<Contents><Key>x/BTCUSDT-1m-2025-01-01.zip.CHECKSUM</Key></Contents>
</ListBucketResult>"""


def test_parse_s3_listing_handles_namespace_and_pagination():
    keys, prefixes, truncated, nxt = collector.parse_s3_listing(SAMPLE)
    assert truncated is True
    assert nxt == "data/futures/um/daily/klines/LUNAUSDT/"
    assert len(prefixes) == 2 and prefixes[1].endswith("LUNAUSDT/")
    days = {m.group(1) for k in keys if (m := collector.DAY_RE.search(k))}
    assert days == {"2025-01-01"}  # CHECKSUM key ignored


def test_hl_mapping_including_k_prefix():
    avail = {"BTCUSDT", "1000PEPEUSDT", "1000BONKUSDT", "WIFUSDT"}
    assert collector.hl_to_binance("BTC", avail) == "BTCUSDT"
    assert collector.hl_to_binance("kPEPE", avail) == "1000PEPEUSDT"
    assert collector.hl_to_binance("BONK", avail) == "1000BONKUSDT"
    assert collector.hl_to_binance("HYPEX", avail) is None


def test_shards_partition_universe_exactly():
    symbols = [f"COIN{i}USDT" for i in range(500)]
    parts = [[s for s in symbols if collector.in_shard(s, i, 16)] for i in range(16)]
    flat = [s for p in parts for s in p]
    assert sorted(flat) == sorted(symbols) and len(flat) == len(set(flat))
    # stable when other symbols appear or disappear
    assert collector.in_shard("BTCUSDT", 3, 16) == collector.in_shard("BTCUSDT", 3, 16)


def test_merge_frames_never_drops_history():
    old = pd.DataFrame({"open_time": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True),
                        "c": [1.0, 2.0]})
    new = pd.DataFrame({"open_time": pd.to_datetime(["2026-01-02", "2026-01-03"], utc=True),
                        "c": [2.5, 3.0]})
    m = collector.merge_frames(old, new, "open_time")
    assert list(m["c"]) == [1.0, 2.5, 3.0]


def test_microsecond_timestamps_are_normalised():
    row = [1735689600000000, 1, 1, 1, 1, 10, 0, 10, 12, 7, 7, 0]
    x = collector.normalize_klines(pd.DataFrame([row], columns=collector.KLINE_FIELDS))
    assert x.iloc[0]["open_time"] == pd.Timestamp("2025-01-01", tz="UTC")
