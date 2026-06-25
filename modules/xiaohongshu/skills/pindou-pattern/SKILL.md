---
name: pindou-pattern
description: 输入图片并生成真实色卡约束的拼豆图纸 PNG。Use when 用户要求照片转拼豆图纸、拼豆图纸下载、按推荐算法生成拼豆、从图片生成 MARD 色号清单、在小红书复刻流程里把 gpt-image-2 源图转成可发给粉丝的真实稿纸、或需要把图纸生成能力嵌到网页脚本里。
---

# Pindou Pattern

把一张图片转成拼豆图纸 PNG。算法复用 `bean-pop-studio` 的推荐尺寸、推荐颜色数、主体取景、清爽描边预处理、CIEDE2000 近色匹配和下载图纸渲染。

在小红书拼豆复刻里，本 skill 是第二步：

1. 先用 `gpt-image-2` 生成适合转拼豆的原创展示源图。
2. 再用 `pindou-pattern` 把源图转成真实色卡稿纸 PNG、色号清单、颗数统计和矩阵。
3. 最后用 `gpt-image-2` 参考稿纸颜色和格子结构生成成品效果图。

运营上优先晒第 1 步展示源图和第 3 步成品效果图；第 2 步稿纸用于评论/私信承接，粉丝要图纸时再给。

## 色卡规则

- 不在 skill 里写死或改动颜色。
- 默认品牌是 `MARD`。
- 当前按已校对的 `MARD 221` 色卡运行。
- 色卡来源是拼豆工具项目里的 JSON：

```text
/Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio/src/data/palettes.json
```

线上公开色卡：

```text
/Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio/public/palettes.json
```

## 网页脚本

优先使用仓库命令行脚本，适合 agent 自动执行：

```bash
cd /Users/admin/growth-symphony
npm run xhs:pindou-pattern -- --input "<源图路径>" --output-dir "<输出目录>" --project-name "蜜桃气泡冰沙"
```

脚本会输出：

- `*-pattern.png`：完整稿纸 PNG，可发给粉丝。
- `*-preview.png`：拼豆成品预览。
- `*-manifest.json`：稿纸路径、预览路径、尺寸、总颗数、色号统计。
- `*-matrix.json`：按格子的色号矩阵。

只有需要嵌到页面或手动调试时，再使用下面的网页脚本。

本地开发默认使用源码项目启动后的脚本：

```text
http://127.0.0.1:4173/skill/pindou-pattern-skill.js
```

对应本地源码入口：

```text
/Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio/src/pindouPatternSkillEntry.js
```

最小调用：

```html
<input id="photo" type="file" accept="image/*" />
<script src="http://127.0.0.1:4173/skill/pindou-pattern-skill.js"></script>
<script>
  document.querySelector("#photo").addEventListener("change", async (event) => {
    const file = event.target.files[0];
    const result = await window.PindouPatternSkill.generate(file);

    console.log(result.width, result.height, result.totalBeads, result.counts);
    document.body.append(result.exportCanvas);
  });
</script>
```

直接下载：

```js
await window.PindouPatternSkill.download(file, {
  projectName: "我的拼豆图纸",
});
```

## 推荐算法

不传 `targetWidth` 和 `maxColors` 时自动推荐：

- `targetWidth`：根据原图尺寸、长宽比、主体占比和透明背景可见面积选择 29/58/87/116/145。
- `maxColors`：根据推荐尺寸、原图尺寸、长宽比、主体识别置信度和品牌色卡上限计算。
- 最终颜色只能来自 `palettes.json` 中存在的真实色号。

可选参数：

```js
await window.PindouPatternSkill.generate(file, {
  brand: "MARD",
  targetWidth: 87,
  maxColors: 24,
  projectName: "peach soda",
  showCodes: true,
  roundBeads: true,
  styleMode: "clean_ink",
  styleIntensity: 0.72,
});
```

## 本地源码

核心实现：

```text
/Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio/src/lib/patternSkill.js
```

网页入口：

```text
/Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio/src/pindouPatternSkillEntry.js
```

构建配置：

```text
/Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio/vite.skill.config.js
```

构建命令：

```bash
cd /Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio
npm run build
```

构建会自动生成并部署：

```text
/Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio/public/skill/pindou-pattern-skill.js
```

## 输出

`window.PindouPatternSkill.generate(file)` 返回：

- `exportCanvas`：可直接挂到页面里的完整图纸画布。
- `patternDataUrl`：图纸 PNG data URL。
- `patternBlob()`：异步生成 PNG Blob。
- `previewCanvas` / `previewDataUrl`：拼豆成品预览。
- `counts`：真实色号、名称、HEX 和颗数。
- `matrix`：按格子的色号矩阵。
- `width` / `height` / `totalBeads` / `colorCount`。

在复刻交付里，必须把以下字段写回上游结果：

- `source_image`：第 1 步展示源图路径或链接。
- `pattern_png`：真实色卡稿纸 PNG 路径或链接。
- `preview_png`：拼豆预览图路径或链接。
- `brand` / `width` / `height` / `totalBeads` / `colorCount`。
- `counts`：真实色号、名称、HEX 和颗数。
- `matrix_path`：如果矩阵另存为 JSON/CSV，写入路径。

## 规则

- 不编造色号、颜色名或不存在的珠子颜色。
- 不擅自扩 MARD 色卡；如果要换色卡，先更新并校对 `palettes.json`。
- 如果用户要求“按推荐算法”，不要手动指定 `targetWidth` 和 `maxColors`，交给 skill 自动计算。
- 如果用户要求“直接下载图纸”，优先使用 `window.PindouPatternSkill.download(file, options)`。
- 本地测试阶段默认使用 `/Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio` 下的源码和 `http://127.0.0.1:4173`，不要默认切到线上域名。
