"""週書單 JSON 快取：唯一寫入點 / 讀取點。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .parser import WeeklyPost

TZ = ZoneInfo("Asia/Taipei")
DATA_DIR = Path("/app/data")


@dataclass
class WeeklySnapshot:
    """JSON 檔的完整內容：metadata + WeeklyPost。"""
    week: str            # "2026-w26"
    url: str
    fetched_at: str      # ISO timestamp, Asia/Taipei
    post: WeeklyPost


def _path(label: str) -> Path:
    return DATA_DIR / f"{label}.json"


def save(label: str, url: str, post: WeeklyPost) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(label)
    data = {
        "week": label,
        "url": url,
        "fetched_at": datetime.now(TZ).isoformat(timespec="seconds"),
        **post.to_dict(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load(label: str) -> WeeklySnapshot | None:
    path = _path(label)
    if not path.exists():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    return WeeklySnapshot(
        week=d["week"],
        url=d["url"],
        fetched_at=d["fetched_at"],
        post=WeeklyPost.from_dict(d),
    )
