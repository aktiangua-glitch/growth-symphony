---
name: strategy-analysis
description: 基于小红书浏览器采集结果做策略分析。Use when 用户要求根据 `agent_input.json`、`samples.json`、`detail.json`、`feed.json`、`profile.json`、`matrix.json` 生成小红书热点判断、关键词矩阵、账号体检、首页推荐流画像、选题策略、标题方向、评论需求分析、爆款结构拆解、Viral Copy 或飞书分析字段补全。
---

# Strategy Analysis

输入是采集 skill 生成的 `agent_input.json`。这个 skill 不采集页面、不跑浏览器，只做策略分析。

## 分工

- `search-hot` / `note-detail` / `home-feed` / `account-scan` / `keyword-matrix`：采集浏览器可见事实和浅层信号。
- `viral-copy`：读取采集结果，生成结构级复刻上下文和固定输出模板。
- `strategy-analysis`：基于事实生成判断、选题和表达策略。
- `xiaohongshu-ops-agent`：决定先采集什么、是否深挖详情、是否写入飞书。

## 输入类型

- `xhs.search_hot.agent_input.v1`：关键词热门分析。重点看标题聚类、详情页正文、评论追问、互动比例和内容形态。
- `xhs.note_detail.agent_input.v1`：单条笔记深挖。重点看标题钩子、正文结构、评论需求、标签和可复刻结构。
- `xhs.home_feed.agent_input.v1`：首页推荐流分析。重点看主导主题、停留钩子、推荐流重复模式和当前账号可借用结构。
- `xhs.account_scan.agent_input.v1`：账号体检。重点看主页定位、近期内容支柱、标题/封面结构、互动转化和可持续性。
- `xhs.keyword_matrix.agent_input.v1`：关键词矩阵。重点比较多个关键词的可见互动上限、标题聚类、信号集中度、内容形态和评论需求。

## 分析步骤

1. 读取 `agent_input.json`，先确认关键词、样本数、详情数、采集时间和页面状态。
2. 只引用输入里存在的标题、正文摘要、评论、标签、互动提示和浅层信号。
3. 先用 Python 给出的结构化字段做证据索引：`hook_analysis`、`content_structure`、`comment_patterns`、`engagement_ratios`、`signals`。
4. 判断内容聚类：教程方法、案例复盘、避坑清单、对比测评、观点讨论、种草转化、评论答疑、效果展示。
5. 判断机会：搜索意图是否清晰、样本是否集中、评论是否有追问、收藏/评论比例是否支持继续深挖、内容形态是否适合当前账号。
6. 生成 3-5 个选题方向。每个方向必须绑定证据，不套固定模板。
7. 输出结构化 JSON；需要报告时，再把 JSON 写成人话总结。

## 上游能力对齐

从 `redbook` 同步到分析层，不同步它的 Cookie/API 执行方式：

- 互动信号：可见时用收藏/点赞、评论/点赞、分享/点赞判断工具型、讨论型、转发型。
- 爆款结构：拆标题钩子、正文结构、标签、CTA、评论主题。
- 爆款模板：多条高信号笔记时，总结共同钩子、正文长度/段落、评论需求和内容形态。
- 关键词矩阵：用户给多个关键词时，分别读取多个 `agent_input.json`，比较 Top 样本、平均互动提示、内容集中度和机会层级。

从 `xiaohongshu-ops-skill` 同步到分析层：

- 账号体检：按定位清晰度、内容结构力、互动转化力、账号辨识度、增长可持续性五维评分。
- 首页推荐流：输出首页画像、高信号样本、可复用模式、下步动作。
- 选题灵感：合并平台信号、评论需求、账号定位，输出 3-5 条可写选题。
- Viral Copy：用户给爆款 URL 时，基于 `note-detail` 输出结构级复刻建议，不逐字照抄，不复用原图。

## 语言策略

- 标题要具体，优先体现人群、场景、结果、冲突或限制条件。
- 不写空泛词：爆款、必看、干货、天花板，除非原始样本高频出现。
- 不直接照搬样本标题，要抽象结构后换成当前课题的真实表达。
- 评论里的问题优先转成二级选题；没有评论证据时不要假设用户痛点。
- 工具名、价格、时间、效果这类信息只在证据出现时使用。

