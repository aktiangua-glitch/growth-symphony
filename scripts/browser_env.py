#!/usr/bin/env python3

import argparse
import json
import re
import subprocess


def main():
    args = parse_args()
    if args.command == "list":
        profiles = list_profiles()
        print_json({"profiles": profiles, "count": len(profiles)})
        return

    if args.command == "resolve":
        profiles = list_profiles()
        matched = resolve_profile(profiles, args.profile)
        if not matched:
            raise SystemExit(f"未找到浏览器环境：{args.profile}")
        print_json({"profile": matched})
        return

    if args.command == "cdp":
        profiles = list_profiles()
        matched = resolve_profile(profiles, args.profile)
        if not matched:
            raise SystemExit(f"未找到浏览器环境：{args.profile}")
        cdp = get_cdp_endpoint(matched["profile_id"], start_if_needed=not args.no_start)
        print_json({"profile": matched, "cdp_endpoint": cdp})
        return

    raise SystemExit(f"未知命令：{args.command}")


def list_profiles():
    raw = run_ads(["get-browser-list", "{}"])
    payload = parse_json_payload(raw)
    rows = extract_profile_rows(payload)
    profiles = []
    for row in rows:
        item = normalize_profile(row)
        if item.get("profile_id"):
            profiles.append(item)
    return profiles


def run_ads(args):
    try:
        result = subprocess.run(
            ["ads", *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise SystemExit("缺少 ads CLI。请先安装并确认 `ads --version` 可用。") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise SystemExit(f"ads CLI 执行失败：{message}") from exc
    return result.stdout


def parse_json_payload(text):
    text = (text or "").strip()
    if not text:
        return {}
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    matches = []
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        matches.append((end, value))
    if not matches:
        raise json.JSONDecodeError("未找到可解析 JSON", text, 0)

    def score(item):
        span, value = item
        if isinstance(value, dict):
            if isinstance(value.get("list"), list):
                return (3, span)
            data = value.get("data")
            if isinstance(data, dict) and any(isinstance(v, list) for v in data.values()):
                return (2, span)
            if isinstance(value.get("profiles"), list):
                return (2, span)
        if isinstance(value, list):
            return (1, span)
        return (0, span)

    return max(matches, key=score)[1]


def extract_profile_rows(payload):
    candidates = [
        payload,
        payload.get("data") if isinstance(payload, dict) else None,
        payload.get("list") if isinstance(payload, dict) else None,
        payload.get("data", {}).get("list") if isinstance(payload, dict) else None,
        payload.get("data", {}).get("items") if isinstance(payload, dict) else None,
        payload.get("profiles") if isinstance(payload, dict) else None,
    ]
    for item in candidates:
        if isinstance(item, list):
            return item
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def normalize_profile(row):
    return {
        "name": str(first(row, "name", "profile_name", "user_name") or ""),
        "profile_id": str(first(row, "profile_id", "user_id", "id") or ""),
        "profile_no": str(first(row, "profile_no", "serial_number", "seq", "no") or ""),
        "group_name": str(first(row, "group_name", "group", "groupName") or ""),
        "last_open_time": str(first(row, "last_open_time", "lastOpenTime", "updated_at") or ""),
    }


def first(row, *keys):
    if not isinstance(row, dict):
        return ""
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def resolve_profile(profiles, query):
    query = str(query or "").strip()
    if not query:
        return None
    for key in ("profile_id", "profile_no", "name"):
        exact = [item for item in profiles if item.get(key) == query]
        if len(exact) == 1:
            return exact[0]
    fuzzy = [item for item in profiles if query in item.get("name", "")]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        names = ", ".join(f"{item.get('name')}({item.get('profile_id')})" for item in fuzzy[:8])
        raise SystemExit(f"匹配到多个浏览器环境，请更精确：{names}")
    return None


def get_cdp_endpoint(profile_id, start_if_needed=True):
    active = run_ads_json("get-browser-active", {"profile_id": profile_id})
    cdp = extract_cdp(active)
    if cdp:
        return cdp
    if not start_if_needed:
        raise SystemExit("浏览器环境未启动，且已设置 --no-start。")
    started = run_ads_json("open-browser", {"profile_id": profile_id})
    cdp = extract_cdp(started)
    if not cdp:
        raise SystemExit("未能从 ADSPower 返回值里取得 CDP endpoint。")
    return cdp


def run_ads_json(command, params):
    return parse_json_payload(run_ads([command, json.dumps(params, ensure_ascii=False)]))


def extract_cdp(payload):
    if not isinstance(payload, dict):
        return ""
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        data = {}
    ws = data.get("ws", {}) if isinstance(data, dict) else {}
    for value in (
        ws.get("puppeteer") if isinstance(ws, dict) else "",
        ws.get("playwright") if isinstance(ws, dict) else "",
        data.get("ws", {}).get("puppeteer") if isinstance(data.get("ws"), dict) else "",
        data.get("debug_port") if isinstance(data, dict) else "",
    ):
        if value:
            if isinstance(value, int) or str(value).isdigit():
                return f"http://127.0.0.1:{value}"
            return str(value)
    return ""


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description="管理 ADSPower 浏览器环境并输出 CDP endpoint")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出浏览器环境")
    resolve = sub.add_parser("resolve", help="按环境名、编号或 profile_id 匹配环境")
    resolve.add_argument("profile", help="环境名、编号或 profile_id")
    cdp = sub.add_parser("cdp", help="取得指定环境的 CDP endpoint")
    cdp.add_argument("profile", help="环境名、编号或 profile_id")
    cdp.add_argument("--no-start", action="store_true", help="环境未启动时不自动启动")
    return parser.parse_args()


if __name__ == "__main__":
    main()
