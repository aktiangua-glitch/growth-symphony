#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKSPACE_ROOT = Path(os.environ.get("GROWTH_SYMPHONY_HOME", "/Users/admin/growth-symphony")).resolve()
WORKSPACE_ROOT = DEFAULT_WORKSPACE_ROOT if (DEFAULT_WORKSPACE_ROOT / "modules" / "xiaohongshu").exists() else SCRIPT_DIR.parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT / "modules" / "xiaohongshu" / "lib"))

import xhs_signal as xs
import xhs_browser as xb


def main():
    args = parse_args()
    if not args.url:
        raise SystemExit("缺少 --url")
    if not args.cdp_endpoint:
        raise SystemExit("缺少 BROWSER_CDP_ENDPOINT。先从已打开的 ADSPower profile 取得 ws.puppeteer。")

    run_dir = Path(args.out_dir).resolve() if args.out_dir else (
        WORKSPACE_ROOT / "runs" / "xiaohongshu" / "note-detail" / f"{xb.timestamp()}-{xb.slugify(note_id_from_url(args.url), 'note')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    if args.screenshot:
        (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)

    detail_path = run_dir / "detail.json"
    agent_input_path = run_dir / "agent_input.json"
    summary_path = run_dir / "summary.md"
    feishu_rows_path = run_dir / "feishu_rows.json"

    detail = run_browser(args, run_dir)
    xb.write_json(detail_path, detail)
    xb.write_json(agent_input_path, build_agent_input(detail))
    xb.write_json(feishu_rows_path, build_feishu_rows(detail, run_dir))
    summary_path.write_text(render_summary(detail), encoding="utf-8")

    print(json.dumps({
        "runDir": str(run_dir),
        "detailPath": str(detail_path),
        "agentInputPath": str(agent_input_path),
        "summaryPath": str(summary_path),
        "feishuRowsPath": str(feishu_rows_path),
        "title": detail.get("title", ""),
        "comments": len(detail.get("comments", [])),
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
            page.goto(xs.canonical_note_url(args.url), wait_until="domcontentloaded", timeout=args.timeout_ms)
            page.wait_for_timeout(args.settle_ms)
            if args.screenshot:
                page.screenshot(path=str(run_dir / "screenshots" / "detail.png"), full_page=False)

            detail = extract_detail(page, args.url, args.comment_limit)
            detail["captured_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            return detail
        finally:
            for page in reversed(created_pages):
                xb.close_page(page)


def extract_detail(page, source_url, comment_limit):
    detail = xb.extract_note_detail(page, comment_limit=comment_limit, tag_limit=20, body_limit=1800, page_text_limit=2600)
    return {
        "source_url": source_url,
        "final_url": detail.pop("url", page.url),
        "note_id": note_id_from_url(page.url or source_url),
        **detail,
    }


def build_agent_input(detail):
    return {
        "schema_version": "xhs.note_detail.agent_input.v1",
        "task": "基于单条小红书笔记做内容结构和评论需求分析",
        "analysis_owner": "agent_llm",
        "script_role": "browser_evidence_collector",
        "rules": [
            "只基于浏览器可见证据分析",
            "不要把单条笔记写成全平台趋势",
            "不要沿用固定选题模板，按标题、正文和评论重新判断",
        ],
        "source_url": detail.get("source_url", ""),
        "final_url": detail.get("final_url", ""),
        "note_id": detail.get("note_id", ""),
        "captured_at": detail.get("captured_at", ""),
        "access_status": detail.get("access_status", ""),
        "title": detail.get("title", ""),
        "author": detail.get("author", {}),
        "signals": detail.get("signals", []),
        "metrics_hint": detail.get("metrics_hint", {}),
        "metric_numbers": detail.get("metric_numbers", {}),
        "engagement_ratios": detail.get("engagement_ratios", {}),
        "hook_analysis": detail.get("hook_analysis", {}),
        "content_structure": detail.get("content_structure", {}),
        "comment_patterns": detail.get("comment_patterns", {}),
        "content_form": detail.get("content_form", ""),
        "tags": detail.get("tags", []),
        "body_excerpt": detail.get("body_excerpt", "")[:1200],
        "comments": (detail.get("comments") or [])[:12],
    }


def build_feishu_rows(detail, run_dir):
    run_id = Path(run_dir).name
    run_row = {
        "run_id": run_id,
        "平台": "小红书",
        "关键词": "笔记深挖",
        "采集时间": detail["captured_at"],
        "样本数": 1,
        "详情数": 1,
        "热点类型": "",
        "机会等级": "",
        "主导钩子": "",
        "内容形态": "",
        "一句话结论": "",
        "本地结果路径": str(run_dir),
    }
    evidence_row = {
        "run_id": run_id,
        "排名": 1,
        "标题": detail.get("title", ""),
        "URL": detail.get("final_url") or detail.get("source_url", ""),
        "可见互动": metrics_text(detail.get("metrics_hint", {})),
        "信号标签": "、".join(detail.get("signals", [])),
        "推荐理由": "",
        "选题方向": "",
        "是否已深入分析": True,
        "备注": detail.get("body_excerpt", "")[:180],
    }
    return {
        "schema_version": "xhs.note_detail.feishu_rows.v1",
        "tables": {
            "分析任务表": [run_row],
            "样本证据表": [evidence_row],
        },
    }


def render_summary(detail):
    comments = "\n".join(f"- {item}" for item in detail.get("comments", [])[:8]) or "- 未采集到评论。"
    tags = "、".join(detail.get("tags", [])) or "不可见"
    metrics = metrics_text(detail.get("metrics_hint", {})) or "不可见"
    signals = "、".join(detail.get("signals", [])) or "未识别"

    return f"""# 小红书笔记采集

## 运行信息

- URL：{detail.get("final_url") or detail.get("source_url")}
- 采集时间：{detail["captured_at"]}
- 页面状态：{detail.get("access_status", "visible")}
- 标题：{detail.get("title", "")}
- 可见互动：{metrics}
- 浅层信号：{signals}
- 标签：{tags}

## 正文摘要

{detail.get("body_excerpt", "")[:900] or "未采集到正文。"}

## 评论信号

{comments}

## Agent 分析入口

- Python 只采集浏览器可见事实和浅层信号。
- 内容形态、主导钩子、机会等级、推荐理由、选题方向由 agent 读取 `agent_input.json` 后生成。
- 分析时必须结合当前笔记和用户课题，不使用固定选题模板。

## 样本限制

- 这是浏览器当前登录态可见页面采样。
- 不可见指标不代表数值为 0。
- 单条笔记只能代表该内容样本，不代表全平台趋势。
"""


def close_page(page):
    try:
        if page and not page.is_closed():
            page.close()
    except Exception:
        pass


def parse_args():
    parser = argparse.ArgumentParser(description="采集单条小红书笔记详情页证据")
    parser.add_argument("--url", default="", help="必填，小红书笔记 URL")
    parser.add_argument("--out-dir", default="", help="输出目录")
    parser.add_argument("--comment-limit", type=int, default=30, help="最多采集评论数量，默认 30")
    parser.add_argument("--settle-ms", type=int, default=5000, help="页面加载后等待毫秒数")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="页面超时毫秒数")
    parser.add_argument("--screenshot", action="store_true", help="调试时保存截图，默认不保存")
    parser.add_argument("--cdp-endpoint", default=os.environ.get("BROWSER_CDP_ENDPOINT", ""), help="CDP endpoint")
    return parser.parse_args()


def extract_signals(title, text):
    return xs.extract_signal_tags(title, text)


def extract_metric_hints(text):
    return xs.extract_metric_hints(text)


def safe_text(locator, timeout=1000):
    if locator is None:
        return ""
    try:
        return normalize_text(locator.inner_text(timeout=timeout))
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


def note_id_from_url(url):
    return xs.note_id_from_url(url)


def access_status(url, title, page_text):
    return xs.detect_access_status(url, title, page_text)


def normalize_text(text):
    return xs.normalize_text(text)


def metrics_text(metrics):
    return xs.metrics_text(metrics)


def unique(values):
    seen = set()
    result = []
    for value in values:
        key = value.lower() if isinstance(value, str) else value
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z").replace(":", "-").replace(".", "-")


def slugify(text):
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", "-", text).strip("-")
    return (slug or "note")[:60]


if __name__ == "__main__":
    main()
