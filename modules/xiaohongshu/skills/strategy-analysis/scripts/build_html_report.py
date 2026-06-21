#!/usr/bin/env python3

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def main():
    args = parse_args()
    output = Path(args.output).resolve() if args.output else default_output(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    sections = []

    for path in args.summary:
        summary = Path(path).resolve()
        if summary.exists():
            sections.append(markdown_section(summary.stem, summary.read_text(encoding="utf-8")))

    for path in args.feishu_rows:
        source = Path(path).resolve()
        if source.exists():
            sections.append(rows_section(source))

    note_html = markdown_to_html(args.note) if args.note else ""
    report = render_html(args.title, note_html, sections)
    output.write_text(report, encoding="utf-8")
    print(json.dumps({"reportPath": str(output)}, ensure_ascii=False, indent=2))


def default_output(args):
    if args.summary:
        return Path(args.summary[0]).resolve().parent / "analysis_report.html"
    if args.feishu_rows:
        return Path(args.feishu_rows[0]).resolve().parent / "analysis_report.html"
    return Path.cwd() / "analysis_report.html"


def markdown_section(title, content):
    return {
        "title": title,
        "body": markdown_to_html(content),
    }


def rows_section(path):
    rows = json.loads(path.read_text(encoding="utf-8"))
    evidence = rows.get("tables", {}).get("样本证据表", [])
    run = first(rows.get("tables", {}).get("分析任务表", []))
    cards = []
    for item in evidence[:30]:
        cards.append(f"""
        <article class="evidence-card">
          <h3>{escape(item.get("标题", "未命名样本"))}</h3>
          <dl>
            <div><dt>互动</dt><dd>{escape(emojify_metrics(item.get("可见互动", "")) or "不可见")}</dd></div>
            <div><dt>信号</dt><dd>{escape(item.get("信号标签", "") or "未识别")}</dd></div>
            <div><dt>备注</dt><dd>{escape(item.get("备注", "") or item.get("推荐理由", "") or "暂无")}</dd></div>
          </dl>
          {link_html(item.get("URL", ""))}
        </article>
        """)
    meta = " · ".join(
        part for part in [
            run.get("平台", ""),
            run.get("关键词", ""),
            f"样本 {run.get('样本数')}" if run.get("样本数") not in (None, "") else "",
            f"详情 {run.get('详情数')}" if run.get("详情数") not in (None, "") else "",
        ]
        if part
    )
    return {
        "title": path.parent.name,
        "body": f"<p class=\"section-meta\">{escape(meta)}</p><div class=\"evidence-grid\">{''.join(cards)}</div>",
    }


def render_html(title, note_html, sections):
    created = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    section_html = "\n".join(
        f"<section><h2>{escape(section['title'])}</h2>{section['body']}</section>"
        for section in sections
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #1f2933;
      --muted: #657282;
      --line: #d9e0e8;
      --soft: #f6f8fa;
      --accent: #b42318;
      --accent-soft: #fff1f0;
      --panel: #ffffff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: var(--soft);
      line-height: 1.65;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 40px 24px 56px;
    }}
    header {{
      border-bottom: 2px solid var(--ink);
      padding-bottom: 20px;
      margin-bottom: 24px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 34px;
      line-height: 1.18;
      letter-spacing: 0;
    }}
    .meta {{
      color: var(--muted);
      font-size: 14px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
      margin-top: 18px;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 22px;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 0 0 10px;
      font-size: 16px;
      letter-spacing: 0;
    }}
    p {{ margin: 0 0 12px; }}
    ul, ol {{ margin: 8px 0 14px 22px; padding: 0; }}
    li {{ margin: 5px 0; }}
    .lead {{
      background: var(--accent-soft);
      border-color: #ffc9c2;
    }}
    .section-meta {{
      color: var(--muted);
      font-size: 14px;
      margin-bottom: 14px;
    }}
    .evidence-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }}
    .evidence-card {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 14px;
      background: #fff;
    }}
    dl {{ margin: 0; }}
    dl div {{
      display: grid;
      grid-template-columns: 48px 1fr;
      gap: 10px;
      padding: 6px 0;
      border-top: 1px solid #eef2f6;
    }}
    dl div:first-child {{ border-top: 0; }}
    dt {{
      color: var(--muted);
      font-size: 13px;
    }}
    dd {{ margin: 0; }}
    a {{ color: var(--accent); text-decoration-thickness: 1px; }}
    code {{
      background: #eef2f6;
      border-radius: 4px;
      padding: 2px 5px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92em;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>{escape(title)}</h1>
      <div class="meta">Generated at {escape(created)}</div>
    </header>
    {f'<section class="lead">{note_html}</section>' if note_html else ''}
    {section_html}
  </main>
</body>
</html>
"""


def markdown_to_html(text):
    lines = text.splitlines()
    out = []
    in_list = False
    for raw in lines:
        line = raw.strip()
        if not line:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        if line.startswith("#"):
            if in_list:
                out.append("</ul>")
                in_list = False
            level = min(len(line) - len(line.lstrip("#")), 3)
            content = line[level:].strip()
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
    return "\n".join(out)


def inline(text):
    value = escape(text)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    return value


def link_html(url):
    url = str(url or "").strip()
    if not url:
        return ""
    safe = escape(url)
    return f'<p><a href="{safe}" target="_blank" rel="noreferrer">打开原文</a></p>'


def emojify_metrics(value):
    text = str(value or "").strip()
    labels = {
        "likes": "👍",
        "like": "👍",
        "comments": "💬",
        "comment": "💬",
        "collects": "⭐",
        "favorites": "⭐",
        "shares": "🔁",
    }
    matches = re.findall(r"([A-Za-z]+):\s*([^,\s;，；]+)", text)
    parts = [f"{labels.get(key, key)} {value}" for key, value in matches]
    return " · ".join(parts) if parts else text


def first(items):
    return items[0] if items else {}


def escape(value):
    return html.escape(str(value or ""), quote=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Build a detailed HTML Xiaohongshu analysis report.")
    parser.add_argument("--title", default="小红书分析报告")
    parser.add_argument("--summary", action="append", default=[], help="summary.md path; can be repeated")
    parser.add_argument("--feishu-rows", action="append", default=[], help="feishu_rows.json path; can be repeated")
    parser.add_argument("--note", default="", help="Final analysis markdown text")
    parser.add_argument("--output", default="", help="Output HTML path")
    return parser.parse_args()


if __name__ == "__main__":
    main()
