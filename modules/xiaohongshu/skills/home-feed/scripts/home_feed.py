#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKSPACE_ROOT = Path(os.environ.get("GROWTH_SYMPHONY_HOME", "/Users/admin/growth-symphony")).resolve()
WORKSPACE_ROOT = DEFAULT_WORKSPACE_ROOT if (DEFAULT_WORKSPACE_ROOT / "modules" / "xiaohongshu").exists() else SCRIPT_DIR.parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT / "modules" / "xiaohongshu" / "lib"))

import xhs_signal as xs
import xhs_browser as xb


def main():
    args = parse_args()
    if not args.cdp_endpoint:
        raise SystemExit("缺少 BROWSER_CDP_ENDPOINT。先从已打开的浏览器 profile 取得 CDP endpoint。")

    run_dir = Path(args.out_dir).resolve() if args.out_dir else (
        WORKSPACE_ROOT / "runs" / "xiaohongshu" / "home-feed" / xb.timestamp()
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.screenshot:
        (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)

    feed_path = run_dir / "feed.json"
    agent_input_path = run_dir / "agent_input.json"
    summary_path = run_dir / "summary.md"
    feishu_rows_path = run_dir / "feishu_rows.json"

    feed = run_browser(args, run_dir)
    xb.write_json(feed_path, feed)
    xb.write_json(agent_input_path, build_agent_input(feed))
    xb.write_json(feishu_rows_path, build_feishu_rows(feed, run_dir))
    summary_path.write_text(render_summary(feed), encoding="utf-8")

    print(json.dumps({
        "runDir": str(run_dir),
        "feedPath": str(feed_path),
        "agentInputPath": str(agent_input_path),
        "summaryPath": str(summary_path),
        "feishuRowsPath": str(feishu_rows_path),
        "cards": len(feed["cards"]),
        "details": len(feed["details"]),
    }, ensure_ascii=False, indent=2))


def run_browser(args, run_dir):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("缺少 Python playwright 依赖。执行：python3 -m pip install -r requirements.txt") from exc

    created_pages = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp_endpoint)
        context = browser.contexts[0] if browser.contexts else None
        if context is None:
            raise RuntimeError("CDP 浏览器没有可用 context。")

        try:
            page = context.new_page()
            created_pages.append(page)
            page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            page.wait_for_timeout(args.settle_ms)
            for _ in range(args.scroll_pages):
                page.mouse.wheel(0, 1400)
                page.wait_for_timeout(args.scroll_delay_ms)
            if args.screenshot:
                page.screenshot(path=str(run_dir / "screenshots" / "home-feed.png"), full_page=False)

            cards = extract_cards(page, args.limit)
            details = []
            for card in cards[:args.detail_limit]:
                detail_page = context.new_page()
                created_pages.append(detail_page)
                try:
                    detail_page.goto(card["url"], wait_until="domcontentloaded", timeout=args.timeout_ms)
                    detail_page.wait_for_timeout(args.settle_ms)
                    details.append(extract_detail(detail_page, card))
                except Exception as exc:
                    details.append({"source_card": card, "error": str(exc)})
                finally:
                    xb.close_page(detail_page)
                page.wait_for_timeout(args.detail_delay_ms)

            return {
                "feed_url": args.url,
                "final_url": page.url,
                "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "limits": {"cards": args.limit, "details": args.detail_limit},
                "cards": cards,
                "details": details,
            }
        finally:
            for page in reversed(created_pages):
                xb.close_page(page)


def extract_cards(page, limit):
    return xb.extract_note_cards(page, limit)


def extract_detail(page, source_card):
    return xb.extract_note_detail(page, source_card, comment_limit=10, tag_limit=16, body_limit=1600, page_text_limit=2200)


