---
name: keyword-matrix
description: 批量采集多个小红书关键词搜索页样本，并生成关键词矩阵分析输入。Use when 用户给出多个小红书关键词、要求比较关键词机会、关键词矩阵、话题组合热度、选题方向优先级或跨关键词内容结构对比。
---

# Keyword Matrix

输入多个关键词和已打开浏览器的 CDP endpoint，逐个采集小红书搜索页样本并生成矩阵证据。

## 执行

```bash
cd /Users/admin/growth-symphony
npm run xhs:keyword-matrix -- --keyword "拼豆" --keyword "拼豆图纸" --keyword "拼豆教程"
```

安装和 `BROWSER_CDP_ENDPOINT` 配置按顶层 `README.md` 执行。

默认每个关键词采样 12 条搜索卡片，打开 1 条详情页。

## 步骤

1. 逐个关键词运行浏览器搜索采样。
2. 保存每个关键词的 `samples.json`、`agent_input.json`、`feishu_rows.json`。
3. 聚合可见互动、标题钩子、内容形态、信号标签和评论主题。
4. 输出 `matrix.json`、`agent_input.json`、`summary.md` 和 `feishu_rows.json`。
5. agent 读取 `agent_input.json` 后，再比较关键词机会和选题优先级。

## 规则

- 只分析浏览器页面可见内容。
- 不读 Cookie。
- 不调用私有接口。
- 不点赞、不收藏、不评论、不关注、不发布。
- 只关闭本次新开的 tab，不关闭浏览器或 profile。
- 关键词机会等级、推荐理由和选题方向由 agent/LLM 判断。
