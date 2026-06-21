#!/usr/bin/env python3

import argparse
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main():
    args = parse_args()
    output = Path(args.output).resolve() if args.output else default_output(args)
    output.parent.mkdir(parents=True, exist_ok=True)

    report = collect_report(args)
    output.write_text(render_html(report), encoding="utf-8")
    print(json.dumps({"reportPath": str(output)}, ensure_ascii=False, indent=2))


def collect_report(args):
    runs = [load_run(Path(path).resolve()) for path in args.feishu_rows if Path(path).exists()]
    summaries = [
        {
            "title": readable_title(Path(path).resolve()),
            "body": markdown_to_html(Path(path).resolve().read_text(encoding="utf-8")),
        }
        for path in args.summary
        if Path(path).exists()
    ]
    rows = [row for run in runs for row in run["rows"]]
    top_rows = sorted(rows, key=lambda row: row.get("likes_number") or 0, reverse=True)[:10]
    signal_counts = Counter()
    for row in rows:
        for item in split_tags(row.get("信号标签", "")):
            signal_counts[item] += 1
    stats = {
        "runs": len(runs),
        "samples": len(rows),
        "details": sum(run["details"] for run in runs),
        "visible_likes": sum(1 for row in rows if row.get("likes_text")),
        "top_like": top_rows[0]["likes_text"] if top_rows and top_rows[0].get("likes_text") else "不可见",
    }
    return {
        "title": args.title,
        "note": args.note,
        "created": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runs": runs,
        "rows": rows,
        "top_rows": top_rows,
        "signals": signal_counts.most_common(8),
        "summaries": summaries,
        "stats": stats,
    }