def build_agent_input(feed):
    return {
        "schema_version": "xhs.home_feed.agent_input.v1",
        "task": "基于小红书首页推荐流样本做推荐流画像、可复用模式和选题判断",
        "analysis_owner": "agent_llm",
        "script_role": "browser_evidence_collector",
        "rules": [
            "只基于浏览器可见证据分析",
            "不要把当前账号首页推荐流写成全平台趋势",
            "先描述看到了什么，再判断可能推荐原因和可复用模式",
        ],
        "feed_url": feed.get("feed_url", ""),
        "final_url": feed.get("final_url", ""),
        "captured_at": feed.get("captured_at", ""),
        "cards": [
            {
                "rank": card.get("index"),
                "title": card.get("title", ""),
                "url": card.get("url", ""),
                "signals": card.get("signals", []),
                "metrics_hint": card.get("metrics_hint", {}),
                "metric_numbers": card.get("metric_numbers", {}),
                "engagement_ratios": card.get("engagement_ratios", {}),
                "hook_analysis": card.get("hook_analysis", {}),
                "content_form": card.get("content_form", ""),
                "visible_text": card.get("visible_text", ""),
            }
            for card in feed.get("cards", [])
        ],
        "details": [
            compact_detail(detail, index)
            for index, detail in enumerate(feed.get("details", []), start=1)
        ],
    }


def compact_detail(detail, index):
    if detail.get("error"):
        return {
            "rank": index,
            "source_title": detail.get("source_card", {}).get("title", ""),
            "url": detail.get("source_card", {}).get("url", ""),
            "error": detail.get("error", ""),
        }
    return {
        "rank": index,
        "source_title": detail.get("source_card", {}).get("title", ""),
        "title": detail.get("title", ""),
        "url": detail.get("url", ""),
        "author": detail.get("author", {}),
        "access_status": detail.get("access_status", ""),
        "signals": detail.get("signals", []),
        "hook_analysis": detail.get("hook_analysis", {}),
        "content_structure": detail.get("content_structure", {}),
        "comment_patterns": detail.get("comment_patterns", {}),
        "metrics_hint": detail.get("metrics_hint", {}),
        "engagement_ratios": detail.get("engagement_ratios", {}),
        "content_form": detail.get("content_form", ""),
        "tags": detail.get("tags", []),
        "body_excerpt": detail.get("body_excerpt", "")[:900],
        "comments": (detail.get("comments") or [])[:8],
    }


def build_feishu_rows(feed, run_dir):
    run_id = Path(run_dir).name
    run_row = {
        "run_id": run_id,
        "平台": "小红书",
        "关键词": "首页推荐流",
        "采集时间": feed["captured_at"],
        "样本数": len(feed["cards"]),
        "详情数": len(feed["details"]),
        "热点类型": "",
        "机会等级": "",
        "主导钩子": "",
        "内容形态": "",
        "一句话结论": "",
        "本地结果路径": str(run_dir),
    }
    evidence_rows = []
    for card in feed["cards"]:
        evidence_rows.append({
            "run_id": run_id,
            "排名": card.get("index"),
            "标题": card.get("title", ""),
            "URL": card.get("url", ""),
            "可见互动": xs.metrics_text(card.get("metrics_hint", {})),
            "信号标签": "、".join(card.get("signals", [])),
            "推荐理由": "",
            "选题方向": "",
            "是否已深入分析": False,
            "备注": card.get("visible_text", "")[:180],
        })
    return {
        "schema_version": "xhs.home_feed.feishu_rows.v1",
        "tables": {
            "分析任务表": [run_row],
            "样本证据表": evidence_rows,
        },
    }


