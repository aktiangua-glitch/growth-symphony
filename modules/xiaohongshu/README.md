# Xiaohongshu

小红书模块只放平台任务。

当前能力：

- `search-hot`：按关键词采集搜索页样本。
- `keyword-matrix`：批量采集多个关键词并生成矩阵证据。
- `note-detail`：按 URL 采集单条笔记详情。
- `home-feed`：采集首页推荐流样本。
- `account-scan`：采集账号主页和近期笔记样本。
- `viral-copy`：基于采集证据生成结构级复刻上下文。
- `strategy-analysis`：基于 `agent_input.json` 做策略分析、选题判断和飞书字段补全。

运行链路：

```text
agent 选择浏览器环境
  -> browser-env 使用 ads CLI 取得 ws.puppeteer
  -> search-hot / keyword-matrix / note-detail / home-feed / account-scan 采集证据
  -> viral-copy 按需生成复刻上下文
  -> strategy-analysis 生成策略判断
  -> feishu-skill 写入多维表
```

`note-detail` 会输出作者主页；需要账号体检时，直接把 `author.profile_url` 交给 `account-scan`。

安装、环境检测和运行命令放在顶层 `README.md`。

默认采样：

- `search-hot`：20 条搜索卡片，3 条详情页。
- `keyword-matrix`：每个关键词 12 条搜索卡片，1 条详情页。
- `home-feed`：20 条首页推荐卡片，3 条详情页。
- `account-scan`：15 条近期笔记，3 条详情页。
