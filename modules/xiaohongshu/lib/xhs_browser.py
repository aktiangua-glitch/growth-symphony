import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import xhs_signal as xs


GENERIC_DETAIL_TITLES = {"猜你想搜", "发现", "首页", "小红书", "登录"}


def resolve_workspace_root(script_dir):
    default_root = Path(os.environ.get("GROWTH_SYMPHONY_HOME", "/Users/admin/growth-symphony")).resolve()
    if (default_root / "modules" / "xiaohongshu").exists():
        return default_root
    path = Path(script_dir).resolve()
    for parent in [path, *path.parents]:
        if (parent / "modules" / "xiaohongshu").exists():
            return parent
    return path.parents[4]


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
        return xs.normalize_text(locator.inner_text(timeout=timeout))
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
        return xs.normalize_text(page.title())
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
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def escape_cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")[:240]


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z").replace(":", "-").replace(".", "-")


def slugify(text, fallback="item", max_len=60):
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", "-", str(text or "")).strip("-")
    return (slug or fallback)[:max_len]


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
    title_attr = xs.normalize_text(safe_attr(anchor, "title"))
    if title_attr:
        return title_attr
    return text[:80]


def first_image_url(root, base_url):
    for image in root.locator("img").all()[:3]:
        src = safe_attr(image, "src")
        if src:
            return urljoin(base_url, src)
    return None


def extract_note_cards(page, limit):
    cards = []
    seen = set()
    for anchor in page.locator("a[href]").all():
        raw_url = safe_attr(anchor, "href")
        if not raw_url:
            continue
        url = xs.canonical_note_url(urljoin(page.url, raw_url))
        if not xs.is_note_url(url):
            continue
        if not safe_box(anchor) and not safe_text(anchor):
            continue

        note_id = xs.note_id_from_url(url)
        if note_id in seen:
            continue
        seen.add(note_id)

        root = card_root(anchor)
        text = xs.normalize_text(safe_text(root) or safe_text(anchor))
        if len(text) < 3:
            continue

        title = extract_card_title(root, anchor, text)
        metrics = xs.extract_metric_hints(text)
        cards.append({
            "index": len(cards) + 1,
            "note_id": note_id,
            "title": title,
            "url": url,
            "visible_text": text[:600],
            "image": first_image_url(root, page.url),
            "signals": xs.extract_signal_tags(title, text),
            "metrics_hint": metrics,
            "metric_numbers": xs.metric_numbers(metrics),
            "engagement_ratios": xs.engagement_ratios(metrics),
            "hook_analysis": xs.analyze_hook(title),
            "content_form": xs.infer_content_form(text, url),
        })
        if len(cards) >= limit:
            break
    return cards


def extract_note_detail(page, source_card=None, comment_limit=10, tag_limit=16, body_limit=1600, page_text_limit=2200):
    source_card = source_card or {}
    page_text = safe_text(page.locator("body").first)
    raw_title = first_text_from(page.locator("h1, [class*=title]"))
    body_candidates = [
        text for text in texts_from(page.locator('[class*="desc"], [class*="content"], article, main'), limit=120)
        if len(text) > 20
    ]
    body_candidates.sort(key=len, reverse=True)
    body = body_candidates[0] if body_candidates else page_text[:body_limit]
    title = choose_detail_title(raw_title, body, safe_page_title(page), source_card)
    comments = unique([
        text for text in texts_from(page.locator('[class*="comment"]'), limit=200)
        if 2 <= len(text) <= 260
    ])[:comment_limit]
    tags = unique([
        text for text in texts_from(page.locator("a, span"), limit=700)
        if text.startswith("#") and len(text) <= 30
    ])[:tag_limit]

    visible_text = f"{title} {body} {page_text[:1200]}"
    metrics = xs.extract_metric_hints(visible_text)
    detail = {
        "url": page.url,
        "access_status": xs.detect_access_status(page.url, title, page_text),
        "title": title,
        "body_excerpt": body[:body_limit],
        "comments": comments,
        "tags": tags,
        "metrics_hint": metrics,
        "metric_numbers": xs.metric_numbers(metrics),
        "engagement_ratios": xs.engagement_ratios(metrics),
        "signals": xs.extract_signal_tags(title, body),
        "hook_analysis": xs.analyze_hook(title),
        "content_structure": xs.analyze_content_structure(body),
        "comment_patterns": xs.analyze_comment_patterns(comments),
        "content_form": xs.infer_content_form(visible_text, page.url),
        "page_text_excerpt": page_text[:page_text_limit],
        "author": extract_author(page, body),
    }
    if source_card:
        detail["source_card"] = source_card
    return detail


