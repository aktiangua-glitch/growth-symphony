#!/usr/bin/env python3

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在：{input_path}")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    source = select_source(data, args.rank)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else input_path.parent / "viral-copy"
    out_dir.mkdir(parents=True, exist_ok=True)

    context = build_context(data, source, input_path, args.topic, args.target_user)
    template = build_template(context)

    context_path = out_dir / "viral_copy_context.json"
    template_path = out_dir / "viral_copy_template.json"
    summary_path = out_dir / "summary.md"
    write_json(context_path, context)
    write_json(template_path, template)
    summary_path.write_text(render_summary(context, template_path), encoding="utf-8")

    print(json.dumps({
        "contextPath": str(context_path),
        "templatePath": str(template_path),
        "summaryPath": str(summary_path),
        "sourceTitle": context["source_note"].get("title", ""),
        "topic": context.get("topic", ""),
    }, ensure_ascii=False, indent=2))


def select_source(data, rank):
    schema = data.get("schema_version", "")
    if schema == "xhs.note_detail.agent_input.v1":
        return data

    details = data.get("details") or []
    if details:
        if rank:
            for detail in details:
                if int(detail.get("rank") or 0) == rank:
                    return detail
        return details[0]

    cards = data.get("cards") or data.get("recent_notes") or []
    if cards:
        if rank:
            for card in cards:
                if int(card.get("rank") or 0) == rank:
                    return card
        return cards[0]

    raise SystemExit("输入里没有可复刻的笔记证据。请先运行 note-detail 或 search-hot。")


def build_context(data, source, input_path, topic, target_user):
    body = clean_body_excerpt(source.get("body_excerpt", ""), source.get("title") or source.get("source_title", ""))
    question_examples = (source.get("comment_patterns") or {}).get("question_examples") or []
    comments = unique_compact_comments([*question_examples, *(source.get("comments") or [])], limit=8)
    evidence_limits = []
    if not body:
        evidence_limits.append("正文不可见或未采集到正文。")
    if not comments:
        evidence_limits.append("评论不可见或未采集到评论。")
    if not source.get("metrics_hint"):
        evidence_limits.append("互动指标不可见。")

    return {
        "schema_version": "xhs.viral_copy_context.v1",
        "source_path": str(input_path),
        "source_schema_version": data.get("schema_version", ""),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "topic": topic,
        "target_user": target_user,
        "source_note": {
            "rank": source.get("rank"),
            "title": source.get("title") or source.get("source_title", ""),
            "url": source.get("url") or source.get("final_url") or source.get("source_url", ""),
            "author": source.get("author", {}),
            "content_form": source.get("content_form", ""),
            "metrics_hint": source.get("metrics_hint", {}),
            "signals": source.get("signals", []),
            "tags": source.get("tags", []),
        },
        "structure_evidence": {
            "hook_analysis": source.get("hook_analysis", {}),
            "content_structure": source.get("content_structure", {}),
            "comment_patterns": source.get("comment_patterns", {}),
            "body_excerpt": body,
            "comment_examples": comments,
        },
        "llm_task": [
            "拆源笔记结构，不复用原文措辞。",
            "提炼可复刻结构和必须替换部分。",
            "围绕 topic 和 target_user 生成新笔记方案。",
            "输出必须符合 viral_copy_template.json。",
        ],
        "evidence_limits": evidence_limits,
    }


def build_template(context):
    return {
        "schema_version": "xhs.viral_copy.v1",
        "source_path": context["source_path"],
        "topic": context.get("topic", ""),
        "source_structure": {
            "title_pattern": "",
            "opening_hook": "",
            "body_rhythm": "",
            "tag_strategy": "",
            "comment_mechanism": "",
            "cover_hierarchy": "",
        },
        "replicable_parts": [],
        "replace_parts": [],
        "new_note_plan": {
            "titles": [],
            "cover_text": {
                "main": "",
                "sub": "",
            },
            "body_outline": [],
            "interaction_question": "",
            "topics": [],
        },
        "risks": [
            "不要逐字照抄原文。",
            "不要复用原图或原作者经历。",
        ],
        "evidence_limits": context.get("evidence_limits", []),
    }


def render_summary(context, template_path):
    note = context["source_note"]
    comments = context["structure_evidence"].get("comment_examples") or []
    comment_lines = "\n".join(f"- {item}" for item in comments[:5]) or "- 未采集到评论。"
    limits = "\n".join(f"- {item}" for item in context.get("evidence_limits", [])) or "- 暂无。"
    return f"""# 小红书笔记复刻上下文

## 源笔记

- 标题：{note.get("title", "")}
- URL：{note.get("url", "")}
- 课题：{context.get("topic", "") or "未指定"}
- 目标人群：{context.get("target_user", "") or "未指定"}
- 输出模板：{template_path}

## 评论证据

{comment_lines}

## 证据限制

{limits}

## Agent 下一步

读取 `viral_copy_context.json`，按 `viral_copy_template.json` 输出结构级复刻方案。
"""


def compact_text(value, limit):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def clean_body_excerpt(value, title):
    text = compact_text(value, 1800)
    text = re.sub(r"^(?:LIVE\s+)*(?:\d+/\d+\s+)?", "", text)
    if title and title in text:
        text = text[text.find(title):]
    for marker in (" 猜你想搜 ", " 共 ", " 评论 "):
        if marker in text:
            text = text.split(marker, 1)[0]
    return compact_text(text, 600)


def unique_compact_comments(values, limit):
    result = []
    seen = set()
    for value in values:
        text = clean_comment_example(value)
        text = re.sub(r"\s*展开\s*\d+\s*条回复.*$", "", text)
        key = re.sub(r"\d{2}-\d{2}.*$|昨天.*$|\d+\s*天前.*$", "", text)
        key = key[:60]
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def clean_comment_example(value):
    text = compact_text(value, 220)
    text = re.sub(r"\s+[^ ]{1,40}\s+作者\s+.*$", "", text)
    text = re.sub(r"\s+\d{2}-\d{2}\S*.*$", "", text)
    text = re.sub(r"\s+\d+\s*天前.*$", "", text)
    text = re.sub(r"\s+昨天.*$", "", text)
    text = re.sub(r"\s+赞\s*\d*.*$", "", text)
    return compact_text(text, 120)


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="生成小红书笔记复刻分析上下文")
    parser.add_argument("--input", required=True, help="note-detail/search-hot 生成的 agent_input.json")
    parser.add_argument("--out-dir", default="", help="输出目录，默认写到输入目录下 viral-copy")
    parser.add_argument("--rank", type=int, default=0, help="从 search-hot/details 里选择第几条，默认第一条详情")
    parser.add_argument("--topic", default="", help="要迁移到的新课题")
    parser.add_argument("--target-user", default="", help="新笔记目标人群")
    return parser.parse_args()


if __name__ == "__main__":
    main()
