"""LINE Messaging API push: Flex Carousel + 純文字錯誤通知。"""
from __future__ import annotations

import logging
import os
import re

import requests

from .parser import Book

# 抓最外層的 《...》 當主標題；其後（含其他括號）為副標題
TITLE_SPLIT_RE = re.compile(r"^\s*(《[^》]+》)\s*(.*)$")

log = logging.getLogger(__name__)

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
# LINE Flex Carousel 一次最多 12 個 bubble
MAX_BUBBLES = 12
# 圖片必須 https
PLACEHOLDER_COVER = "https://via.placeholder.com/240x320?text=No+Cover"


def _headers() -> dict[str, str]:
    token = os.environ["LINE_CHANNEL_TOKEN"]
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }


def _user_id() -> str:
    return os.environ["LINE_USER_ID"]


def _bubble(book: Book) -> dict:
    cover = book.cover or PLACEHOLDER_COVER
    if cover.startswith("//"):
        cover = "https:" + cover
    elif cover.startswith("http://"):
        cover = "https://" + cover[len("http://") :]

    body_contents: list[dict] = []
    if book.sale_date:
        body_contents.append(
            {
                "type": "text",
                "text": f"{book.sale_date}",
                "size": "lg",
                "color": "#1F8E3D",
                "weight": "bold",
            }
        )
    m = TITLE_SPLIT_RE.match(book.title)
    if m and m.group(2):
        main_title, sub_title = m.group(1), m.group(2).strip()
    else:
        main_title, sub_title = book.title, ""

    body_contents.append(
        {
            "type": "text",
            "text": main_title,
            "weight": "bold",
            "size": "md",
            "wrap": False,
            "maxLines": 1,
            "margin": "md",
        }
    )
    if sub_title:
        body_contents.append(
            {
                "type": "text",
                "text": sub_title,
                "size": "sm",
                "color": "#555555",
                "wrap": False,
                "maxLines": 1,
                "margin": "xs",
            }
        )
    if book.author:
        body_contents.append(
            {
                "type": "text",
                "text": book.author[:40],
                "size": "xs",
                "color": "#888888",
                "wrap": True,
                "maxLines": 1,
                "margin": "sm",
            }
        )
    if book.publisher:
        body_contents.append(
            {
                "type": "text",
                "text": book.publisher[:40],
                "size": "xs",
                "color": "#888888",
                "wrap": True,
                "maxLines": 1,
                "margin": "xs",
            }
        )

    return {
        "type": "bubble",
        "size": "kilo",
        "action": {
            "type": "uri",
            "label": "去 Kobo 看看",
            "uri": book.url,
        },
        "hero": {
            "type": "image",
            "url": cover,
            "size": "full",
            "aspectRatio": "3:4",
            "aspectMode": "fit",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": body_contents,
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#1F8E3D",
                    "action": {
                        "type": "uri",
                        "label": "去 Kobo 看看",
                        "uri": book.url,
                    },
                }
            ],
        },
    }


def push_books(books: list[Book], header_text: str) -> None:
    """header_text 為部落格 h1 標題，會作為第一則純文字訊息。"""
    if not books:
        log.warning("push_books called with empty list")
        return

    bubbles = [_bubble(b) for b in books[:MAX_BUBBLES]]
    if len(books) > MAX_BUBBLES:
        header_text = f"{header_text}\n（共 {len(books)} 本，顯示前 {MAX_BUBBLES} 本）"

    payload = {
        "to": _user_id(),
        "messages": [
            {"type": "text", "text": header_text},
            {
                "type": "flex",
                "altText": header_text[:400],
                "contents": {"type": "carousel", "contents": bubbles},
            },
        ],
    }
    r = requests.post(LINE_PUSH_URL, headers=_headers(), json=payload, timeout=15)
    if r.status_code >= 300:
        log.error("LINE push failed %s: %s", r.status_code, r.text)
        r.raise_for_status()
    log.info("LINE push ok, %d books", len(books))


def push_error(message: str) -> None:
    try:
        payload = {
            "to": _user_id(),
            "messages": [{"type": "text", "text": f"⚠️ Kobo Bot 失敗\n{message}"}],
        }
        r = requests.post(LINE_PUSH_URL, headers=_headers(), json=payload, timeout=15)
        if r.status_code >= 300:
            log.error("error-notify also failed %s: %s", r.status_code, r.text)
    except Exception:
        log.exception("push_error itself raised")
