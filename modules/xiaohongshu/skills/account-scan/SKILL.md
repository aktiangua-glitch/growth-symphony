---
name: account-scan
description: 采集小红书账号主页和近期笔记样本，并为 agent 生成账号体检证据。Use when 用户要求分析小红书账号、竞品账号拆解、账号定位诊断、近期内容体检、判断账号优势短板或生成账号下一步运营动作。
---

# Account Scan

输入账号主页 URL 和已打开浏览器的 CDP endpoint，采集当前登录态可见的账号主页与近期笔记。

## 执行

```bash
cd /Users/admin/growth-symphony
npm run xhs:account-scan -- --url "https://www.xiaohongshu.com/user/profile/..."
```

安装和 `BROWSER_CDP_ENDPOINT` 配置按顶层 `README.md` 执行。

默认采样 15 条近期笔记，打开 3 条详情页。

## 步骤

1. 打开账号主页。
2. 读取主页可见文本、统计提示和近期笔记卡片。
3. 打开少量代表性笔记详情。
4. 提取标题、正文摘要、评论、标签、标题钩子、正文结构、互动比例和浅层信号。
5. 输出 `profile.json`、`agent_input.json`、`summary.md` 和 `feishu_rows.json`。
6. agent 读取 `agent_input.json` 后，再做五维账号体检和下一步动作判断。

## 规则

- 使用指定浏览器 profile 的当前登录态。
- 只分析浏览器页面可见内容。
- 不读 Cookie。
- 不调用私有接口。
- 默认不点赞、不收藏、不评论、不关注、不发布。
- 只关闭本次新开的 tab，不关闭浏览器或 profile。
- 样本少时只做轻量体检，不下长期增长结论。
- Python 脚本不写固定评分、优势短板或下一步动作。
