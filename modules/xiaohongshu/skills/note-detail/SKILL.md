---
name: note-detail
description: 采集单条小红书笔记详情页证据，并为 agent 生成策略分析输入。Use when 用户给出小红书笔记 URL、要求深挖某条笔记、分析评论需求、拆解正文结构、提取选题机会或把单条笔记结果输出为 `feishu_rows.json`。
---

# Note Detail

输入笔记 URL 和已打开浏览器的 CDP endpoint，采集当前登录态可见的笔记详情。

## 执行

```bash
cd /Users/admin/growth-symphony
npm run xhs:note-detail -- --url "https://www.xiaohongshu.com/..."
```

安装和 `BROWSER_CDP_ENDPOINT` 配置按顶层 `README.md` 执行。

## 步骤

1. 打开传入的笔记 URL。
2. 读取标题、正文摘要、标签、可见互动、评论文本、标题钩子、正文结构、评论主题和浅层信号。
3. 输出 `detail.json`、`agent_input.json`、`summary.md` 和 `feishu_rows.json`。
4. agent 读取 `agent_input.json` 后，再按用户课题生成内容结构、评论需求和选题机会。

## 规则

- 使用指定浏览器 profile 的当前登录态。
- 只分析浏览器页面可见内容。
- 不读 Cookie。
- 不调用私有接口。
- 默认不点赞、不收藏、不评论、不关注、不发布。
- 只关闭本次新开的 tab，不关闭浏览器或 profile。
- 指标不可见就写不可见，不补数字。
- Python 脚本不写固定选题、不写机会等级、不写推荐理由。
