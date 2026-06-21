import re
from urllib.parse import urlparse, urlunparse


NUMBER_TEXT = r"([\d]+(?:[.,]\d+)?\s*(?:万|亿|千|[kKwW])?)"

EMOTION_WORDS = [
    "太香了", "绝了", "震惊", "真香", "上头", "离谱", "爆了",
    "神了", "炸裂", "天花板", "好看", "治愈", "崩溃", "哭了",
]

IDENTITY_MARKERS = [
    "新手", "小白", "学生党", "上班族", "宝妈", "打工人", "普通人",
    "手残党", "懒人", "姐妹", "妈妈", "孩子", "自担", "同担",
]

CONTRAST_PATTERNS = [
    r"不是.{1,10}才",
    r"竟然",
    r"居然",
    r"没想到",
    r"万万没想到",
    r"以为.{1,12}(其实|结果|没想到)",
    r"才发现",
    r"原来",
]

DEMAND_PATTERNS = {
    "求资源": r"求|蹲|链接|图纸|模板|清单|发我|在哪",
    "教程需求": r"教程|怎么|如何|步骤|可以教|出一期|求教",
    "购买价格": r"多少钱|价格|买|店铺|平替|同款",
    "材料工具": r"材料|工具|设备|软件|尺寸|参数|温度|时间|型号",
    "效果反馈": r"好看|喜欢|绝|有用|学会|成功|失败|翻车",
    "风险疑问": r"踩坑|避雷|风险|会不会|安全吗|靠谱吗|真的假的",
    "身份场景": r"学生|上班|新手|小白|宝妈|同事|朋友|自担|孩子",
}


def normalize_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def canonical_note_url(url):
    parsed = urlparse(url)
    match = re.match(r"^/search_result/([a-zA-Z0-9]+)", parsed.path)
    if not match:
        match = re.match(r"^/user/profile/[a-zA-Z0-9]+/([a-zA-Z0-9]+)", parsed.path)
    if not match:
        return url
    path = f"/explore/{match.group(1)}"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, parsed.fragment))


def is_note_url(url):
    return bool(re.search(r"/(?:search_result|explore|discovery/item)/[a-zA-Z0-9]+", url)) or bool(
        re.search(r"/user/profile/[a-zA-Z0-9]+/[a-zA-Z0-9]+", url)
    )


