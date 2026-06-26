"""解析 Kobo「一週 99 書單」部落格頁面。

URL pattern: https://www.kobo.com/zh/blog/weekly-dd99-<year>-w<week>

頁面結構（部落格 CMS 提供穩定 class）：
  - <h1>: 「【一週99書單】... （M/D-M/D）」整週區間
  - <div class="book-block"> × N：每本書一個區塊，內含：
      span.title       — 書名（含書名號）
      span.author      — 作者（「由 XXX@著」）
      a (no class)     — 第一個是出版社（純文字）
      a.book-block__link — TW 商品連結
      img              — 封面
  - <div class="content-block"> × (N+1)：第 0 是前言，第 i+1 對應 book-block #i，
    含「M/D 週X Kobo99選書:《書名》介紹文」
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field

from bs4 import BeautifulSoup, Tag

log = logging.getLogger(__name__)

DATE_RANGE_RE = re.compile(r"(\d{1,2}/\d{1,2}\s*[-~–]\s*\d{1,2}/\d{1,2})")
# 「6/18 週四 Kobo99選書:」
SALE_DATE_RE = re.compile(r"(\d{1,2}/\d{1,2})\s*(週[一二三四五六日])?\s*Kobo99選書")
# 「由 Kobo • 六月 17, 2026」
PUBLISH_DATE_RE = re.compile(r"(一|二|三|四|五|六|七|八|九|十|十一|十二)月\s*(\d{1,2}),\s*(\d{4})")
_CN_MONTH = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
    "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
}


@dataclass
class Book:
    title: str
    url: str
    cover: str | None = None
    author: str | None = None
    publisher: str | None = None
    sale_date: str | None = None         # 例如 "6/18 週四"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Book":
        return cls(
            title=d["title"],
            url=d["url"],
            cover=d.get("cover"),
            author=d.get("author"),
            publisher=d.get("publisher"),
            sale_date=d.get("sale_date"),
        )


@dataclass
class WeeklyPost:
    title: str
    date_range: str | None
    publish_date: str | None = None      # ISO date, e.g. "2026-06-17"
    books: list[Book] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "date_range": self.date_range,
            "publish_date": self.publish_date,
            "books": [b.to_dict() for b in self.books],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WeeklyPost":
        return cls(
            title=d["title"],
            date_range=d.get("date_range"),
            publish_date=d.get("publish_date"),
            books=[Book.from_dict(b) for b in d.get("books", [])],
        )


def _abs_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return "https://www.kobo.com" + href


def _normalize_cover(src: str | None) -> str | None:
    if not src:
        return None
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("http://"):
        return "https://" + src[len("http://") :]
    return src


def _clean_author(s: str) -> str:
    """『由 XXX@著』→『XXX』"""
    s = s.strip()
    s = re.sub(r"^由\s*", "", s)
    s = re.sub(r"[@＠]著\s*$", "", s)
    return s.strip()


def _extract_title_and_date(soup: BeautifulSoup) -> tuple[str, str | None]:
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""
    m = DATE_RANGE_RE.search(title)
    date_range = m.group(1).replace(" ", "") if m else None
    return title, date_range


def _extract_publish_date(soup: BeautifulSoup) -> str | None:
    """從 <p class="meta">「由 Kobo • 六月 17, 2026」抽出 ISO 日期。"""
    meta = soup.find("p", class_="meta")
    if not meta:
        return None
    m = PUBLISH_DATE_RE.search(meta.get_text(" ", strip=True))
    if not m:
        return None
    month = _CN_MONTH.get(m.group(1))
    if not month:
        return None
    return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"


def _parse_sale_date(content_block: Tag | None) -> str | None:
    if content_block is None:
        return None
    text = content_block.get_text(" ", strip=True)
    m = SALE_DATE_RE.search(text)
    if not m:
        return None
    date = m.group(1)
    weekday = m.group(2) or ""
    return f"{date} {weekday}".strip()


def _parse_book_block(bb: Tag, sale_date: str | None) -> Book | None:
    title_el = bb.find(class_="title")
    link_el = bb.find("a", class_="book-block__link")
    if not title_el or not link_el:
        return None
    book_title = title_el.get_text(strip=True)
    url = _abs_url(link_el.get("href", ""))
    if not book_title or not url:
        return None

    author_el = bb.find(class_="author")
    author = _clean_author(author_el.get_text(strip=True)) if author_el else None

    # 出版社：book-block 內 href 指向 Kobo search、文字非「查看電子書」的 a
    publisher: str | None = None
    for a in bb.find_all("a"):
        classes = a.get("class") or []
        if "book-block__link" in classes or "book-block__img" in classes:
            continue
        href = a.get("href", "")
        if "/ebook/" in href:  # HK / TW 商品連結都排除
            continue
        text = a.get_text(strip=True)
        if text and "查看電子書" not in text:
            publisher = text
            break

    img = bb.find("img")
    cover = _normalize_cover(img.get("src") if img else None)

    return Book(
        title=book_title,
        url=url,
        cover=cover,
        author=author,
        publisher=publisher,
        sale_date=sale_date,
    )


def parse_post(html: str) -> WeeklyPost:
    soup = BeautifulSoup(html, "html.parser")
    post_title, date_range = _extract_title_and_date(soup)
    publish_date = _extract_publish_date(soup)

    book_blocks = soup.find_all(class_="book-block")
    content_blocks = soup.find_all(class_="content-block")

    # content-block[0] 是前言；content-block[i+1] 對應 book-block[i]
    sale_dates: list[str | None] = []
    for i in range(len(book_blocks)):
        cb = content_blocks[i + 1] if i + 1 < len(content_blocks) else None
        sale_dates.append(_parse_sale_date(cb))

    books: list[Book] = []
    for bb, sd in zip(book_blocks, sale_dates):
        b = _parse_book_block(bb, sd)
        if b:
            books.append(b)

    log.info(
        "parsed: title=%r range=%s publish_date=%s, %d books",
        post_title, date_range, publish_date, len(books),
    )
    return WeeklyPost(
        title=post_title,
        date_range=date_range,
        publish_date=publish_date,
        books=books,
    )