def render_summary(feed):
    card_rows = "\n".join(
        f"| {card.get('index')} | {escape_cell(card.get('title', ''))} | "
        f"{escape_cell(card.get('content_form', '') or '不可见')} | "
        f"{escape_cell(' / '.join(card.get('signals', [])) or '未识别')} | "
        f"{escape_cell(xs.metrics_text(card.get('metrics_hint', {})) or '不可见')} |"
        for card in feed["cards"]
    )
    detail_rows = "\n".join(
        f"| {index + 1} | {escape_cell(detail.get('title') or detail.get('source_card', {}).get('title', ''))} | "
        f"{escape_cell(' / '.join((detail.get('comment_patterns') or {}).get('question_examples', [])[:2]))} |"
        for index, detail in enumerate(feed["details"])
    )
    return f"""# 小红书首页推荐流采集

## 运行信息

- 首页 URL：{feed.get("final_url") or feed.get("feed_url")}
- 采集时间：{feed["captured_at"]}
- 卡片数：{len(feed["cards"])}
- 详情页数：{len(feed["details"])}

## 推荐流样本

| # | 标题 | 形态 | 信号 | 可见互动 |
| ---: | --- | --- | --- | --- |
{card_rows or "| - | 未采集到首页卡片 | - | - | - |"}

## 深入详情

| # | 标题 | 评论问题样本 |
| ---: | --- | --- |
{detail_rows or "| - | 未采集详情页 | - |"}

## Agent 分析入口

- Python 只采集首页推荐流可见事实和浅层信号。
- 推荐流画像、可复用模式、账号适配和选题方向由 agent 读取 `agent_input.json` 后生成。
- 当前首页受浏览器登录态和历史兴趣影响，不代表全平台趋势。
"""


def card_root(anchor):
    root = anchor.locator("xpath=ancestor-or-self::*[self::section or self::article or self::li or self::div][1]")
    try:
        if root.count() > 0:
            return root.first
    except Exception:
        pass
    return anchor


def extract_card_title(root, anchor, text):
    title = first_text_from(root.locator('[class*="title"], [class*="desc"], h3, h2'))
    if title:
        return title
    title_attr = normalize_text(safe_attr(anchor, "title"))
    if title_attr:
        return title_attr
    return text[:80]


def first_image_url(root, base_url):
    for image in root.locator("img").all()[:3]:
        src = safe_attr(image, "src")
        if src:
            return urljoin(base_url, src)
    return None


def close_page(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def safe_text(locator, timeout=1000):
    if locator is None:
        return ""
    try:
        return normalize_text(locator.inner_text(timeout=timeout))
    except Exception:
        return ""


def safe_attr(locator, name, timeout=1000):
    if locator is None:
        return ""
    try:
        return locator.get_attribute(name, timeout=timeout) or ""
    except Exception:
        return ""


def safe_page_title(page):
    try:
        return normalize_text(page.title())
    except Exception:
        return ""


def first_text_from(locator):
    try:
        if locator.count() <= 0:
            return ""
        return safe_text(locator.first)
    except Exception:
        return ""


def texts_from(locator, limit):
    values = []
    for item in locator.all()[:limit]:
        text = safe_text(item)
        if text:
            values.append(text)
    return values


def normalize_text(text):
    return xs.normalize_text(text)


def unique(values):
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def escape_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")[:240]


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z").replace(":", "-").replace(".", "-")


def parse_args():
    parser = argparse.ArgumentParser(description="采集小红书首页推荐流证据")
    parser.add_argument("--url", default="https://www.xiaohongshu.com/explore", help="首页推荐流 URL")
    parser.add_argument("--out-dir", default="", help="输出目录")
    parser.add_argument("--limit", type=int, default=20, help="采样首页卡片数量，默认 20")
    parser.add_argument("--detail-limit", type=int, default=3, help="打开的详情页数量，默认 3")
    parser.add_argument("--scroll-pages", type=int, default=2, help="首页向下滚动次数，默认 2")
    parser.add_argument("--scroll-delay-ms", type=int, default=1600, help="滚动后等待毫秒数")
    parser.add_argument("--detail-delay-ms", type=int, default=2500, help="详情页之间等待毫秒数")
    parser.add_argument("--settle-ms", type=int, default=5000, help="页面加载后等待毫秒数")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="页面超时毫秒数")
    parser.add_argument("--screenshot", action="store_true", help="调试时保存截图，默认不保存")
    parser.add_argument("--cdp-endpoint", default=os.environ.get("BROWSER_CDP_ENDPOINT", ""), help="CDP endpoint")
    return parser.parse_args()


if __name__ == "__main__":
    main()
