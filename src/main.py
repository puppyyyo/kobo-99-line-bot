"""入口：常駐 + APScheduler 每週觸發 + 啟動立即跑一次。"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from . import storage
from .fetcher import build_url, current_iso_week, fetch_html, previous_iso_week
from .notifier import push_books, push_error, push_today_book
from .parser import parse_post

TZ = ZoneInfo("Asia/Taipei")
LOG_DIR = Path("/app/logs")
LAST_SENT_FILE = storage.DATA_DIR / "last_sent.txt"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    handler.setFormatter(fmt)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[handler, stream])


log = logging.getLogger("main")


def week_label() -> str:
    y, w = current_iso_week()
    return f"{y}-w{w:02d}"


def already_sent(label: str) -> bool:
    if not LAST_SENT_FILE.exists():
        return False
    return LAST_SENT_FILE.read_text(encoding="utf-8").strip() == label


def mark_sent(label: str) -> None:
    LAST_SENT_FILE.write_text(label, encoding="utf-8")


def refresh_weekly() -> str | None:
    """抓 Kobo → 解析 → 寫 JSON 快取。回傳 label，全部失敗回 None（已自行 push_error）。"""
    # 先試本週，失敗就 fallback 上週（Kobo 通常週四才上稿）
    candidates = [current_iso_week(), previous_iso_week()]
    url = ""
    last_err: str = ""
    for y, w in candidates:
        url = build_url(y, w)
        try:
            html = fetch_html(url)
        except Exception as e:
            log.warning("fetch failed for %s: %s", url, e)
            last_err = str(e)
            continue
        post = parse_post(html)
        if post.books:
            label = f"{y}-w{w:02d}"
            path = storage.save(label, url, post)
            log.info("saved weekly json: %s (%d books)", path, len(post.books))
            return label
        log.info("no books on %s, try previous week", url)

    push_error(f"本週/上週都抓不到 99 書單。最後一個 URL: {url}\n錯誤: {last_err}")
    return None


def publish_weekly(label: str) -> None:
    """讀 JSON 快取 → 推 LINE → 標記已推。"""
    snap = storage.load(label)
    if snap is None:
        push_error(f"找不到 {label} 的 JSON 快取，無法推播。")
        return
    if not snap.post.books:
        log.warning("no books in snapshot %s", label)
        push_error(f"快取 {label} 沒有任何書。\nURL: {snap.url}")
        return

    header = snap.post.title or f"Kobo {label} 99 元電子書"
    try:
        push_books(snap.post.books, header_text=header, blog_url=snap.url)
        mark_sent(label)
    except Exception as e:
        log.exception("push failed")
        push_error(f"LINE 推播失敗 ({label}): {e}")


def run_once(force: bool = False) -> None:
    label = week_label()
    if not force and already_sent(label):
        log.info("week %s already sent, skip", label)
        return

    new_label = refresh_weekly()
    if new_label is None:
        return
    publish_weekly(new_label)


def push_today() -> None:
    """每日 09:00：找今天日期對應的書，推單本 Flex bubble。找不到就跳過不推。"""
    today_iso = date.today().isoformat()
    label = week_label()
    snap = storage.load(label)
    if snap is None:
        log.info("today=%s: no cache for %s, refreshing", today_iso, label)
        new_label = refresh_weekly()
        if new_label is None:
            log.warning("today=%s: refresh failed, skip", today_iso)
            return
        snap = storage.load(new_label)
        if snap is None:
            log.warning("today=%s: still no cache after refresh, skip", today_iso)
            return

    today_book = next(
        (b for b in snap.post.books if b.sale_date_iso == today_iso),
        None,
    )
    if today_book is None:
        log.info("today=%s: no book today in %s, skip", today_iso, snap.week)
        return

    try:
        push_today_book(today_book)
    except Exception as e:
        log.exception("daily push failed")
        push_error(f"每日推播失敗 ({today_iso}): {e}")


def main() -> None:
    load_dotenv()
    setup_logging()

    for key in ("LINE_CHANNEL_TOKEN", "LINE_USER_ID"):
        if not os.environ.get(key):
            log.error("missing env %s, exiting", key)
            sys.exit(1)

    if os.environ.get("RUN_ON_STARTUP", "true").lower() == "true":
        log.info("RUN_ON_STARTUP=true, running once now (will skip if this week already sent)")
        run_once(force=False)

    day = os.environ.get("SCHEDULE_DAY", "wed")
    hour = int(os.environ.get("SCHEDULE_HOUR", "19"))
    minute = int(os.environ.get("SCHEDULE_MINUTE", "0"))
    daily_hour = int(os.environ.get("DAILY_HOUR", "12"))
    daily_minute = int(os.environ.get("DAILY_MINUTE", "0"))

    scheduler = BlockingScheduler(timezone=TZ)
    scheduler.add_job(
        run_once,
        CronTrigger(day_of_week=day, hour=hour, minute=minute, timezone=TZ),
        name="weekly-kobo",
    )
    scheduler.add_job(
        push_today,
        CronTrigger(hour=daily_hour, minute=daily_minute, timezone=TZ),
        name="daily-kobo",
    )
    log.info(
        "scheduler: weekly=%s %02d:%02d, daily=%02d:%02d Asia/Taipei",
        day, hour, minute, daily_hour, daily_minute,
    )
    scheduler.start()


if __name__ == "__main__":
    main()
