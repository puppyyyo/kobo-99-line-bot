"""批次抓取歷史週次，存成 data/{year}-w{week}.json。不推 LINE。

用法（容器內）：
    docker compose run --rm bot python -m src.backfill 2026 1 25
        → 抓 2026 年第 1~25 週

選項：
    --force   即使 JSON 已存在也重抓
    --sleep N 每週之間 sleep N 秒（預設 3）
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from . import storage
from .fetcher import build_url, fetch_html
from .parser import parse_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("backfill")


def backfill_one(year: int, week: int, force: bool) -> str:
    """回傳狀態字串：'skip' | 'ok:N' | 'empty' | 'error:msg'"""
    label = f"{year}-w{week:02d}"
    if not force and storage.load(label) is not None:
        log.info("[%s] skip (already exists)", label)
        return "skip"
    url = build_url(year, week)
    try:
        html = fetch_html(url)
    except Exception as e:
        log.warning("[%s] fetch failed: %s", label, e)
        return f"error:{e}"
    post = parse_post(html)
    if not post.books:
        log.warning("[%s] no books parsed (URL maybe 404 or empty page)", label)
        return "empty"
    storage.save(label, url, post)
    log.info("[%s] saved %d books", label, len(post.books))
    return f"ok:{len(post.books)}"


def main() -> None:
    ap = argparse.ArgumentParser(description="批次抓 Kobo 週 99 書單存 JSON")
    ap.add_argument("year", type=int, help="ISO year, e.g. 2026")
    ap.add_argument("start_week", type=int, help="起始週 (1-53)")
    ap.add_argument("end_week", type=int, help="結束週 (含)")
    ap.add_argument("--force", action="store_true", help="已存在的也重抓")
    ap.add_argument("--sleep", type=float, default=3.0, help="每週之間 sleep 秒數")
    args = ap.parse_args()

    if not (1 <= args.start_week <= args.end_week <= 53):
        ap.error("週數要在 1~53 且 start <= end")

    weeks = list(range(args.start_week, args.end_week + 1))
    log.info(
        "backfill %d-w%02d ~ %d-w%02d (%d 週), force=%s, sleep=%.1fs",
        args.year, weeks[0], args.year, weeks[-1], len(weeks), args.force, args.sleep,
    )

    results: dict[str, str] = {}
    for i, w in enumerate(weeks):
        label = f"{args.year}-w{w:02d}"
        results[label] = backfill_one(args.year, w, args.force)
        if i < len(weeks) - 1 and not results[label].startswith("skip"):
            time.sleep(args.sleep)

    ok = [k for k, v in results.items() if v.startswith("ok")]
    skip = [k for k, v in results.items() if v == "skip"]
    empty = [k for k, v in results.items() if v == "empty"]
    err = [k for k, v in results.items() if v.startswith("error")]
    log.info("=" * 50)
    log.info("summary: ok=%d, skip=%d, empty=%d, error=%d", len(ok), len(skip), len(empty), len(err))
    if empty:
        log.info("empty: %s", ", ".join(empty))
    if err:
        log.info("error: %s", ", ".join(err))


if __name__ == "__main__":
    main()
