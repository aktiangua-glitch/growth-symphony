#!/usr/bin/env python3

import argparse
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PALETTE_URL = "https://xn--muu023g.cn/palettes.json"
DEFAULT_PALETTE_BRAND = "MARD"
DEFAULT_PALETTE_MAX_COLORS = 72


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在：{input_path}")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    source = select_source(data, args.rank)
    out_dir = Path(args.out_dir).resolve() if args.out_dir else input_path.parent / "viral-copy"
    out_dir.mkdir(parents=True, exist_ok=True)

    palette_reference = build_palette_reference(args, out_dir, args.topic)
    context = build_context(data, source, input_path, args.topic, args.target_user, palette_reference)
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


def build_context(data, source, input_path, topic, target_user, palette_reference):
    body = clean_body_excerpt(source.get("body_excerpt", ""), source.get("title") or source.get("source_title", ""))
    question_examples = (source.get("comment_patterns") or {}).get("question_examples") or []
    comments = unique_compact_comments([*question_examples, *(source.get("comments") or [])], limit=8)
    media_refs = media_references(source)
    is_bead_task = is_bead_pattern_task(source, topic)
    evidence_limits = []
    if not body:
        evidence_limits.append("正文不可见或未采集到正文。")
    if not comments:
        evidence_limits.append("评论不可见或未采集到评论。")
    if not source.get("metrics_hint"):
        evidence_limits.append("互动指标不可见。")
    if not media_refs:
        evidence_limits.append("未采集到可用原图、视频或截图引用；视觉复刻需要用户补原图/截图或重新采集。")
    if is_bead_task and not palette_reference.get("enabled"):
        evidence_limits.append("拼豆真实色卡未加载成功；图纸色号需要用户补色卡或重新拉取 palettes.json。")

    llm_task = [
        "拆源笔记结构，不复用原文措辞。",
        "拆源图像结构，不复用原图。",
        "提炼可复刻结构和必须替换部分。",
        "围绕 topic 和 target_user 生成新笔记方案、视觉方案和互动方案。",
        "输出必须符合 viral_copy_template.json。",
    ]
    if is_bead_task:
        llm_task.append("如果生成拼豆图纸，必须从 bead_palette_reference 的真实色号中选色，不能写不存在的颜色。")

    return {
        "schema_version": "xhs.viral_copy_context.v1",
        "source_path": str(input_path),
        "source_schema_version": data.get("schema_version", ""),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "topic": topic,
        "target_user": target_user,
        "is_bead_pattern_task": is_bead_task,
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
        "visual_evidence": {
            "content_form": source.get("content_form", ""),
            "media_refs": media_refs,
            "source_visual_notes": [
                "只把原图/关键帧作为构图、色块、信息层级参考。",
                "最终图片或图纸必须原创，不复用原图。"
            ],
        },
        "bead_palette_reference": palette_reference,
        "llm_task": llm_task,
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
        "visual_plan": {
            "reference_handling": "说明如何使用原图/截图/关键帧作为参考，以及哪些元素必须替换。",
            "target_visual_type": "例如：拼豆图纸、成品展示图、教程步骤图、视频关键帧组图。",
            "image_prompts": [
                {
                    "name": "",
                    "prompt": "",
                    "notes": "用于 gpt-image-2 实际出图，并作为随附记录保存。"
                }
            ],
            "generated_assets": [
                {
                    "type": "image_or_pattern_sheet",
                    "mode": "Mode A 本地落盘 / Mode B 宿主出图 / Mode C 无法出图",
                    "path_or_url": "",
                    "prompt_path": "",
                    "notes": "有图像能力时必须写实际图片路径或链接；只有 Mode C 才写无法出图原因。"
                }
            ],
            "pattern_sheet": {
                "canvas_ratio": "",
                "grid_size": "",
                "palette_source": context.get("bead_palette_reference", {}).get("source_url", ""),
                "brand": context.get("bead_palette_reference", {}).get("brand", ""),
                "palette": [],
                "color_limit": "拼豆图纸色块只能使用 bead_palette_reference 里存在的真实色号；palette 数组必须写 code/name/hex/usage。",
                "layout_notes": "",
                "text_overlay": "",
            },
            "video_keyframes": [],
        },
        "risks": [
            "不要逐字照抄原文。",
            "不要复用原图、视频原帧或原作者经历。",
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

## 视觉证据

{visual_lines(context)}

## 拼豆色卡

{palette_lines(context)}

## 证据限制

{limits}

## Agent 下一步

读取 `viral_copy_context.json`，按 `viral_copy_template.json` 输出文案结构、视觉复刻和互动方案。若用户要图纸，优先输出拼豆图纸 prompt、真实色号和色块说明。
"""


def build_palette_reference(args, out_dir, topic):
    if args.no_palette:
        return {
            "enabled": False,
            "source_url": args.palette_url,
            "brand": args.palette_brand,
            "error": "已通过 --no-palette 跳过真实拼豆色卡。",
            "usage_rules": [],
        }

    try:
        with urllib.request.urlopen(args.palette_url, timeout=args.palette_timeout) as response:
            payload = response.read().decode("utf-8")
        data = json.loads(payload)
    except Exception as exc:
        return {
            "enabled": False,
            "source_url": args.palette_url,
            "brand": args.palette_brand,
            "error": f"{type(exc).__name__}: {exc}",
            "usage_rules": [
                "拼豆图纸不能凭空编造色号。",
                "重新拉取 palettes.json 或让用户上传色卡后再生成可落地图纸。",
            ],
        }

    cache_path = out_dir / "palette_reference.json"
    write_json(cache_path, data)

    brands = data.get("brands") or {}
    brand_id = args.palette_brand if args.palette_brand in brands else next(iter(brands), "")
    brand = brands.get(brand_id) or {}
    colors = brand.get("colors") or []
    groups = data.get("groups") or {}
    selected_group_ids = select_palette_groups(topic, colors)
    selected_colors = select_palette_colors(colors, groups, selected_group_ids, args.palette_max_colors)

    return {
        "enabled": True,
        "source_url": args.palette_url,
        "local_cache_path": str(cache_path),
        "brand": brand_id,
        "brand_label": brand.get("label", ""),
        "palette_edition": brand.get("paletteEdition", ""),
        "total_colors": len(colors),
        "recommended_color_counts": brand.get("recommendedColorCounts", []),
        "selected_groups": [
            {
                "id": group_id,
                "label": (groups.get(group_id) or {}).get("label", group_id),
                "bucket": (groups.get(group_id) or {}).get("bucket", ""),
            }
            for group_id in selected_group_ids
        ],
        "selected_colors": selected_colors,
        "usage_rules": [
            "拼豆图纸只能使用 selected_colors 或 local_cache_path 中存在的真实 code/name/hex。",
            "pattern_sheet.palette 必须写 code、name、hex、usage；不要只写“浅粉/奶油黄”这类抽象色。",
            "gpt-image-2 prompt 里要明确色块来自真实拼豆色卡，并要求生成可按格子复刻的像素图纸。",
            "如果需要更多颜色，读取 local_cache_path 的全量色卡，不要临时编色号。",
        ],
    }


def is_bead_pattern_task(source, topic):
    text = " ".join([
        str(topic or ""),
        str(source.get("title") or source.get("source_title") or ""),
        str(source.get("body_excerpt") or ""),
    ]).lower()
    keywords = ("拼豆", "豆豆", "图纸", "像素", "perler", "hama", "mard", "bead")
    return any(keyword in text for keyword in keywords)


def select_palette_groups(topic, colors):
    all_groups = []
    for color in colors:
        group_id = color.get("group", "")
        if group_id and group_id not in all_groups:
            all_groups.append(group_id)

    text = str(topic or "").lower()
    matches = []
    rules = [
        (("桃", "蜜桃", "peach", "橙", "orange", "黄", "lemon", "柠檬", "暖", "夏日"), ("A", "E")),
        (("冰", "气泡", "海", "水", "蓝", "sky", "blue", "slush"), ("C",)),
        (("草", "抹茶", "绿", "mint", "green"), ("B",)),
        (("紫", "葡萄", "lavender", "purple"), ("D",)),
        (("粉", "草莓", "樱花", "pink", "strawberry"), ("E",)),
        (("红", "爱心", "苹果", "red", "heart"), ("F",)),
        (("肤", "人物", "脸", "skin", "face"), ("G",)),
        (("黑", "白", "灰", "描边", "阴影", "neutral", "outline"), ("H", "M")),
    ]
    for needles, group_ids in rules:
        if any(needle in text for needle in needles):
            for group_id in group_ids:
                if group_id in all_groups and group_id not in matches:
                    matches.append(group_id)

    if not matches:
        matches = list(all_groups)

    for neutral in ("H", "M"):
        if neutral in all_groups and neutral not in matches:
            matches.append(neutral)
    return matches


def select_palette_colors(colors, groups, selected_group_ids, max_colors):
    by_group = {group_id: [] for group_id in selected_group_ids}
    for color in colors:
        group_id = color.get("group", "")
        if group_id in by_group:
            by_group[group_id].append(color)

    if not selected_group_ids:
        return []

    per_group = max(1, max_colors // len(selected_group_ids))
    selected = []
    seen = set()
    for group_id in selected_group_ids:
        picked = pick_evenly(by_group.get(group_id, []), per_group)
        for color in picked:
            add_color(selected, seen, color, groups)

    if len(selected) < max_colors:
        for color in colors:
            if color.get("group", "") not in selected_group_ids:
                continue
            add_color(selected, seen, color, groups)
            if len(selected) >= max_colors:
                break

    return selected[:max_colors]


def pick_evenly(items, limit):
    if limit <= 0 or not items:
        return []
    if len(items) <= limit:
        return list(items)
    if limit == 1:
        return [items[len(items) // 2]]
    step = (len(items) - 1) / (limit - 1)
    indexes = []
    for i in range(limit):
        index = round(i * step)
        if index not in indexes:
            indexes.append(index)
    return [items[index] for index in indexes[:limit]]


def add_color(selected, seen, color, groups):
    code = color.get("code", "")
    if not code or code in seen:
        return
    seen.add(code)
    group_id = color.get("group", "")
    group = groups.get(group_id) or {}
    selected.append({
        "code": code,
        "name": color.get("name", ""),
        "hex": color.get("hex", ""),
        "group": group_id,
        "group_label": group.get("label", group_id),
    })


def media_references(source):
    refs = []
    image = source.get("image")
    if image:
        refs.append({"type": "image", "url": image, "role": "source_card_cover"})
    source_card = source.get("source_card") or {}
    if source_card.get("image"):
        refs.append({"type": "image", "url": source_card["image"], "role": "source_card_cover"})
    for item in source.get("media_refs") or []:
        if item.get("url"):
            refs.append({
                "type": item.get("type", "media"),
                "url": item.get("url", ""),
                "role": item.get("role", "media_ref"),
            })
    for key in ("screenshot", "screenshot_path", "video", "video_url"):
        value = source.get(key)
        if value:
            media_type = "video" if "video" in key else "screenshot"
            refs.append({"type": media_type, "url": value, "role": key})
    seen = set()
    unique_refs = []
    for ref in refs:
        marker = (ref.get("type"), ref.get("url"))
        if marker in seen:
            continue
        seen.add(marker)
        unique_refs.append(ref)
    return unique_refs


def visual_lines(context):
    refs = context.get("visual_evidence", {}).get("media_refs") or []
    if not refs:
        return "- 未采集到可用原图/视频引用。"
    return "\n".join(
        f"- {item.get('type', '')}｜{item.get('role', '')}：{item.get('url', '')}"
        for item in refs
    )


def palette_lines(context):
    palette = context.get("bead_palette_reference") or {}
    if not palette.get("enabled"):
        error = palette.get("error") or "未加载。"
        return f"- 未加载真实拼豆色卡：{error}"
    selected = palette.get("selected_colors") or []
    sample = "、".join(
        f"{item.get('code')} {item.get('hex')}"
        for item in selected[:12]
    )
    return "\n".join([
        f"- 来源：{palette.get('source_url', '')}",
        f"- 品牌：{palette.get('brand_label') or palette.get('brand', '')}，共 {palette.get('total_colors', 0)} 色",
        f"- 全量缓存：{palette.get('local_cache_path', '')}",
        f"- 候选色示例：{sample or '暂无'}",
        "- 生成图纸时必须写真实 code/name/hex，不要编造色号。",
    ])


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
    parser.add_argument("--palette-url", default=DEFAULT_PALETTE_URL, help="拼豆真实色卡 palettes.json URL")
    parser.add_argument("--palette-brand", default=DEFAULT_PALETTE_BRAND, help="拼豆色卡品牌，默认 MARD")
    parser.add_argument("--palette-max-colors", type=int, default=DEFAULT_PALETTE_MAX_COLORS, help="写入上下文的候选色数量")
    parser.add_argument("--palette-timeout", type=int, default=12, help="拉取色卡超时时间（秒）")
    parser.add_argument("--no-palette", action="store_true", help="跳过真实拼豆色卡加载")
    return parser.parse_args()


if __name__ == "__main__":
    main()
