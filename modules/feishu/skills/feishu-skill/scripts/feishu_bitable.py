#!/usr/bin/env python3

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_TABLES = ("分析任务表", "样本证据表")
COMPACT_FIELDS = ("标题", "备注", "可见互动", "信号标签", "选题方向", "URL", "来源场景", "采集时间")


def main():
    args = parse_args()
    source = Path(args.input).resolve()
    if not source.exists():
        raise SystemExit(f"文件不存在：{source}")

    rows = json.loads(source.read_text(encoding="utf-8"))
    validate_rows(rows)

    out_dir = Path(args.out_dir).resolve() if args.out_dir else source.parent / "feishu_payload"
    out_dir.mkdir(parents=True, exist_ok=True)

    config = load_config()
    manifest = build_manifest(rows, source, out_dir, config)
    compact_rows = build_compact_rows(rows)
    write_payload_files(rows, compact_rows, out_dir, manifest)

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.execute:
        if not manifest["ready_to_write"]:
            raise SystemExit("飞书多维表未配置完整，已生成本地待导入包，未执行写入。")
        cli = find_feishu_cli()
        if not cli:
            raise SystemExit("未找到飞书 CLI，已生成本地待导入包，未执行写入。")
        manifest["write_results"] = write_tables(cli, compact_rows, config)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "payloadDir": str(out_dir),
        "manifestPath": str(manifest_path),
        "readyToWrite": manifest["ready_to_write"],
        "missingConfig": manifest["missing_config"],
        "tables": manifest["tables"],
        "writeResults": manifest.get("write_results", []),
    }, ensure_ascii=False, indent=2))


def validate_rows(rows):
    schema = rows.get("schema_version", "")
    if not schema.startswith("xhs.") or ".feishu_rows.v" not in schema:
        raise SystemExit(f"不支持的 schema_version：{schema}")
    tables = rows.get("tables")
    if not isinstance(tables, dict):
        raise SystemExit("缺少 tables 对象。")
    for name in REQUIRED_TABLES:
        value = tables.get(name)
        if not isinstance(value, list):
            raise SystemExit(f"缺少表数据：{name}")
        for index, row in enumerate(value, start=1):
            if not isinstance(row, dict):
                raise SystemExit(f"{name} 第 {index} 行不是对象。")


def load_config():
    return {
        "app_token": os.environ.get("FEISHU_BITABLE_APP_TOKEN", ""),
        "analysis_table_id": os.environ.get("FEISHU_ANALYSIS_TABLE_ID", ""),
        "evidence_table_id": os.environ.get("FEISHU_EVIDENCE_TABLE_ID", ""),
    }


def build_manifest(rows, source, out_dir, config):
    missing = [key for key, value in config.items() if not value]
    compact_count = len(rows["tables"].get("样本证据表", []))
    tables = {
        "小红书分析": {
            "table_id": config.get("evidence_table_id", ""),
            "rows": compact_count,
            "payload_file": str(out_dir / "compact_rows.json"),
        },
    }
    app_token = config.get("app_token", "")
    return {
        "schema_version": "feishu.bitable_payload.v1",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_file": str(source),
        "app_token": app_token,
        "base_url": f"https://www.feishu.cn/base/{app_token}" if app_token else "",
        "ready_to_write": not missing,
        "missing_config": missing,
        "tables": tables,
        "rules": [
            "多维表只写 8 列概要索引",
            "主键/首列使用文章标题",
            "详细分析写入 HTML 报告，不塞进多维表",
        ],
    }