def note_id_from_url(url):
    match = re.search(r"/(?:explore|search_result|discovery/item)/([a-zA-Z0-9]+)", url)
    if not match:
        match = re.search(r"/user/profile/[a-zA-Z0-9]+/([a-zA-Z0-9]+)", url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    return parsed.path.strip("/").split("/")[-1] or "note"


def parse_count_value(value):
    if isinstance(value, (int, float)):
        return int(value)
    raw = str(value or "").replace(",", "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([万亿千kKwW]?)", raw)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    multiplier = 1
    if unit in ("w", "万"):
        multiplier = 10_000
    elif unit == "亿":
        multiplier = 100_000_000
    elif unit in ("k", "千"):
        multiplier = 1_000
    return int(number * multiplier)


def extract_metric_hints(text):
    source = normalize_text(text)
    metrics = {}
    patterns = {
        "likes": [
            rf"(?:赞|点赞|喜欢|获赞)\s*[:：]?\s*{NUMBER_TEXT}",
            rf"{NUMBER_TEXT}\s*(?:赞|点赞|喜欢)",
        ],
        "collects": [
            rf"(?:收藏|获赞与收藏|赞藏)\s*[:：]?\s*{NUMBER_TEXT}",
            rf"{NUMBER_TEXT}\s*(?:收藏|赞藏)",
        ],
        "comments": [
            rf"(?:评论|留言)\s*[:：]?\s*{NUMBER_TEXT}",
            rf"{NUMBER_TEXT}\s*(?:评论|留言)",
        ],
        "shares": [
            rf"(?:分享|转发)\s*[:：]?\s*{NUMBER_TEXT}",
            rf"{NUMBER_TEXT}\s*(?:分享|转发)",
        ],
        "followers": [
            rf"(?:粉丝)\s*[:：]?\s*{NUMBER_TEXT}",
            rf"{NUMBER_TEXT}\s*(?:粉丝)",
        ],
    }
    for key, key_patterns in patterns.items():
        for pattern in key_patterns:
            match = re.search(pattern, source)
            if match:
                metrics[key] = normalize_text(match.group(1))
                break

    if "likes" not in metrics:
        tail_match = re.search(rf"(?:^|\s){NUMBER_TEXT}\s*$", source)
        if tail_match:
            metrics["likes"] = normalize_text(tail_match.group(1))
    return metrics


def metric_numbers(metrics):
    result = {}
    for key, value in (metrics or {}).items():
        parsed = parse_count_value(value)
        if parsed is not None:
            result[key] = parsed
    return result


def engagement_ratios(metrics):
    numbers = metric_numbers(metrics)
    likes = numbers.get("likes") or 0
    if likes <= 0:
        return {}

    ratios = {"likes": likes}
    labels = []
    if "collects" in numbers:
        pct = round(numbers["collects"] / likes * 100, 2)
        ratios["collect_like_pct"] = pct
        if pct > 40:
            labels.append("工具收藏型")
        elif pct >= 20:
            labels.append("认知收藏型")
        else:
            labels.append("轻消费型")
    if "comments" in numbers:
        pct = round(numbers["comments"] / likes * 100, 2)
        ratios["comment_like_pct"] = pct
        if pct > 15:
            labels.append("讨论驱动型")
        elif pct >= 5:
            labels.append("正常互动型")
        else:
            labels.append("围观点赞型")
    if "shares" in numbers:
        pct = round(numbers["shares"] / likes * 100, 2)
        ratios["share_like_pct"] = pct
        if pct > 10:
            labels.append("转发货币型")
    if labels:
        ratios["ratio_labels"] = labels
    return ratios


def analyze_hook(title):
    text = normalize_text(title)
    patterns = []
    if re.search(r"\d+|[一二三四五六七八九十]+", text):
        patterns.append("数字钩子")
    if re.search(r"[?？]", text):
        patterns.append("提问钩子")
    if re.search(r"[!！]", text):
        patterns.append("感叹强化")
    if re.search(r"清单|合集|盘点|TOP|top|第[一二三四五六七八九十\d]+|[①②③④⑤⑥⑦⑧⑨⑩]", text):
        patterns.append("清单结构")
    if any(word in text for word in IDENTITY_MARKERS):
        patterns.append("身份钩子")
    if any(word in text for word in EMOTION_WORDS):
        patterns.append("情绪词")
    if any(re.search(pattern, text) for pattern in CONTRAST_PATTERNS):
        patterns.append("反差钩子")
    if re.search(r"第[一二三四五六七八九十\d]+[期篇章集部]|Part\s*\d+|P\d+", text, re.I):
        patterns.append("系列连载")
    if re.search(r"[\U0001F300-\U0001FAFF]", text):
        patterns.append("表情符号")
    return {
        "title_length": len(text),
        "hook_patterns": patterns,
    }


def analyze_content_structure(text):
    raw = str(text or "")
    normalized = normalize_text(raw)
    hashtags = re.findall(r"#[^\s#]+", raw)
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n|\n", raw) if item.strip()]
    return {
        "body_length": len(normalized),
        "paragraph_count": len(paragraphs) or (1 if normalized else 0),
        "hashtag_count": len(hashtags),
        "hashtags": hashtags[:12],
        "has_call_to_action": bool(re.search(r"评论区|留言|收藏|关注|私信|蹲|求|你觉得|你会", normalized)),
        "uses_list_or_steps": bool(re.search(r"(\d+[.、]|[一二三四五六七八九十]+[.、]|步骤|第一|第二|第三)", normalized)),
    }


def analyze_comment_patterns(comments):
    values = [normalize_text(item) for item in (comments or []) if normalize_text(item)]
    theme_counts = []
    joined = " ".join(values)
    for name, pattern in DEMAND_PATTERNS.items():
        count = len(re.findall(pattern, joined))
        if count:
            theme_counts.append({"theme": name, "count": count})
    theme_counts.sort(key=lambda item: item["count"], reverse=True)

    question_examples = [
        item for item in values
        if re.search(r"[?？]|怎么|如何|哪里|能不能|可以吗|求", item)
    ][:5]
    avg_length = round(sum(len(item) for item in values) / len(values), 1) if values else 0
    return {
        "total_visible": len(values),
        "question_count": len(question_examples),
        "question_rate": round(len(question_examples) / len(values) * 100, 2) if values else 0,
        "themes": theme_counts[:8],
        "question_examples": question_examples,
        "avg_comment_length": avg_length,
    }


def extract_signal_tags(title, text):
    joined = normalize_text(f"{title} {text}")
    signals = []
    checks = [
        ("教程方法", r"教程|方法|步骤|怎么|如何|入门|手把手"),
        ("资源模板", r"模板|清单|合集|图纸|链接|资料|素材"),
        ("避坑预警", r"避坑|别|不要|后悔|踩坑|避雷"),
        ("对比测评", r"测评|对比|横评|值不值|优缺点|哪个好"),
        ("数字表达", r"\d+|[一二三四五六七八九十]+"),
        ("提问钩子", r"[?？]"),
        ("身份人群", "|".join(map(re.escape, IDENTITY_MARKERS))),
        ("情绪强钩子", "|".join(map(re.escape, EMOTION_WORDS))),
        ("反差转折", "|".join(CONTRAST_PATTERNS)),
        ("系列连载", r"第[一二三四五六七八九十\d]+[期篇章集部]|Part\s*\d+|P\d+"),
        ("种草好物", r"好物|种草|同款|推荐|平替|买"),
        ("评论引导", r"评论区|留言|蹲|求|私信"),
        ("价格成本", r"价格|多少钱|预算|成本|省钱|平价"),
        ("效果展示", r"成品|效果|前后|出炉|展示|完成|成果"),
    ]
    for name, pattern in checks:
        if pattern and re.search(pattern, joined, re.I):
            signals.append(name)
    return signals


def infer_content_form(text, url=""):
    joined = normalize_text(f"{text} {url}")
    if re.search(r"视频|播放|video", joined, re.I):
        return "视频"
    if re.search(r"图文|图片|封面|配图|笔记", joined):
        return "图文"
    return "不可见"


def metrics_text(metrics):
    if not metrics:
        return ""
    return " ".join(f"{key}:{value}" for key, value in metrics.items())


def detect_access_status(url, title, page_text):
    joined = f"{url} {title} {page_text}"
    if re.search(r"当前笔记暂时无法浏览|error_code=|/404|页面不存在|内容无法查看", joined):
        return "unavailable"
    if re.search(r"登录后查看|请先登录|登录后", joined):
        return "login_required"
    if re.search(r"广告屏蔽插件|移除插件|加入插件白名单", joined):
        return "blocked_by_page"
    return "visible"