def load_run(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    run = first(payload.get("tables", {}).get("分析任务表", []))
    evidence = payload.get("tables", {}).get("样本证据表", [])
    schema = payload.get("schema_version", "")
    scene = infer_scene(schema, run)
    rows = []
    for item in evidence:
        row = dict(item)
        metric = parse_metrics(row.get("可见互动", ""))
        row["scene"] = scene
        row["source_label"] = f"{scene} #{row.get('排名')}" if row.get("排名") not in (None, "") else scene
        row["likes_text"] = metric.get("likes_text", "")
        row["likes_number"] = metric.get("likes_number")
        row["metric_display"] = metric_display(metric)
        rows.append(row)
    return {
        "path": str(path),
        "title": readable_title(path),
        "scene": scene,
        "keyword": run.get("关键词", ""),
        "captured_at": run.get("采集时间", ""),
        "samples": len(evidence),
        "details": number_or_zero(run.get("详情数")),
        "rows": rows,
    }


def render_html(report):
    nav = "\n".join(
        f'<a href="#{anchor}">{label}</a>'
        for anchor, label in (
            ("overview", "总览"),
            ("signals", "信号"),
            ("samples", "样本"),
            ("details", "原始摘要"),
        )
    )
    stats = report["stats"]
    stat_html = "".join(
        stat_card(label, value)
        for label, value in (
            ("采集任务", stats["runs"]),
            ("样本总数", stats["samples"]),
            ("详情页", stats["details"]),
            ("可见点赞样本", stats["visible_likes"]),
            ("最高可见点赞", stats["top_like"]),
        )
    )
    signal_html = "".join(signal_chip(name, count, stats["samples"]) for name, count in report["signals"])
    top_html = "".join(top_sample_card(row, index) for index, row in enumerate(report["top_rows"], start=1))
    table_html = "".join(sample_row(row) for row in report["rows"])
    summary_html = "".join(
        f'<section class="source-section"><h3>{escape(item["title"])}</h3>{item["body"]}</section>'
        for item in report["summaries"]
    )
    note_html = markdown_to_html(report["note"]) if report["note"] else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(report["title"])}</title>
  <style>
    :root {{
      color-scheme: light;
      --paper: #f7f5f0;
      --panel: #ffffff;
      --ink: #1d252c;
      --muted: #687481;
      --line: #d9ded8;
      --line-strong: #242b31;
      --red: #b42318;
      --red-soft: #fff0ed;
      --teal: #0f766e;
      --teal-soft: #e6f4f1;
      --amber: #9a5b00;
      --amber-soft: #fff6df;
      --shadow: 0 18px 46px rgba(29, 37, 44, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
      line-height: 1.68;
      text-wrap: pretty;
    }}
    a {{ color: inherit; text-decoration-color: rgba(180, 35, 24, 0.5); text-underline-offset: 3px; }}
    .layout {{
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      gap: 28px;
      max-width: 1320px;
      margin: 0 auto;
      padding: 28px;
    }}
    aside {{
      position: sticky;
      top: 24px;
      align-self: start;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.78);
      border-radius: 8px;
      padding: 16px;
      box-shadow: var(--shadow);
    }}
    .brand {{
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 12px;
    }}
    nav {{
      display: grid;
      gap: 6px;
    }}
    nav a {{
      display: block;
      padding: 9px 10px;
      border-radius: 6px;
      text-decoration: none;
      color: var(--ink);
      font-weight: 600;
    }}
    nav a:hover {{ background: var(--teal-soft); }}
    main {{ min-width: 0; }}
    header {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 32px;
      box-shadow: var(--shadow);
    }}
    .eyebrow {{
      color: var(--red);
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 10px;
    }}
    h1 {{
      margin: 0;
      max-width: 900px;
      font-size: clamp(34px, 5vw, 64px);
      line-height: 1.05;
      letter-spacing: 0;
    }}
    .subtitle {{
      max-width: 820px;
      margin: 18px 0 0;
      color: var(--muted);
      font-size: 18px;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 22px;
      color: var(--muted);
      font-size: 13px;
    }}
    .meta span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      background: #fbfaf6;
    }}
    section {{
      margin-top: 22px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 26px;
      box-shadow: var(--shadow);
    }}
    h2 {{
      margin: 0 0 16px;
      font-size: 26px;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 0 0 10px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    p {{ margin: 0 0 12px; }}
    ul, ol {{ margin: 8px 0 16px 22px; padding: 0; }}
    li {{ margin: 5px 0; }}
    .note {{
      border-top: 4px solid var(--red);
      background: var(--red-soft);
    }}
    .stat-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin-top: 18px;
    }}
    .stat-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      background: #fbfaf6;
    }}
    .stat-label {{
      color: var(--muted);
      font-size: 12px;
    }}
    .stat-value {{
      margin-top: 6px;
      font-size: 24px;
      font-weight: 800;
    }}
    .signal-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
    }}
    .signal-chip {{
      border: 1px solid #b7d7d1;
      background: var(--teal-soft);
      border-radius: 8px;
      padding: 14px;
    }}
    .signal-chip strong {{
      display: block;
      color: var(--teal);
      font-size: 19px;
    }}
    .bar {{
      margin-top: 10px;
      height: 8px;
      border-radius: 999px;
      background: rgba(15, 118, 110, 0.14);
      overflow: hidden;
    }}
    .bar i {{
      display: block;
      height: 100%;
      background: var(--teal);
    }}
    .top-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 14px;
    }}
    .sample-card {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 16px;
    }}
    .rank {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      border-radius: 50%;
      background: var(--ink);
      color: white;
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 12px;
    }}
    .metric {{
      display: inline-block;
      margin: 10px 8px 0 0;
      padding: 5px 9px;
      border-radius: 999px;
      background: var(--amber-soft);
      color: var(--amber);
      font-weight: 700;
      font-size: 13px;
    }}
    .tagline {{
      color: var(--muted);
      font-size: 14px;
      margin-top: 8px;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 980px;
      background: #fff;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid #edf0ed;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #f8f8f4;
      z-index: 1;
      color: var(--muted);
      font-size: 12px;
      letter-spacing: 0.04em;
    }}
    td:first-child {{
      font-weight: 700;
      min-width: 260px;
    }}
    .source-section {{
      margin-top: 14px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fbfaf6;
      box-shadow: none;
    }}
    .source-section table {{
      min-width: 760px;
      margin-top: 10px;
    }}
    code {{
      background: #edf0ed;
      border-radius: 4px;
      padding: 2px 5px;
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 0.92em;
    }}
    @media (max-width: 980px) {{
      .layout {{
        grid-template-columns: 1fr;
        padding: 16px;
      }}
      aside {{
        position: static;
      }}
      nav {{
        grid-template-columns: repeat(4, minmax(0, 1fr));
      }}
      header, section {{
        padding: 20px;
      }}
      .stat-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 560px) {{
      nav {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .stat-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <div class="brand">Growth Symphony</div>
      <nav>{nav}</nav>
    </aside>
    <main>
      <header id="overview">
        <div class="eyebrow">小红书运营研究报告</div>
        <h1>{escape(report["title"])}</h1>
        <p class="subtitle">把浏览器可见样本整理成可复盘的运营判断：多维表用于筛选样本，HTML 报告用于阅读结论和证据。</p>
        <div class="meta">
          <span>生成时间 {escape(report["created"])}</span>
          <span>数据来源 浏览器可见采样</span>
          <span>不可见指标不补数</span>
        </div>
        <div class="stat-grid">{stat_html}</div>
      </header>
      {f'<section class="note"><h2>核心判断</h2>{note_html}</section>' if note_html else ''}
      <section id="signals">
        <h2>高频内容信号</h2>
        <div class="signal-grid">{signal_html}</div>
      </section>
      <section>
        <h2>高互动样本</h2>
        <div class="top-grid">{top_html}</div>
      </section>
      <section id="samples">
        <h2>样本矩阵</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>标题</th>
                <th>来源</th>
                <th>互动</th>
                <th>信号</th>
                <th>备注</th>
                <th>链接</th>
              </tr>
            </thead>
            <tbody>{table_html}</tbody>
          </table>
        </div>
      </section>
      <section id="details">
        <h2>原始采集摘要</h2>
        {summary_html}
      </section>
    </main>
  </div>
</body>
</html>
"""


def stat_card(label, value):
    return f"""
    <div class="stat-card">
      <div class="stat-label">{escape(label)}</div>
      <div class="stat-value">{escape(value)}</div>
    </div>
    """


def signal_chip(name, count, total):
    width = 8 if not total else max(8, min(100, round(count / total * 100)))
    return f"""
    <div class="signal-chip">
      <strong>{escape(name)}</strong>
      <span>{count} 个样本出现</span>
      <div class="bar"><i style="width:{width}%"></i></div>
    </div>
    """


def top_sample_card(row, index):
    metric = row.get("metric_display") or "互动不可见"
    return f"""
    <article class="sample-card">
      <span class="rank">{index}</span>
      <h3>{escape(row.get("标题", "未命名样本"))}</h3>
      <div class="metric">{escape(metric)}</div>
      <p class="tagline">{escape(row.get("信号标签", "") or "未识别信号")}</p>
      <p class="tagline">{escape(row.get("source_label", ""))}</p>
    </article>
    """


def sample_row(row):
    url = str(row.get("URL", "") or "").strip()
    link = f'<a href="{escape(url)}" target="_blank" rel="noreferrer">打开</a>' if url else "无"
    return f"""
    <tr>
      <td>{escape(row.get("标题", ""))}</td>
      <td>{escape(row.get("source_label", ""))}</td>
      <td>{escape(row.get("metric_display", "") or "不可见")}</td>
      <td>{escape(row.get("信号标签", "") or "未识别")}</td>
      <td>{escape(row.get("备注", "") or row.get("推荐理由", "") or "暂无")}</td>
      <td>{link}</td>
    </tr>
    """


def parse_metrics(value):
    text = str(value or "").strip()
    result = {}
    for key, raw_value in re.findall(r"([A-Za-z\u4e00-\u9fff]+):\s*([^,\s;，；]+)", text):
        normalized = normalize_metric_key(key)
        result[f"{normalized}_text"] = raw_value
        number = parse_count(raw_value)
        if number is not None:
            result[f"{normalized}_number"] = number
    return result


def metric_display(metric):
    labels = {
        "likes": "点赞",
        "comments": "评论",
        "collects": "收藏",
        "shares": "分享",
    }
    parts = []
    for key in ("likes", "collects", "comments", "shares"):
        value = metric.get(f"{key}_text")
        if value:
            parts.append(f"{labels[key]} {value}")
    return " · ".join(parts)


def normalize_metric_key(key):
    key = key.lower()
    mapping = {
        "like": "likes",
        "likes": "likes",
        "点赞": "likes",
        "赞": "likes",
        "comment": "comments",
        "comments": "comments",
        "评论": "comments",
        "collect": "collects",
        "collects": "collects",
        "favorite": "collects",
        "favorites": "collects",
        "收藏": "collects",
        "share": "shares",
        "shares": "shares",
        "分享": "shares",
    }
    return mapping.get(key, key)


def parse_count(value):
    text = str(value or "").strip().lower().replace("+", "")
    match = re.match(r"([\d.]+)\s*([万w亿k千]?)", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit in ("万", "w"):
        number *= 10_000
    elif unit == "亿":
        number *= 100_000_000
    elif unit in ("k", "千"):
        number *= 1_000
    return int(number)


def infer_scene(schema, run):
    keyword = str(run.get("关键词", "") or "").strip()
    if "search_hot" in schema:
        return f"关键词搜索：{keyword}" if keyword else "关键词搜索"
    if "home_feed" in schema:
        return "首页推荐流"
    if "account_scan" in schema:
        return "账号体检样本"
    if "keyword_matrix" in schema:
        return "关键词矩阵"
    if "note_detail" in schema:
        return "笔记深挖"
    return keyword or "小红书分析"


def markdown_to_html(text):
    lines = text.splitlines()
    out = []
    in_list = False
    in_table = False
    table_rows = []
    for raw in lines:
        line = raw.strip()
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            if in_table:
                out.append(render_markdown_table(table_rows))
                table_rows = []
                in_table = False
            continue
        if "|" in line and line.startswith("|") and line.endswith("|"):
            if in_list:
                out.append("</ul>")
                in_list = False
            in_table = True
            table_rows.append(line)
            continue
        if in_table:
            out.append(render_markdown_table(table_rows))
            table_rows = []
            in_table = False
        if line.startswith("#"):
            level = min(len(line) - len(line.lstrip("#")) + 2, 4)
            content = line[len(line) - len(line.lstrip("#")):].strip()
            out.append(f"<h{level}>{inline(content)}</h{level}>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(line[2:])}</li>")
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    if in_table:
        out.append(render_markdown_table(table_rows))
    return "\n".join(out)


def render_markdown_table(rows):
    clean_rows = []
    for row in rows:
        cells = [cell.strip().replace("\\|", "|") for cell in row.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        clean_rows.append(cells)
    if not clean_rows:
        return ""
    head = clean_rows[0]
    body = clean_rows[1:]
    head_html = "".join(f"<th>{inline(cell)}</th>" for cell in head)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>"
        for row in body
    )
    return f'<div class="table-wrap"><table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table></div>'


def inline(text):
    value = escape(text)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    return value


def split_tags(value):
    text = str(value or "")
    return [item.strip() for item in re.split(r"、|/|,", text) if item.strip()]


def readable_title(path):
    return path.parent.name if path.name in {"feishu_rows.json", "summary.md"} else path.stem


def first(items):
    return items[0] if items else {}


def number_or_zero(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def escape(value):
    return html.escape(str(value or ""), quote=True)


def default_output(args):
    if args.summary:
        return Path(args.summary[0]).resolve().parent / "analysis_report.html"
    if args.feishu_rows:
        return Path(args.feishu_rows[0]).resolve().parent / "analysis_report.html"
    return Path.cwd() / "analysis_report.html"


def parse_args():
    parser = argparse.ArgumentParser(description="Build a designed Xiaohongshu HTML analysis report.")
    parser.add_argument("--title", default="小红书分析报告")
    parser.add_argument("--summary", action="append", default=[], help="summary.md path; can be repeated")
    parser.add_argument("--feishu-rows", action="append", default=[], help="feishu_rows.json path; can be repeated")
    parser.add_argument("--note", default="", help="Final analysis markdown text")
    parser.add_argument("--output", default="", help="Output HTML path")
    return parser.parse_args()


if __name__ == "__main__":
    main()
