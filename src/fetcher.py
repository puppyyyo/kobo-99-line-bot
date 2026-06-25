"""用 Playwright 抓 Kobo 週週 99 元頁面，繞過 anti-bot challenge。"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

log = logging.getLogger(__name__)

# Kobo 的網址用不補零的週數：...-w1 而不是 ...-w01
URL_TEMPLATE = "https://www.kobo.com/zh/blog/weekly-dd99-{year}-w{week}"


def current_iso_week(today: date | None = None) -> tuple[int, int]:
    today = today or date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return iso_year, iso_week


def previous_iso_week(today: date | None = None) -> tuple[int, int]:
    today = today or date.today()
    last = today - timedelta(days=7)
    iso_year, iso_week, _ = last.isocalendar()
    return iso_year, iso_week


def build_url(year: int, week: int) -> str:
    return URL_TEMPLATE.format(year=year, week=week)


def fetch_html(url: str, timeout_ms: int = 30000) -> str:
    """回傳完整 HTML。若遇到 Cloudflare challenge 會等它過。"""
    log.info("fetching %s", url)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="zh-TW",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # challenge 通常 3-5 秒解掉；等到 article 內 h1 出現代表 hydration 完成
        try:
            page.wait_for_selector("article h1, main h1", timeout=timeout_ms)
        except Exception:
            log.warning("h1 not found within timeout, returning whatever we got")
        # 多等一下確保 img.audiobook 也都注入
        try:
            page.wait_for_selector("img.audiobook", timeout=5000)
        except Exception:
            log.warning("img.audiobook not seen within 5s")
        html = page.content()
        browser.close()
    return html
