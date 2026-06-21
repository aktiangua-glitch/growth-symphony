---
name: home-feed
description: 采集小红书首页推荐流样本，并为 agent 生成推荐流画像和选题分析证据。Use when 用户要求分析首页推荐流、找推荐页选题灵感、拆解首页内容结构、观察当前账号兴趣流或判断哪些推荐内容值得复用。
---

# Home Feed

输入已打开浏览器的 CDP endpoint，采集当前登录态下的小红书首页推荐流证据。

## 执行

```bash
cd /Users/admin/growth-symphony
npm run xhs:home-feed
```

安装和 `BROWSER_CDP_ENDPOINT` 配置按顶层 `README.md` 执行。

默认采样 20 条首页卡片，打开 3 条详情页。

## 步骤

1. 打开小红书首页推荐流。
2. 采样可见推荐卡片。
3. 打开少量详情页补充正文、评论和话题。
4. 提取标题、封面/卡片文本、可见互动、标题钩子、正文结构、评论主题和浅层信号。
5. 输出 `feed.json`、`agent_input.json`、`summary.md` 和 `feishu_rows.json`。
6. agent 读取 `agent_input.json` 后，再生成推荐流画像、可复用模式和选题方向。

## 规则

- 只分析浏览器页面可见内容。
- 不读 Cookie。
- 不调用私有接口。
- 不点赞、不收藏、不评论、不关注、不发布。
- 只关闭本次新开的 tab，不关闭浏览器或 profile。
- 当前首页受登录态和历史兴趣影响，不写成全平台趋势。
- Python 脚本不写推荐理由、机会等级或选题结论。
