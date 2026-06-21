#!/usr/bin/env python3

import argparse
import importlib.util
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKSPACE_ROOT = Path(os.environ.get("GROWTH_SYMPHONY_HOME", "/Users/admin/growth-symphony")).resolve()
WORKSPACE_ROOT = DEFAULT_WORKSPACE_ROOT if (DEFAULT_WORKSPACE_ROOT / "modules" / "xiaohongshu").exists() else SCRIPT_DIR.parents[4]
sys.path.insert(0, str(WORKSPACE_ROOT / "modules" / "xiaohongshu" / "lib"))

import xhs_browser as xb
import xhs_signal as xs


def main():
    args = parse_args()
    keywords = normalize_keywords(args.keyword, args.keywords)
    if len(keywords) < 2:
        raise SystemExit("至少需要 2 个关键词。")
    if not args.cdp_endpoint:
        raise SystemExit("缺少 BROWSER_CDP_ENDPOINT。先从已打开的浏览器 profile 取得 CDP endpoint。")

    run_dir = Path(args.out_dir).resolve() if args.out_dir else (
        WORKSPACE_ROOT / "runs" / "xiaohongshu" / "keyword-matrix" / f"{xb.timestamp()}-{xb.slugify('-'.join(keywords), 'keywords')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    search_hot = load_search_hot()
    keyword_runs = []
    for keyword in keywords:
        keyword_dir = run_dir / xb.slugify(keyword, "keyword")
        keyword_dir.mkdir(parents=True, exist_ok=True)
        local_args = argparse.Namespace(
            keyword=keyword,
            cdp_endpoint=args.cdp_endpoint,
            out_dir=str(keyword_dir),
            limit=args.limit,
            detail_limit=args.detail_limit,
            detail_delay_ms=args.detail_delay_ms,
            settle_ms=args.settle_ms,
            timeout_ms=args.timeout_ms,
            screenshot=args.screenshot,
        )
        samples = search_hot.run_browser(local_args, keyword_dir)
        xb.write_json(keyword_dir / "samples.json", samples)
        xb.write_json(keyword_dir / "agent_input.json", search_hot.build_agent_input(samples))
        xb.write_json(keyword_dir / "feishu_rows.json", search_hot.build_feishu_rows(samples, keyword_dir))
        (keyword_dir / "summary.md").write_text(search_hot.render_summary(samples), encoding="utf-8")
        keyword_runs.append({
            "keyword": keyword,
            "run_dir": str(keyword_dir),
            "samples": samples,
        })

    matrix = build_matrix(keyword_runs, run_dir)
    xb.write_json(run_dir / "matrix.json", matrix)
    xb.write_json(run_dir / "agent_input.json", build_agent_input(matrix))
    xb.write_json(run_dir / "feishu_rows.json", build_feishu_rows(matrix, run_dir))
    (run_dir / "summary.md").write_text(render_summary(matrix), encoding="utf-8")

    print(json.dumps({
        "runDir": str(run_dir),
        "matrixPath": str(run_dir / "matrix.json"),
        "agentInputPath": str(run_dir / "agent_input.json"),
        "summaryPath": str(run_dir / "summary.md"),
        "feishuRowsPath": str(run_dir / "feishu_rows.json"),
        "keywords": len(keywords),
        "cards": sum(len(item["samples"].get("cards", [])) for item in keyword_runs),
        "details": sum(len(item["samples"].get("details", [])) for item in keyword_runs),
    }, ensure_ascii=False, indent=2))


def load_search_hot():
    path = WORKSPACE_ROOT / "modules" / "xiaohongshu" / "skills" / "search-hot" / "scripts" / "search_hot.py"
    spec = importlib.util.spec_from_file_location("search_hot_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_matrix(keyword_runs, run_dir):
    rows = []
    for item in keyword_runs:
        samples = item["samples"]
        cards = samples.get("cards", [])
        details = samples.get("details", [])
        like_values = [
            (card.get("metric_numbers") or {}).get("likes")
            for card in cards
            if (card.get("metric_numbers") or {}).get("likes") is not None
        ]
        signal_counter = Counter()
        hook_counter = Counter()
        form_counter = Counter()
        ratio_counter = Counter()
        comment_theme_counter = Counter()
        for card in cards:
            signal_counter.update(card.get("signals") or [])
            hook_counter.update((card.get("hook_analysis") or {}).get("hook_patterns") or [])
            form = card.get("content_form")
            if form:
                form_counter.update([form])
            ratio_counter.update((card.get("engagement_ratios") or {}).get("ratio_labels") or [])
        for detail in details:
            if detail.get("error"):
                continue
            for theme in (detail.get("comment_patterns") or {}).get("themes", []):
                comment_theme_counter.update({theme.get("theme", ""): theme.get("count", 0)})

        rows.append({
            "keyword": item["keyword"],
            "run_dir": item["run_dir"],
            "captured_at": samples.get("captured_at", ""),
            "cards": len(cards),
            "details": len(details),
            "top_like_visible": max(like_values) if like_values else None,
            "avg_like_visible": round(sum(like_values) / len(like_values), 2) if like_values else None,
            "top_titles": [card.get("title", "") for card in cards[:5]],
            "dominant_signals": top_items(signal_counter),
            "dominant_hooks": top_items(hook_counter),
            "content_forms": top_items(form_counter),
            "engagement_labels": top_items(ratio_counter),
            "comment_themes": top_items(comment_theme_counter),
            "sample_urls": [card.get("url", "") for card in cards[:5]],
        })
    return {
        "schema_version": "xhs.keyword_matrix.v1",
        "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_dir": str(run_dir),
        "keywords": [item["keyword"] for item in keyword_runs],
        "rows": rows,
        "source_runs": [
            {
                "keyword": item["keyword"],
                "run_dir": item["run_dir"],
                "cards": len(item["samples"].get("cards", [])),
                "details": len(item["samples"].get("details", [])),
            }
            for item in keyword_runs
        ],
    }


def build_agent_input(matrix):
    return {
        "schema_version": "xhs.keyword_matrix.agent_input.v1",
        "task": "基于多个小红书关键词搜索样本做关键词矩阵和选题优先级分析",
        "analysis_owner": "agent_llm",
        "script_role": "browser_evidence_collector",
        "rules": [
            "只基于浏览器可见证据分析",
            "不要把单轮关键词矩阵写成全平台趋势",
            "关键词机会等级和选题优先级由 agent/LLM 判断",
        ],
        "captured_at": matrix["captured_at"],
        "keywords": matrix["keywords"],
        "rows": matrix["rows"],
        "source_runs": matrix["source_runs"],
    }


def build_feishu_rows(matrix, run_dir):
    run_id = Path(run_dir).name
    run_row = {
        "run_id": run_id,
        "平台": "小红书",
        "关键词": "关键词矩阵：" + "、".join(matrix["keywords"]),
        "采集时间": matrix["captured_at"],
        "样本数": sum(row["cards"] for row in matrix["rows"]),
        "详情数": sum(row["details"] for row in matrix["rows"]),
        "热点类型": "",
        "机会等级": "",
        "主导钩子": "",
        "内容形态": "",
        "一句话结论": "",
        "本地结果路径": str(run_dir),
    }
    evidence_rows = []
    for index, row in enumerate(matrix["rows"], start=1):
        evidence_rows.append({
            "run_id": run_id,
            "排名": index,
            "标题": row["keyword"],
            "URL": (row.get("sample_urls") or [""])[0],
            "可见互动": f"top_like:{row.get('top_like_visible') or '不可见'} avg_like:{row.get('avg_like_visible') or '不可见'}",
            "信号标签": "、".join(item["name"] for item in row.get("dominant_signals", [])),
            "推荐理由": "",
            "选题方向": "",
            "是否已深入分析": row["details"] > 0,
            "备注": "；".join(row.get("top_titles", [])[:3]),
        })
    return {
        "schema_version": "xhs.keyword_matrix.feishu_rows.v1",
        "tables": {
            "分析任务表": [run_row],
            "样本证据表": evidence_rows,
        },
    }


def render_summary(matrix):
    rows = "\n".join(
        f"| {xb.escape_cell(row['keyword'])} | {row['cards']} | {row['details']} | "
        f"{row.get('top_like_visible') if row.get('top_like_visible') is not None else '不可见'} | "
        f"{xb.escape_cell('、'.join(item['name'] for item in row.get('dominant_signals', [])[:4]))} | "
        f"{xb.escape_cell('、'.join(item['name'] for item in row.get('dominant_hooks', [])[:4]))} |"
        for row in matrix["rows"]
    )
    return f"""# 小红书关键词矩阵采集

## 运行信息

- 关键词：{"、".join(matrix["keywords"])}
- 采集时间：{matrix["captured_at"]}
- 关键词数：{len(matrix["rows"])}

## 矩阵证据

| 关键词 | 卡片数 | 详情数 | 可见最高点赞 | 高频信号 | 高频钩子 |
| --- | ---: | ---: | ---: | --- | --- |
{rows or "| - | 0 | 0 | - | - | - |"}

## Agent 分析入口

- Python 只聚合可见事实。
- 关键词机会、优先级、选题方向由 agent 读取 `agent_input.json` 后生成。
"""


def top_items(counter, limit=6):
    return [
        {"name": name, "count": count}
        for name, count in counter.most_common(limit)
        if name
    ]


def normalize_keywords(repeated, csv_value):
    values = []
    for item in repeated or []:
        values.extend(split_keywords(item))
    values.extend(split_keywords(csv_value))
    result = []
    seen = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def split_keywords(value):
    if not value:
        return []
    return [item.strip() for item in str(value).replace("，", ",").split(",") if item.strip()]


def parse_args():
    parser = argparse.ArgumentParser(description="批量采集小红书关键词矩阵证据")
    parser.add_argument("--keyword", action="append", default=[], help="关键词，可重复传入")
    parser.add_argument("--keywords", default="", help="逗号分隔的关键词列表")
    parser.add_argument("--out-dir", default="", help="输出目录")
    parser.add_argument("--limit", type=int, default=12, help="每个关键词采样搜索卡片数量，默认 12")
    parser.add_argument("--detail-limit", type=int, default=1, help="每个关键词打开的详情页数量，默认 1")
    parser.add_argument("--detail-delay-ms", type=int, default=2500, help="详情页之间等待毫秒数")
    parser.add_argument("--settle-ms", type=int, default=5000, help="页面加载后等待毫秒数")
    parser.add_argument("--timeout-ms", type=int, default=45000, help="页面超时毫秒数")
    parser.add_argument("--screenshot", action="store_true", help="调试时保存截图，默认不保存")
    parser.add_argument("--cdp-endpoint", default=os.environ.get("BROWSER_CDP_ENDPOINT", ""), help="CDP endpoint")
    return parser.parse_args()


if __name__ == "__main__":
    main()
