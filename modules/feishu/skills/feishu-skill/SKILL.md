---
name: feishu-skill
description: 使用飞书 CLI 操作飞书能力，并将固定格式的 `feishu_rows.json` 写入固定飞书多维表。Use when 用户要求通过飞书 CLI 写入多维表/Base、导入小红书分析结果、导入运营分析样本、处理 `feishu_rows.json`。
---

# Feishu Skill

用飞书 CLI 执行飞书操作。当前核心功能：验证 `feishu_rows.json`，生成多维表待导入包；飞书固定 ID 配好后再写入固定多维表。

## CLI

优先使用本机已安装的飞书 CLI。执行前先确认命令存在：

```bash
command -v lark-cli || command -v feishu-cli || command -v feishu || command -v lark
```

没有可用 CLI 时，停下来说明缺少 CLI，不伪造写入成功。

安装官方 CLI：

```bash
npm install -g @larksuite/cli
```

## 固定多维表

用环境变量配置，不写入仓库：

```bash
FEISHU_BITABLE_APP_TOKEN
FEISHU_ANALYSIS_TABLE_ID
FEISHU_EVIDENCE_TABLE_ID
```

如果任一值缺失，先生成本地待导入包，不声明写入成功。

获取方式：

- 打开普通飞书多维表，URL 形如 `https://xxx.feishu.cn/base/<app_token>?table=<table_id>&view=...`。
- `app_token` 是 `/base/` 后面的那段。
- `table_id` 是 URL 里的 `table=` 参数。
- 切到“分析任务表”复制一次 URL，拿分析任务表 table id。
- 切到“样本证据表”复制一次 URL，拿样本证据表 table id。
- 如果链接是 `/wiki/`，先让用户换成普通 `/base/` 多维表，v1 不处理 wiki token 解析。

## 导入 `feishu_rows.json`

未配置飞书多维表前，先执行本地打包：

```bash
python3 modules/feishu/skills/feishu-skill/scripts/feishu_bitable.py --input /path/to/feishu_rows.json
```

输出：

- `manifest.json`：写入目标、缺失配置、行数统计。
- `analysis_rows.json`：分析任务表待导入行。
- `evidence_rows.json`：样本证据表待导入行。
- `source_feishu_rows.json`：原始输入副本。

读取 JSON：

- `schema_version` 必须以 `xhs.` 开头，并以 `.feishu_rows.v1` 结尾。
- `tables.分析任务表` 写入分析任务表。
- `tables.样本证据表` 写入样本证据表。
- 字段按 JSON key 原样写入多维表字段。

执行顺序：

1. 读取并解析 `feishu_rows.json`。
2. 生成本地待导入包。
3. 检查飞书 CLI 和固定多维表 ID。
4. 配置完整后，再用飞书 CLI 写入 `tables.分析任务表`。
5. 用飞书 CLI 写入 `tables.样本证据表`。
6. 回报 `run_id`、关键词、两张表写入行数和多维表链接。

## 规则

- 不重新分析 `samples.json`。
- 不把正文、评论全文或截图写入多维表。
- 不在仓库写入飞书 token、app secret 或 cookie。
- 没有 CLI、固定 ID 或写入结果时，不声明成功。
- 当前未配置多维表时，只生成待导入包和 manifest。