def write_payload_files(rows, compact_rows, out_dir, manifest):
    shutil.copyfile(manifest["source_file"], out_dir / "source_feishu_rows.json")
    (out_dir / "compact_rows.json").write_text(
        json.dumps(compact_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_feishu_cli():
    for name in ("lark-cli", "feishu-cli", "feishu", "lark"):
        found = shutil.which(name)
        if found:
            return found
    return ""


def write_tables(cli, compact_rows, config):
    results = []
    table_id = config["evidence_table_id"]
    for batch_index, batch in enumerate(chunks(compact_rows, 200), start=1):
        result = write_batch(cli, config["app_token"], table_id, batch)
        results.append({
            "table": "小红书分析",
            "table_id": table_id,
            "batch": batch_index,
            "rows": len(batch),
            "ok": result.get("ok", False),
            "identity": result.get("identity", ""),
            "error": result.get("error", {}),
        })
    return results


def write_batch(cli, app_token, table_id, rows):
    if not rows:
        return {"ok": True, "identity": "", "data": {"records": []}}
    fields = [field for field in COMPACT_FIELDS if field in rows[0]]
    payload = {
        "fields": fields,
        "rows": [[row.get(field) for field in fields] for row in rows],
    }
    result = subprocess.run(
        [
            cli,
            "base",
            "+record-batch-create",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(payload, ensure_ascii=False),
            "--format",
            "json",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output = (result.stdout or result.stderr or "").strip()
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        parsed = {"ok": False, "error": {"message": output}}
    if result.returncode != 0 and parsed.get("ok") is not False:
        parsed["ok"] = False
    if not parsed.get("ok", False):
        raise SystemExit(f"飞书写入失败：{json.dumps(parsed.get('error', parsed), ensure_ascii=False)}")
    return parsed


def chunks(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def build_compact_rows(rows):
    schema = rows.get("schema_version", "")
    run_row = first_item(rows["tables"].get("分析任务表", []))
    source_scene = infer_source_scene(schema, run_row)
    captured_at = run_row.get("采集时间", "")
    compact = []
    for evidence in rows["tables"].get("样本证据表", []):
        title = clean_text(evidence.get("标题", ""))
        if not title:
            continue
        rank = evidence.get("排名")
        scene = source_scene if rank in (None, "") else f"{source_scene} #{rank}"
        note = join_parts(evidence.get("备注", ""), evidence.get("推荐理由", ""))
        compact.append({
            "标题": title,
            "备注": note,
            "可见互动": emojify_metrics(evidence.get("可见互动", "")),
            "信号标签": clean_text(evidence.get("信号标签", "")),
            "选题方向": clean_text(evidence.get("选题方向", "")),
            "URL": clean_text(evidence.get("URL", "")),
            "来源场景": scene,
            "采集时间": captured_at,
        })
    return compact


def infer_source_scene(schema, run_row):
    keyword = clean_text(run_row.get("关键词", ""))
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


def emojify_metrics(value):
    text = clean_text(value)
    if not text:
        return ""
    labels = {
        "likes": "👍",
        "like": "👍",
        "点赞": "👍",
        "comments": "💬",
        "comment": "💬",
        "评论": "💬",
        "collects": "⭐",
        "favorites": "⭐",
        "favorite": "⭐",
        "收藏": "⭐",
        "shares": "🔁",
        "share": "🔁",
        "分享": "🔁",
    }
    matches = re.findall(r"([A-Za-z\u4e00-\u9fff]+):\s*([^,\s;，；]+)", text)
    parts = [f"{labels.get(key, key)} {value}" for key, value in matches]
    if parts:
        return " · ".join(parts)
    return text


def first_item(items):
    return items[0] if items else {}


def join_parts(*items):
    parts = [clean_text(item) for item in items if clean_text(item)]
    return "；".join(dict.fromkeys(parts))


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def parse_args():
    parser = argparse.ArgumentParser(description="验证 feishu_rows.json 并生成飞书多维表待导入包")
    parser.add_argument("--input", required=True, help="feishu_rows.json 路径")
    parser.add_argument("--out-dir", default="", help="输出待导入包目录，默认在输入文件旁边")
    parser.add_argument("--execute", action="store_true", help="配置完整后才允许尝试写入；当前默认不执行")
    return parser.parse_args()


if __name__ == "__main__":
    main()
