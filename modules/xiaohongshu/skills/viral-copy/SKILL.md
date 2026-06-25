---
name: viral-copy
description: 基于小红书浏览器采集结果做爆款结构复刻、视觉复刻和仿写方案。Use when 用户要求复刻笔记、仿写小红书、爆款结构拆解、Viral Copy、标题仿写、正文大纲、封面文案、评论互动设计、参考原图生成相似图/拼豆图纸、用 pindou-pattern 生成真实色卡稿纸、视频关键帧复刻或基于某条笔记生成可发布方案。
---

# Viral Copy

基于 `note-detail` 或 `search-hot` 生成的 `agent_input.json` 做结构级复刻。复刻交付必须覆盖文案和视觉两层；小红书笔记不能只给正文。拼豆图纸必须绑定真实色卡，不能生成现实珠子里不存在的颜色。拼豆复刻默认走“展示源图 -> 真实稿纸 -> 成品效果图”的三段闭环。

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

拼豆图纸默认会读取真实色卡：

```bash
npm run xhs:viral-copy-context -- --input /path/to/agent_input.json --topic "蜜桃气泡冰沙拼豆图纸" --palette-brand MARD
```

脚本输出：

- `viral_copy_context.json`：压缩后的证据，只保留复刻判断需要的字段。
- `viral_copy_template.json`：LLM 需要补全的固定 JSON 结构。
- `palette_reference.json`：当未使用 `--no-palette` 时写入，缓存来自 `https://拼豆.cn/palettes.json` 的全量真实拼豆色卡。
- `summary.md`：本次复刻分析入口。

## 分工

- `note-detail` / `search-hot`：采集浏览器可见事实。
- `viral-copy`：压缩证据、固定输出结构、约束复刻边界。
- `pindou-pattern`：把可用于拼豆的源图转换为真实色卡稿纸 PNG、色号清单、颗数统计和矩阵。
- agent/LLM：基于 `viral_copy_context.json` 输出新笔记方案，调用 `gpt-image-2` 与 `pindou-pattern` 生成完整视觉资产，并补充评论互动方案。

## 视觉复刻流程

- 图文笔记：优先读取浏览器可见原图或截图，把它作为参考图；结合新主题文本生成原创相似图或拼豆图纸。不要复用原图、不要逐像素照抄原图。
- 拼豆类笔记：如果用户说“图纸”，必须产出三类图片资产：1）`gpt-image-2` 生成的展示源图，画面干净、主体明确、适合转拼豆；2）`pindou-pattern` 生成的真实色卡稿纸 PNG，能发给粉丝照着摆；3）参考第 2 步稿纸颜色和格子结构再生成的成品效果图/晒图。
- 拼豆真实色卡：默认使用 `https://拼豆.cn/palettes.json`，优先品牌 `MARD`。生成图纸时只能使用 `bead_palette_reference.selected_colors` 或 `palette_reference.json` 里存在的 `code/name/hex`，不要编造“浅粉/奶油黄”等无法购买的颜色。需要更多颜色时回查 `palette_reference.json` 全量色卡。
- 视频笔记：如果可合法访问视频素材，先截取 3-5 个关键帧作为镜头参考；输出关键帧说明和相似图生成提示词，并标注“参考帧，不可直接搬运”。没有视频文件或无法访问时，写入 `evidence_limits`。
- 使用图像生成时，默认必须用 `gpt-image-2` 完成出图闭环。先按 `gpt-image-2` skill 检测模式：Mode A 直接调用本地脚本落盘；Mode B 调用宿主图像工具出图；只有 Mode C 才能退化为 prompt 顾问。prompt 必须声明“色块来自真实拼豆色卡”，并列出所用色号。不要让图像模型自由生成渐变色、金属光、半透明珠子或真实色卡不存在的颜色。
- `image_prompts` 只是出图过程记录，不能作为有图像能力时的最终交付。最终交付必须在 `generated_assets` 写入图片路径、链接或明确的无法出图原因。

## 拼豆视觉闭环

拼豆复刻必须按这个顺序执行：

1. **展示源图**：用 `gpt-image-2` 生成原创源图。画面要适合转稿纸：主体居中、轮廓清楚、少背景、少渐变、色块干净。
2. **拼豆稿纸**：用 `pindou-pattern` 读取第 1 步图片，按推荐算法生成真实色卡稿纸 PNG，并记录色号清单、颗数统计、矩阵和稿纸路径。
3. **成品效果图**：用 `gpt-image-2` 参考第 2 步稿纸颜色和格子结构，生成“拼好后”的成品晒图。不能自由换色，必须贴近稿纸主色和形状。

运营使用：小红书正文/封面优先晒第 1 张展示源图和第 3 张成品效果图；第 2 张稿纸作为评论/私信承接物，粉丝要图纸时再给。

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
  "visual_plan": {
    "reference_handling": "",
    "target_visual_type": "",
    "image_prompts": [],
    "generated_assets": [],
    "pindou_pattern": {
      "source_image": "",
      "pattern_png": "",
      "preview_png": "",
      "brand": "",
      "width": "",
      "height": "",
      "total_beads": "",
      "color_count": "",
      "counts": [],
      "matrix_path": "",
      "notes": ""
    },
    "pattern_sheet": {
      "canvas_ratio": "",
      "grid_size": "",
      "palette_source": "",
      "brand": "",
      "palette": [],
      "color_limit": "",
      "layout_notes": "",
      "text_overlay": ""
    },
    "video_keyframes": []
  },
  "risks": [],
  "evidence_limits": []
}
```

## 规则

- 只做结构级复刻，不逐字照抄。
- 不复用原图、原作者经历、隐私信息、评论原话。
- 视觉复刻必须生成“原创相似图/图纸图片”，不能只给封面文案或图片生成提示词。
- 参考原图只能用于构图、色块、镜头、信息层级分析；最终图像必须换主题、换主体细节或换色系。
- 如果用户要求“图纸”，优先按三段闭环生成展示源图、`pindou-pattern` 稿纸和成品效果图，并输出真实色号、色块建议和图纸备注；prompt 只作为随附记录。
- 拼豆图纸的 `pattern_sheet.palette` 必须逐项写 `code/name/hex/usage`，且每个色号必须能在 `bead_palette_reference` 或 `palette_reference.json` 查到。
- 拼豆稿纸的真实色号和颗数以 `pindou-pattern` 输出为准；第 3 张成品效果图必须参考稿纸主色、网格形状和色块比例。
- 如果源内容是视频，必须给关键帧提取/参考说明；能截帧就列出关键帧，不能截帧就说明限制。
- 新标题必须换人群、场景、结果或限制条件。
- 正文只给大纲和表达策略，不生成搬运式长文。
- 评论需求只能来自采集到的评论证据。
- 没有正文、评论或互动证据时，必须写入 `evidence_limits`。
