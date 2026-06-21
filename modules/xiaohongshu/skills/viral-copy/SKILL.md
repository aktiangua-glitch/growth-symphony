---
name: viral-copy
description: 基于小红书浏览器采集结果做爆款结构复刻和仿写方案。Use when 用户要求复刻笔记、仿写小红书、爆款结构拆解、Viral Copy、标题仿写、正文大纲、封面文案、评论互动设计或基于某条笔记生成可发布方案。
---

# Viral Copy

基于 `note-detail` 或 `search-hot` 生成的 `agent_input.json` 做结构级复刻。

## 执行

如果用户给的是笔记 URL，先跑 `note-detail`：

```bash
cd /Users/admin/growth-symphony
npm run xhs:note-detail -- --url "https://www.xiaohongshu.com/..."
```

再生成复刻上下文：

```bash
npm run xhs:viral-copy-context -- --input /path/to/agent_input.json --topic "你的课题"
```

脚本输出：

- `viral_copy_context.json`：压缩后的证据，只保留复刻判断需要的字段。
- `viral_copy_template.json`：LLM 需要补全的固定 JSON 结构。
- `summary.md`：本次复刻分析入口。

## 分工

- `note-detail` / `search-hot`：采集浏览器可见事实。
- `viral-copy`：压缩证据、固定输出结构、约束复刻边界。
- agent/LLM：基于 `viral_copy_context.json` 输出新笔记方案。

## 输出要求

LLM 必须输出 `xhs.viral_copy.v1` JSON：

```json
{
  "schema_version": "xhs.viral_copy.v1",
  "source_path": "",
  "topic": "",
  "source_structure": {
    "title_pattern": "",
    "opening_hook": "",
    "body_rhythm": "",
    "tag_strategy": "",
    "comment_mechanism": "",
    "cover_hierarchy": ""
  },
  "replicable_parts": [],
  "replace_parts": [],
  "new_note_plan": {
    "titles": [],
    "cover_text": {
      "main": "",
      "sub": ""
    },
    "body_outline": [],
    "interaction_question": "",
    "topics": []
  },
  "risks": [],
  "evidence_limits": []
}
```

## 规则

- 只做结构级复刻，不逐字照抄。
- 不复用原图、原作者经历、隐私信息、评论原话。
- 新标题必须换人群、场景、结果或限制条件。
- 正文只给大纲和表达策略，不生成搬运式长文。
- 评论需求只能来自采集到的评论证据。
- 没有正文、评论或互动证据时，必须写入 `evidence_limits`。
