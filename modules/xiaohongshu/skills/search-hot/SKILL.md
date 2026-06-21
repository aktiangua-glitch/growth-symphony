---
name: search-hot
description: 采集小红书关键词搜索页样本，并为 agent 生成热门分析证据。Use when 用户要求小红书关键词热门分析、关键词搜索采样、选题机会、爆款结构拆解、标题/评论/话题模式提取。
---

# Search Hot

输入关键词和已打开浏览器的 CDP endpoint，采集小红书搜索页证据。

## 执行

```bash
cd /Users/admin/growth-symphony
npm run xhs:search-hot -- --keyword "AI编程"
```

安装和 `BROWSER_CDP_ENDPOINT` 配置按顶层 `README.md` 执行。

默认采样 20 条搜索卡片，打开 3 条详情页。

## 步骤

1. 打开搜索页：`https://www.xiaohongshu.com/search_result?keyword=<keyword>&type=51`
2. 采样可见搜索卡片。
3. 打开少量详情页。
4. 提取标题、正文摘要、评论、话题、可见互动、标题钩子、正文结构、评论主题和浅层信号。
5. 输出 `samples.json`、`agent_input.json`、`summary.md` 和 `feishu_rows.json`。
6. agent 读取 `agent_input.json` 后，再按用户课题生成热点判断和选题结论。

## 规则

- 只分析浏览器页面可见内容。
- 不读 Cookie。
- 不调用私有接口。
- 不点赞、不收藏、不评论、不关注、不发布。
- 只关闭本次新开的 tab，不关闭浏览器或 profile。
- 指标不可见就写不可见，不补数字。
- 只基于单次搜索页采样时，不下“全平台趋势”结论。
- Python 脚本不写固定选题、不写机会等级、不写推荐理由。
