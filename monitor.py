#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
X (Twitter) 账号监听 → Discord
使用 GitHub Actions + Nitter RSS，完全免费
"""

import os
import re
import json
import time
import feedparser
import requests
from pathlib import Path
from datetime import datetime, timezone
from typing import Set, List, Dict, Optional

# ==================== 配置区 ====================

# 要监听的账号（不加 @，最多建议 50 个）
ACCOUNTS = [
    "elonmusk",
    "OpenAI",
    "xai",
    # 继续添加你的账号...
]

# Nitter 实例列表（优先使用还支持 RSS 的）
# 可随时去 https://status.d420.de 查看最新可用实例并更新这里
NITTER_INSTANCES = [
    "https://nitter.meowing.monster",
    "https://nitter.kareem.one",
    "https://nitter.tiekoetter.com",
    "https://nitter.netbub.com",
    "https://nitter.jaydenha.uk",
]

# Discord Webhook（从环境变量读取，不要写死在代码里）
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "").strip()

# 已发送记录文件
SEEN_FILE = Path("seen.json")
MAX_SEEN_KEEP = 5000          # 最多保留多少条已读 ID

# 是否排除回复（True = 不推送以 @ 开头的回复）
EXCLUDE_REPLIES = True

# ==================== 工具函数 ====================

def load_seen() -> Set[str]:
    if SEEN_FILE.exists():
        try:
            data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            return set(data)
        except Exception as e:
            print(f"[警告] 读取 seen.json 失败: {e}")
    return set()


def save_seen(seen: Set[str]):
    # 只保留最近的记录，防止文件无限变大
    ordered = list(seen)[-MAX_SEEN_KEEP:]
    SEEN_FILE.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[信息] 已保存 {len(ordered)} 条已读记录")


def extract_tweet_id(link: str) -> Optional[str]:
    """从链接中提取推文 ID"""
    if not link:
        return None
    # 匹配 /status/数字
    m = re.search(r"/status/(\d+)", link)
    if m:
        return m.group(1)
    return None


def clean_nitter_link(link: str) -> str:
    """把 Nitter 链接转成正常 x.com 链接"""
    if not link:
        return link
    # 去掉实例域名，换成 x.com
    link = re.sub(r"https?://[^/]+/", "https://x.com/", link)
    # 去掉可能的 /rss 等后缀
    link = link.split("?")[0].split("#")[0]
    return link


def send_to_discord(username: str, title: str, link: str, content: str, published: Optional[str] = None):
    """发送美观的 Embed 到 Discord"""
    if not DISCORD_WEBHOOK:
        print("[错误] 未设置 DISCORD_WEBHOOK")
        return

    # 清理内容（去掉 HTML 标签）
    if content:
        content = re.sub(r"<[^>]+>", "", content)
        content = content.strip()

    embed = {
        "author": {
            "name": f"@{username}",
            "url": f"https://x.com/{username}"
        },
        "title": (title or "新推文")[:256],
        "url": link,
        "description": (content or "（无文字内容）")[:4000],
        "color": 0x1DA1F2,  # X 蓝色
        "footer": {
            "text": "X Monitor · GitHub Actions"
        }
    }

    if published:
        try:
            # 尝试转成 ISO 格式
            embed["timestamp"] = published
        except:
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
            print(f"  ❌ Discord 返回 {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"  ❌ 发送 Discord 异常: {e}")


def fetch_rss_entries(username: str) -> List[Dict]:
    """从多个 Nitter 实例尝试获取 RSS"""
    for base in NITTER_INSTANCES:
        rss_url = f"{base.rstrip('/')}/{username}/rss"
        try:
            print(f"  尝试 {rss_url}")
            feed = feedparser.parse(rss_url, request_headers={
                "User-Agent": "Mozilla/5.0 (compatible; X-Monitor/1.0)"
            })

            if feed.bozo and not feed.entries:
                print(f"    解析失败或无内容")
                continue

            if feed.entries:
                print(f"    成功获取 {len(feed.entries)} 条")
                return feed.entries
        except Exception as e:
            print(f"    请求失败: {e}")
            continue

    print(f"  所有实例均失败: @{username}")
    return []


# ==================== 主程序 ====================

def main():
    print("=" * 50)
    print(f"开始运行 X Monitor  {datetime.now(timezone.utc).isoformat()}")
    print(f"监听账号数量: {len(ACCOUNTS)}")
    print("=" * 50)

    if not DISCORD_WEBHOOK:
        print("❌ 错误：请在 GitHub Secrets 中设置 DISCORD_WEBHOOK")
        return

    if not ACCOUNTS:
        print("❌ 错误：ACCOUNTS 列表为空")
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

        # 从旧到新处理，避免乱序
        for entry in reversed(entries):
            link = entry.get("link") or entry.get("id") or ""
            tweet_id = extract_tweet_id(link)

            if not tweet_id:
                continue

            if tweet_id in seen:
                continue

            title = entry.get("title", "")
            content = entry.get("summary") or entry.get("description") or ""
            published = entry.get("published") or entry.get("updated")

            # 简单过滤回复
            if EXCLUDE_REPLIES and (title.startswith("@") or content.strip().startswith("@")):
                print(f"  跳过回复: {tweet_id}")
                seen.add(tweet_id)  # 也记录下来，避免反复检查
                continue

            clean_link = clean_nitter_link(link)
            send_to_discord(username, title, clean_link, content, published)
            seen.add(tweet_id)
            new_count += 1

            # 避免 Discord 限流
            time.sleep(1.2)

    save_seen(seen)
    print("\n" + "=" * 50)
    print(f"本轮完成，新推送 {new_count} 条")
    print("=" * 50)


if __name__ == "__main__":
    main()
