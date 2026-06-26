# Kobo 一週 99 書單 → LINE Bot

每週三晚上推當週「一週 99 書單」、每天早上推當日特價書到你的 LINE，免得錯過 99 元電子書。

資料來源：<https://www.kobo.com/zh/blog/weekly-dd99-2026-wXX>（網址結尾 `wXX` 為 ISO 週數）

## Quick Start

### 1. 申請 LINE Bot

到 https://developers.line.biz/console/

→ **Create a new provider**

→ **Create a Messaging API channel**，然後拿兩個東西：

| 要的東西 | 在哪 |
|---|---|
| **Channel access token (long-lived)** | 「Messaging API」分頁最下面，點 **Issue** |
| **Your user ID**（U 開頭） | 「Basic settings」分頁最下面 |

> ⚠ 用手機 LINE **加 bot 為好友**（QR code 在「Messaging API」分頁上方），不加好友收不到通知。

### 2. 設定

```bash
cp .env.example .env
# 編輯 .env，填入 LINE_CHANNEL_TOKEN 與 LINE_USER_ID
```

### 3. 啟動

```bash
docker compose up -d --build
```

啟動後會立刻推一次測試訊息到你 LINE。之後：
- **每週三 19:00**（台北時間）推當週完整書單
- **每天 12:00** 推當日 99 元特價書（當天沒對應書就不推）

## 常用指令

```bash
docker compose logs -f bot                              # 看 log
rm -f data/last_sent.txt && docker compose restart bot  # 再推一次
docker compose up -d                                    # 改 .env 後套用（recreate 容器）
docker compose down                                     # 停掉
```

> 改 `.env` 後用 `docker compose up -d` 會 recreate 容器讀新 .env，
> 不要用 `restart` 只會重啟 process，不會重讀 .env。