## 账号体检输出

当输入是 `xhs.account_scan.agent_input.v1`，输出必须包含：

- 账号一句话定位。
- 五维评分，每项 `1-5` 分并给一句证据理由。
- 最大优势、最大短板、造成当前结果的主要原因。
- 3 条下一步动作：立刻调整、1 周测试、继续观察指标。

## 首页推荐流输出

当输入是 `xhs.home_feed.agent_input.v1`，输出必须包含：

- 首页画像：主导主题、常见情绪、高频内容类型、可能推荐原因。
- 高信号样本：3-5 条，每条写标题、钩子、结构、互动机制、可复用点。
- 可复用模式：3-5 条。
- 下步动作：选题、封面表达、标题句式或账号定位方向。

## 关键词矩阵输出

当输入是 `xhs.keyword_matrix.agent_input.v1`，输出必须包含：

- 关键词排序：按可见互动、内容集中度、评论需求和账号适配判断。
- 每个关键词的内容类型：工具收藏型、讨论驱动型、效果展示型、种草型等。
- 关键词风险：样本少、指标不可见、内容过散、同质化高。
- 下一步建议：优先深挖哪个关键词、应该追加哪些长尾词。

## Viral Copy 输出

当用户要求爆款结构复刻，必须基于 `note-detail` 或 `search-hot` 的详情证据输出：

- 源笔记结构：标题句式、首段钩子、正文节奏、标签、评论互动机制。
- 可复刻部分：结构、情绪、互动方式、封面信息层级、视觉构图和色块逻辑。
- 必须替换部分：原文措辞、原作者经历、图片素材、视频原帧、隐私信息。
- 新笔记方案：3 个标题、1 版正文大纲、封面主副文案、互动提问、5-8 个话题、视觉复刻方案。
- 如果用户要求图纸：输出拼豆图纸/像素格稿生成提示词、色块建议、网格尺寸、备注说明。
- 如果源内容是视频：输出 3-5 个关键帧参考说明；不可把原帧作为最终发布素材。
- 风险：逐字照抄、原图复用、原视频帧搬运、夸大承诺、引战。

## 输出 JSON

```json
{
  "schema_version": "xhs.strategy_analysis.v2",
  "source_path": "agent_input.json",
  "run_id": "",
  "topic": "",
  "analysis": {
    "hot_type": "",
    "opportunity_tier": "",
    "content_form": "",
    "primary_hooks": [],
    "engagement_profile": [],
    "comment_needs": [],
    "one_line_conclusion": "",
    "evidence_limits": []
  },
  "content_ideas": [
    {
      "title_direction": "",
      "target_user": "",
      "angle": "",
      "evidence": [],
      "risk": ""
    }
  ],
  "account_scan": {
    "positioning": "",
    "scores": {},
    "strength": "",
    "weakness": "",
    "next_actions": []
  },
  "home_feed": {
    "feed_portrait": "",
    "reusable_patterns": [],
    "next_actions": []
  },
  "keyword_matrix": {
    "ranked_keywords": [],
    "comparison": [],
    "long_tail_keywords": []
  },
  "viral_copy": {
    "source_structure": {},
    "replicable_parts": [],
    "replace_parts": [],
    "new_note_plan": {},
    "risks": []
  },
  "evidence_updates": [
    {
      "rank": 1,
      "recommend_reason": "",
      "topic_direction": ""
    }
  ]
}
```

## 飞书字段

如果需要补全 `feishu_rows.json`：

- 分析任务表：填 `热点类型`、`机会等级`、`主导钩子`、`内容形态`、`一句话结论`。
- 样本证据表：按排名填 `推荐理由`、`选题方向`。
- 不把正文、评论全文或截图写入多维表。

## 规则

- 不把单次采样写成全平台趋势。
- 不根据脚本里的浅层信号直接下结论，必须回看原始标题、正文和评论。
- 不输出没有证据支撑的选题。
- 不做点赞、收藏、评论、关注、发布等写动作建议，除非用户明确要求。