def choose_detail_title(raw_title, body, page_title, source_card):
    candidates = [
        raw_title,
        title_from_body(body),
        (source_card or {}).get("title", ""),
        page_title,
    ]
    for candidate in candidates:
        title = clean_title(candidate)
        if is_good_detail_title(title):
            return title
    return clean_title(candidates[0]) or clean_title(candidates[-1])


def clean_title(value):
    text = xs.normalize_text(value)
    text = re.sub(r"\s+(?:\d{2}-\d{2}|昨天|前天|\d+\s*天前|赞|回复)\b.*$", "", text)
    text = re.sub(r"\s+(?:likes|赞|收藏|评论)[:：]?\s*\d.*$", "", text, flags=re.I)
    return text[:120]


def is_good_detail_title(title):
    if not title or title in GENERIC_DETAIL_TITLES:
        return False
    if len(title) < 2:
        return False
    if re.fullmatch(r"[\d\s:：.,，/-]+", title):
        return False
    if re.search(r"共\s*\d+\s*条评论", title):
        return False
    return True


def title_from_body(body):
    text = xs.normalize_text(body)
    match = re.search(
        r"(?:LIVE\s+)*(?:\d+/\d+\s+)?(?P<author>.{1,48}?)\s+关注\s+(?P<title>.+?)(?:\s+#|\s+猜你想搜|\s+\d{2}-\d{2}\b|\s+编辑于|\s+共\s*\d+\s*条评论)",
        text,
    )
    if not match:
        return ""
    title = match.group("title")
    title = re.split(r"\s+(?:禁止|图纸来源|链接|http|编辑于|共\s*\d+\s*条评论)\b", title)[0]
    title = re.split(r"[。！？!?]", title)[0]
    return title.strip()


def extract_author(page, body):
    text = xs.normalize_text(body)
    body_author = ""
    match = re.search(r"(?:LIVE\s+)*(?:\d+/\d+\s+)?(?P<author>.{1,48}?)\s+关注\s+", text)
    if match:
        body_author = clean_author_name(match.group("author"))

    candidates = []
    for anchor in page.locator('a[href*="/user/profile/"]').all()[:20]:
        href = safe_attr(anchor, "href")
        if not href:
            continue
        name = clean_author_name(safe_text(anchor))
        score = 0
        if name and name == body_author:
            score += 10
        if "xsec_source=pc_note" in href or "parent_page_channel_type=web_profile_board" in href:
            score += 4
        if name and name != "我":
            score += 2
        if name == "我":
            score -= 8
        candidates.append({
            "score": score,
            "name": name,
            "profile_url": urljoin(page.url, href),
        })

    candidates.sort(key=lambda item: item["score"], reverse=True)
    best = candidates[0] if candidates else {}
    profile_name = body_author or best.get("name", "")

    return {
        "name": clean_author_name(profile_name),
        "profile_url": best.get("profile_url", ""),
    }


def clean_author_name(value):
    text = xs.normalize_text(value)
    text = re.sub(r"^(?:LIVE\s+)*(?:\d+/\d+\s+)?", "", text)
    text = re.sub(r"\s*关注.*$", "", text)
    return text[:80]
