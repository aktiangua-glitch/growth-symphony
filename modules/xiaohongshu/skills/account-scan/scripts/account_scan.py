#!/usr/bin/env python3

import argparse
import json
import os
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
    if not args.url:
        raise SystemExit("缺少 --url。请传入小红书账号主页 URL。")
    if not args.cdp_endpoint:
        raise SystemExit("缺少 BROWSER_CDP_ENDPOINT。先从已打开的浏览器 profile 取得 CDP endpoint。")

    run_dir = Path(args.out_dir).resolve() if args.out_dir else (
        WORKSPACE_ROOT / "runs" / "xiaohongshu" / "account-scan" / f"{xb.timestamp()}-{xb.slugify(xs.note_id_from_url(args.url), 'account')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.screenshot:
        (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)

    profile_path = run_dir / "profile.json"
    agent_input_path = run_dir / "agent_input.json"
    summary_path = run_dir / "summary.md"
    feishu_rows_path = run_dir / "feishu_rows.json"

    profile = run_browser(args, run_dir)
    xb.write_json(profile_path, profile)
    xb.write_json(agent_input_path, build_agent_input(profile))
    xb.write_json(feishu_rows_path, build_feishu_rows(profile, run_dir))
    summary_path.write_text(render_summary(profile), encoding="utf-8")

    print(json.dumps({
        "runDir": str(run_dir),
        "profilePath": str(profile_path),
        "agentInputPath": str(agent_input_path),
        "summaryPath": str(summary_path),
        "feishuRowsPath": str(feishu_rows_path),
        "cards": len(profile["recent_notes"]),
        "details": len(profile["details"]),
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
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(args.scroll_delay_ms)
            if args.screenshot:
                page.screenshot(path=str(run_dir / "screenshots" / "account.png"), full_page=False)

            profile_info = extract_profile_info(page, args.url)
            recent_notes = extract_recent_notes(page, args.limit)
            details = []
            for card in recent_notes[:args.detail_limit]:
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
                "source_url": args.url,
                "final_url": page.url,
                "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "profile": profile_info,
                "limits": {"recent_notes": args.limit, "details": args.detail_limit},
                "recent_notes": recent_notes,
                "details": details,
            }
        finally:
            for page in reversed(created_pages):
                xb.close_page(page)


def extract_profile_info(page, source_url):
    page_text = xb.safe_text(page.locator("body").first)
    title = xb.first_text_from(page.locator("h1, [class*=name], [class*=nickname]")) or xb.safe_page_title(page)
    metrics = xs.extract_metric_hints(page_text[:2000])
    return {
        "source_url": source_url,
        "final_url": page.url,
        "page_title": title,
        "stats_hint": metrics,
        "stat_numbers": xs.metric_numbers(metrics),
        "profile_text_excerpt": page_text[:1800],
    }


def extract_recent_notes(page, limit):
    return xb.extract_note_cards(page, limit)


def extract_detail(page, source_card):
    return xb.extract_note_detail(page, source_card, comment_limit=10, tag_limit=16, body_limit=1600, page_text_limit=2200)


def build_agent_input(profile):
    return {
        "schema_version": "xhs.account_scan.agent_input.v1",
        "task": "基于小红书账号主页和近期笔记样本做账号体检",
        "analysis_owner": "agent_llm",
        "script_role": "browser_evidence_collector",
        "rules": [
            "只基于浏览器可见证据分析",
            "样本少时只做轻量体检，不下长期增长结论",
            "账号评分必须引用主页信息、近期标题、正文或评论证据",
        ],
        "analysis_dimensions": [
            "定位清晰度",
            "内容结构力",
            "互动转化力",
            "账号辨识度",
            "增长可持续性",
        ],
        "source_url": profile.get("source_url", ""),
        "final_url": profile.get("final_url", ""),
        "captured_at": profile.get("captured_at", ""),
        "profile": profile.get("profile", {}),
        "recent_notes": [
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
            for card in profile.get("recent_notes", [])
        ],
        "details": [
            compact_detail(detail, index)
            for index, detail in enumerate(profile.get("details", []), start=1)
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


def build_feishu_rows(profile, run_dir):
    run_id = Path(run_dir).name
    run_row = {
        "run_id": run_id,
        "平台": "小红书",
        "关键词": "账号体检",
        "采集时间": profile["captured_at"],
        "样本数": len(profile["recent_notes"]),
        "详情数": len(profile["details"]),
        "热点类型": "",
        "机会等级": "",
        "主导钩子": "",
        "内容形态": "",
        "一句话结论": "",
        "本地结果路径": str(run_dir),
    }
    evidence_rows = []
    for card in profile["recent_notes"]:
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
        "schema_version": "xhs.account_scan.feishu_rows.v1",
        "tables": {
            "分析任务表": [run_row],
            "样本证据表": evidence_rows,
        },
    }


def render_summary(profile):
    info = profile.get("profile", {})
    card_rows = "\n".join(
        f"| {card.get('index')} | {escape_cell(card.get('title', ''))} | "
        f"{escape_cell(card.get('content_form', '') or '不可见')} | "
        f"{escape_cell(' / '.join(card.get('signals', [])) or '未识别')} | "
        f"{escape_cell(xs.metrics_text(card.get('metrics_hint', {})) or '不可见')} |"
        for card in profile["recent_notes"]
    )
    detail_rows = "\n".join(
        f"| {index + 1} | {escape_cell(detail.get('title') or detail.get('source_card', {}).get('title', ''))} | "
        f"{escape_cell(' / '.join((detail.get('comment_patterns') or {}).get('question_examples', [])[:2]))} |"
        for index, detail in enumerate(profile["details"])
    )
    return f"""# 小红书账号采集

## 运行信息

- 账号页：{profile.get("final_url") or profile.get("source_url")}
- 采集时间：{profile["captured_at"]}
- 页面标题：{info.get("page_title", "")}
- 可见统计：{xs.metrics_text(info.get("stats_hint", {})) or "不可见"}
- 近期笔记数：{len(profile["recent_notes"])}
- 详情页数：{len(profile["details"])}

## 主页摘要

{info.get("profile_text_excerpt", "")[:800] or "未采集到主页文本。"}

## 近期笔记

| # | 标题 | 形态 | 信号 | 可见互动 |
| ---: | --- | --- | --- | --- |
{card_rows or "| - | 未采集到近期笔记 | - | - | - |"}

## 深入详情

| # | 标题 | 评论问题样本 |
| ---: | --- | --- |
{detail_rows or "| - | 未采集详情页 | - |"}

## Agent 分析入口

- Python 只采集账号主页、近期笔记和少量详情证据。
- 五维评分、最大优势、最大短板和下一步动作由 agent 读取 `agent_input.json` 后生成。
- 样本少时只做轻量体检。
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
    parser = argparse.ArgumentParser(description="采集小红书账号主页和近期笔记证据")
    parser.add_argument("--url", default="", help="必填，小红书账号主页 URL")
    parser.add_argument("--out-dir", default="", help="输出目录")
    parser.add_argument("--limit", type=int, default=15, help="采样近期笔记数量，默认 15")
    parser.add_argument("--detail-limit", type=int, default=3, help="打开的详情页数量，默认 3")
    parser.add_argument("--scroll-pages", type=int, default=1, help="账号页向下滚动次数，默认 1")
    parser.add_argument("--scroll-delay-ms", type=int, default=1600, help="滚动后等待毫秒数")
    parser.add_argument("--detail-delay-ms", type=int, default=2500, help="详情页之间等待毫秒数")
    parser.add_argument("--settle-ms", type=int, default=5000, help="页面加载后等待毫秒数")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="页面超时毫秒数")
    parser.add_argument("--screenshot", action="store_true", help="调试时保存截图，默认不保存")
    parser.add_argument("--cdp-endpoint", default=os.environ.get("BROWSER_CDP_ENDPOINT", ""), help="CDP endpoint")
    return parser.parse_args()


if __name__ == "__main__":
    main()
