#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X (Twitter) 账号监听 → Discord
正式版：只推送新推文，不刷历史
"""

import os
import re
import json
import time
import feedparser
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Set, List, Optional
from email.utils import parsedate_to_datetime

# ==================== 配置区 ====================

ACCOUNTS = [
    "eloscapeHQ",
    "kalosfun",
    "ChainzyLabs",
    "SignalFam",
    # 继续添加账号...
]

NITTER_INSTANCES = [
    "https://nitter.meowing.monster",
    "https://nitter.kareem.one",
    "https://nitter.tiekoetter.com",
    "https://nitter.netbub.com",
    "https://nitter.jaydenha.uk",
]

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "").strip()

SEEN_FILE = Path("seen.json")
MAX_SEEN_KEEP = 5000
EXCLUDE_REPLIES = True

# ==================== 工具函数 ====================

def load_seen() -> Set[str]:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[警告] 读取 seen.json 失败: {e}")
    return set()


def save_seen(seen: Set[str]):
    ordered = list(seen)[-MAX_SEEN_KEEP:]
    SEEN_FILE.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[信息] 已保存 {len(ordered)} 条已读记录")


def extract_tweet_id(link: str) -> Optional[str]:
    if not link:
        return None
    m = re.search(r"/status/(\d+)", link)
    return m.group(1) if m else None


def clean_nitter_link(link: str) -> str:
    if not link:
        return link
    link = re.sub(r"https?://[^/]+/", "https://x.com/", link)
    return link.split("?")[0].split("#")[0]


def send_to_discord(username: str, title: str, link: str, content: str, published: Optional[str] = None):
    if not DISCORD_WEBHOOK:
        print("[错误] 未设置 DISCORD_WEBHOOK")
        return

    if content:
        content = re.sub(r"<[^>]+>", "", content)
        content = (content.replace("&amp;", "&").replace("&lt;", "<")
                   .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'").strip())
    else:
        content = ""

    title = (title or "新推文").strip()[:256] or "新推文"
    description = (content[:4000] if content else "（无文字内容）") or "（无文字内容）"

    embed = {
        "author": {"name": f"@{username}", "url": f"https://x.com/{username}"},
        "title": title,
        "url": link,
        "description": description,
        "color": 1942002,
        "footer": {"text": "X Monitor · GitHub Actions"}
    }

    if published:
        try:
            dt = parsedate_to_datetime(published)
            embed["timestamp"] = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            pass

    payload = {
        "username": "X 监听机器人",
        "avatar_url": "https://abs.twimg.com/icons/apple-touch-icon-192x192.png",
        "embeds": [embed]
    }

    try:
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=20)
        if resp.status_code in (200, 204):
            print(f"  ✅ 已推送: {link}")
        else:
            print(f"  ❌ Discord 返回 {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        print(f"  ❌ 发送异常: {e}")


def fetch_rss_entries(username: str) -> List:
    for base in NITTER_INSTANCES:
        rss_url = f"{base.rstrip('/')}/{username}/rss"
        try:
            print(f"  尝试 {rss_url}")
            feed = feedparser.parse(rss_url, request_headers={"User-Agent": "Mozilla/5.0 (compatible; X-Monitor/1.0)"})
            if feed.entries:
                print(f"    成功获取 {len(feed.entries)} 条")
                return feed.entries
        except Exception as e:
            print(f"    失败: {e}")
    print(f"  所有实例均失败: @{username}")
    return []


# ==================== 主程序 ====================

def main():
    print("=" * 55)
    print(f"开始运行 X Monitor  {datetime.now(timezone.utc).isoformat()}")
    print(f"监听账号数量: {len(ACCOUNTS)}")
    print("=" * 55)

    if not DISCORD_WEBHOOK:
        print("❌ 错误：请设置 DISCORD_WEBHOOK")
        return
    if not ACCOUNTS:
        print("❌ 错误：ACCOUNTS 为空")
        return

    seen = load_seen()
    print(f"当前已记录推文数: {len(seen)}")

    new_count = 0

    for username in ACCOUNTS:
        username = username.strip().lstrip("@")
        if not username:
            continue

        print(f"\n检查 @{username} ...")
        entries = fetch_rss_entries(username)

        for entry in reversed(entries):
            link = entry.get("link") or entry.get("id") or ""
            tweet_id = extract_tweet_id(link)

            if not tweet_id or tweet_id in seen:
                continue

            title = entry.get("title", "")
            content = entry.get("summary") or entry.get("description") or ""
            published = entry.get("published") or entry.get("updated")

            if EXCLUDE_REPLIES:
                text_check = (title + " " + content).strip()
                if text_check.startswith("@"):
                    print(f"  跳过回复: {tweet_id}")
                    seen.add(tweet_id)
                    continue

            clean_link = clean_nitter_link(link)
            send_to_discord(username, title, clean_link, content, published)
            seen.add(tweet_id)
            new_count += 1
            time.sleep(1.5)

    save_seen(seen)

    print("\n" + "=" * 55)
    print(f"本轮完成，新推送 {new_count} 条")
    print("=" * 55)


if __name__ == "__main__":
    main()
