#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKSPACE_ROOT = Path(os.environ.get("GROWTH_SYMPHONY_HOME", "/Users/admin/growth-symphony")).resolve()
WORKSPACE_ROOT = DEFAULT_WORKSPACE_ROOT if (DEFAULT_WORKSPACE_ROOT / "modules" / "xiaohongshu").exists() else SCRIPT_DIR.parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT / "modules" / "xiaohongshu" / "lib"))

import xhs_signal as xs
import xhs_browser as xb


def main():
    args = parse_args()
    if not args.keyword:
        raise SystemExit("缺少 --keyword")
    if not args.cdp_endpoint:
        raise SystemExit("缺少 BROWSER_CDP_ENDPOINT。先从已打开的 ADSPower profile 取得 ws.puppeteer。")

    run_dir = Path(args.out_dir).resolve() if args.out_dir else (
        WORKSPACE_ROOT / "runs" / "xiaohongshu" / "search-hot" / f"{xb.timestamp()}-{xb.slugify(args.keyword, 'keyword')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.screenshot:
        (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)

    samples_path = run_dir / "samples.json"
    agent_input_path = run_dir / "agent_input.json"
    feishu_rows_path = run_dir / "feishu_rows.json"
    summary_path = run_dir / "summary.md"

    samples = run_browser(args, run_dir)
    xb.write_json(samples_path, samples)
    xb.write_json(agent_input_path, build_agent_input(samples))
    xb.write_json(feishu_rows_path, build_feishu_rows(samples, run_dir))
    summary_path.write_text(render_summary(samples), encoding="utf-8")

    print(json.dumps({
        "runDir": str(run_dir),
        "samplesPath": str(samples_path),
        "agentInputPath": str(agent_input_path),
        "summaryPath": str(summary_path),
        "feishuRowsPath": str(feishu_rows_path),
        "cards": len(samples["cards"]),
        "details": len(samples["details"]),
    }, ensure_ascii=False, indent=2))


def run_browser(args, run_dir):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit("缺少 Python playwright 依赖。执行：python3 -m pip install -r requirements.txt") from exc

    search_url = f"https://www.xiaohongshu.com/search_result?keyword={quote(args.keyword)}&type=51"
    created_pages = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp_endpoint)
        context = browser.contexts[0] if browser.contexts else None
        if context is None:
            raise RuntimeError("CDP 浏览器没有可用 context。")

        try:
            search_page = context.new_page()
            created_pages.append(search_page)
            search_page.goto(search_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            search_page.wait_for_timeout(args.settle_ms)
            if args.screenshot:
                search_page.screenshot(path=str(run_dir / "screenshots" / "search.png"), full_page=False)

            cards = extract_search_cards(search_page, args.limit)
            details = []
            for card in cards[:args.detail_limit]:
                if not card.get("url"):
                    continue
                detail_page = context.new_page()
                created_pages.append(detail_page)
                try:
                    detail_page.goto(card["url"], wait_until="domcontentloaded", timeout=args.timeout_ms)
                    detail_page.wait_for_timeout(args.settle_ms)
                    if args.screenshot:
                        index = len(details) + 1
                        detail_page.screenshot(path=str(run_dir / "screenshots" / f"detail-{index}.png"), full_page=False)
                    details.append(extract_detail(detail_page, card))
                except Exception as exc:
                    details.append({"source_card": card, "error": str(exc)})
                finally:
                    xb.close_page(detail_page)
                search_page.wait_for_timeout(args.detail_delay_ms)

            samples = {
                "keyword": args.keyword,
                "search_url": search_url,
                "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "limits": {"cards": args.limit, "details": args.detail_limit},
                "cards": cards,
                "details": details,
            }
            return samples
        finally:
            for page in reversed(created_pages):
                xb.close_page(page)


def close_page(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def extract_search_cards(page, limit):
    return xb.extract_note_cards(page, limit)


def extract_detail(page, source_card):
    return xb.extract_note_detail(page, source_card, comment_limit=8, tag_limit=12, body_limit=1600, page_text_limit=2400)


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


def extract_signals(title, text):
    return xs.extract_signal_tags(title, text)


def extract_metric_hints(text):
    return xs.extract_metric_hints(text)


def is_note_url(url):
    return xs.is_note_url(url)


def note_id_from_url(url):
    return xs.note_id_from_url(url)


def normalize_url(base_url, raw_url):
    return urljoin(base_url, raw_url)


def normalize_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


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


def safe_box(locator):
    try:
        return locator.bounding_box()
    except Exception:
        return None


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


def build_agent_input(samples):
    return {
        "schema_version": "xhs.search_hot.agent_input.v1",
        "task": "基于小红书搜索页样本做关键词热门分析",
        "analysis_owner": "agent_llm",
        "script_role": "browser_evidence_collector",
        "rules": [
            "只基于浏览器可见证据分析",
            "不要把单次搜索采样写成全平台趋势",
            "不要沿用固定选题模板，按关键词、标题、正文和评论重新判断",
        ],
        "keyword": samples["keyword"],
        "captured_at": samples["captured_at"],
        "search_url": samples["search_url"],
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
                "image": card.get("image", ""),
            }
            for card in samples["cards"]
        ],
        "details": [
            compact_detail(detail, index)
            for index, detail in enumerate(samples["details"], start=1)
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
        "source_card": compact_source_card(detail.get("source_card", {})),
        "title": detail.get("title", ""),
        "url": detail.get("url", ""),
        "author": detail.get("author", {}),
        "signals": detail.get("signals", []),
        "metrics_hint": detail.get("metrics_hint", {}),
        "metric_numbers": detail.get("metric_numbers", {}),
        "engagement_ratios": detail.get("engagement_ratios", {}),
        "hook_analysis": detail.get("hook_analysis", {}),
        "content_structure": detail.get("content_structure", {}),
        "comment_patterns": detail.get("comment_patterns", {}),
        "content_form": detail.get("content_form", ""),
        "media_refs": detail.get("media_refs", []),
        "access_status": detail.get("access_status", ""),
        "tags": detail.get("tags", []),
        "body_excerpt": detail.get("body_excerpt", "")[:900],
        "comments": (detail.get("comments") or [])[:8],
    }


def compact_source_card(card):
    return {
        "title": card.get("title", ""),
        "url": card.get("url", ""),
        "image": card.get("image", ""),
        "visible_text": card.get("visible_text", ""),
        "content_form": card.get("content_form", ""),
    }


def build_feishu_rows(samples, run_dir):
    run_id = Path(run_dir).name
    run_row = {
        "run_id": run_id,
        "平台": "小红书",
        "关键词": samples["keyword"],
        "采集时间": samples["captured_at"],
        "样本数": len(samples["cards"]),
        "详情数": len(samples["details"]),
        "热点类型": "",
        "机会等级": "",
        "主导钩子": "",
        "内容形态": "",
        "一句话结论": "",
        "本地结果路径": str(run_dir),
    }
    evidence_rows = []
    for card in samples["cards"]:
        evidence_rows.append({
            "run_id": run_id,
            "排名": card.get("index"),
            "标题": card.get("title", ""),
            "URL": card.get("url", ""),
            "可见互动": metrics_text(card.get("metrics_hint", {})),
            "信号标签": "、".join(card.get("signals", [])),
            "推荐理由": "",
            "选题方向": "",
            "是否已深入分析": False,
            "备注": "",
        })
    return {
        "schema_version": "xhs.search_hot.feishu_rows.v1",
        "tables": {
            "分析任务表": [run_row],
            "样本证据表": evidence_rows,
        },
    }


def render_summary(samples):
    card_rows = "\n".join(
        f"| {card.get('index')} | {escape_cell(card.get('title', ''))} | "
        f"{escape_cell(' / '.join(card.get('signals', [])) or '未识别')} | "
        f"{escape_cell(metrics_text(card.get('metrics_hint', {})) or '不可见')} |"
        for card in samples["cards"]
    )
    detail_rows = "\n".join(
        f"| {index + 1} | {escape_cell(detail.get('title') or detail.get('source_card', {}).get('title', ''))} | "
        f"{escape_cell(detail.get('source_card', {}).get('visible_text', ''))} | "
        f"{escape_cell(' / '.join((detail.get('comments') or [])[:3]))} |"
        for index, detail in enumerate(samples["details"])
    )

    return f"""# 小红书关键词热门采集

## 运行信息

- 关键词：{samples["keyword"]}
- 采集时间：{samples["captured_at"]}
- 搜索页：{samples["search_url"]}
- 搜索卡片数：{len(samples["cards"])}
- 详情页数：{len(samples["details"])}

## 样本

| # | 标题 | 信号 | 可见互动 |
| ---: | --- | --- | --- |
{card_rows or "| - | 未采集到搜索卡片 | - | - |"}

## 详情页

| # | 标题 | 来源卡片 | 评论信号 |
| ---: | --- | --- | --- |
{detail_rows or "| - | 未采集详情页 | - | - |"}

## Agent 分析入口

- Python 只采集浏览器可见事实和浅层信号。
- 热点类型、机会等级、内容形态、推荐理由、选题方向由 agent 读取 `agent_input.json` 后生成。
- 分析时必须结合当前关键词，不使用固定选题模板。

## 样本限制

- 这是浏览器可见页面采样。
- 不可见指标不代表数值为 0。
- 单次搜索页不足以代表全平台趋势。
"""


def parse_args():
    parser = argparse.ArgumentParser(description="采集小红书关键词搜索页热门内容证据")
    parser.add_argument("--keyword", default="", help="必填，搜索关键词")
    parser.add_argument("--out-dir", default="", help="输出目录")
    parser.add_argument("--limit", type=int, default=20, help="采样搜索卡片数量，默认 20")
    parser.add_argument("--detail-limit", type=int, default=3, help="打开的详情页数量，默认 3")
    parser.add_argument("--detail-delay-ms", type=int, default=2500, help="详情页之间等待毫秒数")
    parser.add_argument("--settle-ms", type=int, default=5000, help="页面加载后等待毫秒数")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="页面超时毫秒数")
    parser.add_argument("--screenshot", action="store_true", help="调试时保存截图，默认不保存")
    parser.add_argument("--cdp-endpoint", default=os.environ.get("BROWSER_CDP_ENDPOINT", ""), help="CDP endpoint")
    return parser.parse_args()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def metrics_text(metrics):
    return xs.metrics_text(metrics)


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


def escape_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")[:240]


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z").replace(":", "-").replace(".", "-")


def slugify(text):
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", "-", text).strip("-")
    return (slug or "keyword")[:60]


if __name__ == "__main__":
    main()
