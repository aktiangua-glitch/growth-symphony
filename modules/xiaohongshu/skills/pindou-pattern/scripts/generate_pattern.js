#!/usr/bin/env node

import { chromium } from "playwright";
import fs from "node:fs/promises";
import path from "node:path";

const DEFAULT_BUNDLE_PATH = "/Users/admin/Documents/VibeProjects/vibe-codex/bean-pop-studio/public/skill/pindou-pattern-skill.js";

function parseArgs(argv) {
  const args = {
    brand: "MARD",
    browserChannel: "chrome",
    outputDir: "",
    projectName: "",
    roundBeads: true,
    scriptPath: DEFAULT_BUNDLE_PATH,
    showCodes: true,
    styleIntensity: 0.72,
    styleMode: "clean_ink",
  };

  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key.startsWith("--")) continue;
    if (key === "--input") args.input = value;
    if (key === "--output-dir") args.outputDir = value;
    if (key === "--project-name") args.projectName = value;
    if (key === "--brand") args.brand = value;
    if (key === "--browser-channel") args.browserChannel = value;
    if (key === "--target-width") args.targetWidth = Number(value);
    if (key === "--max-colors") args.maxColors = Number(value);
    if (key === "--style-mode") args.styleMode = value;
    if (key === "--style-intensity") args.styleIntensity = Number(value);
    if (key === "--script-path") args.scriptPath = value;
    if (key === "--show-codes") args.showCodes = value !== "false";
    if (key === "--round-beads") args.roundBeads = value !== "false";
    index += 1;
  }

  if (!args.input) {
    throw new Error("Missing --input <image-path>");
  }
  return args;
}

function safeSlug(value) {
  return String(value || "pindou-pattern")
    .trim()
    .replace(/\.[a-z0-9]+$/i, "")
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "pindou-pattern";
}

function imageBufferFromDataUrl(dataUrl) {
  const match = /^data:image\/png;base64,(.+)$/u.exec(dataUrl || "");
  if (!match) {
    throw new Error("Expected PNG data URL from pindou-pattern");
  }
  return Buffer.from(match[1], "base64");
}

async function writeJson(filePath, data) {
  await fs.writeFile(filePath, JSON.stringify(data, null, 2), "utf8");
}

async function launchBrowser(channel) {
  if (channel && channel !== "none") {
    try {
      return await chromium.launch({ channel, headless: true });
    } catch (error) {
      console.warn(`Unable to launch browser channel "${channel}", falling back to bundled Chromium.`);
      console.warn(error.message);
    }
  }
  return chromium.launch({ headless: true });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const inputPath = path.resolve(args.input);
  const outputDir = path.resolve(args.outputDir || path.join(path.dirname(inputPath), "pindou-pattern"));
  const bundlePath = path.resolve(args.scriptPath);
  const sourceBase = safeSlug(args.projectName || path.basename(inputPath));

  await fs.access(inputPath);
  const bundle = (await fs.readFile(bundlePath, "utf8"))
    .replace("previewCanvas:x,previewDataUrl:x.toDataURL(\"image/png\")", "previewCanvas:x,previewDataUrl:x");
  await fs.mkdir(outputDir, { recursive: true });

  const browser = await launchBrowser(args.browserChannel);
  try {
    const page = await browser.newPage();
    await page.setContent(`
      <!doctype html>
      <meta charset="utf-8">
      <input id="photo" type="file" accept="image/*">
      <script>${bundle}</script>
    `);
    await page.setInputFiles("#photo", inputPath);

    const options = {
      brand: args.brand,
      projectName: args.projectName || sourceBase,
      roundBeads: args.roundBeads,
      showCodes: args.showCodes,
      styleIntensity: args.styleIntensity,
      styleMode: args.styleMode,
    };
    if (Number.isFinite(args.targetWidth)) options.targetWidth = args.targetWidth;
    if (Number.isFinite(args.maxColors)) options.maxColors = args.maxColors;

    const result = await page.evaluate(async (runOptions) => {
      const file = document.querySelector("#photo").files[0];
      const pattern = await window.PindouPatternSkill.generate(file, runOptions);
      return {
        backgroundColorCode: pattern.backgroundColorCode,
        brand: pattern.brand,
        colorCount: pattern.colorCount,
        counts: pattern.counts,
        height: pattern.height,
        hiddenBackgroundCells: pattern.hiddenBackgroundCells,
        matrix: pattern.matrix,
        maxColors: pattern.maxColors,
        patternDataUrl: pattern.patternDataUrl,
        previewDataUrl: pattern.previewDataUrl,
        subjectBox: pattern.subjectBox,
        targetWidth: pattern.targetWidth,
        title: pattern.title,
        totalBeads: pattern.totalBeads,
        width: pattern.width,
      };
    }, options);

    const patternPath = path.join(outputDir, `${sourceBase}-pattern.png`);
    const previewPath = path.join(outputDir, `${sourceBase}-preview.png`);
    const matrixPath = path.join(outputDir, `${sourceBase}-matrix.json`);
    const manifestPath = path.join(outputDir, `${sourceBase}-manifest.json`);

    await fs.writeFile(patternPath, imageBufferFromDataUrl(result.patternDataUrl));
    await fs.writeFile(previewPath, imageBufferFromDataUrl(result.previewDataUrl));
    await writeJson(matrixPath, result.matrix);

    const manifest = {
      source_image: inputPath,
      pattern_png: patternPath,
      preview_png: previewPath,
      matrix_path: matrixPath,
      brand: result.brand,
      width: result.width,
      height: result.height,
      total_beads: result.totalBeads,
      color_count: result.colorCount,
      counts: result.counts,
      metadata: {
        backgroundColorCode: result.backgroundColorCode,
        hiddenBackgroundCells: result.hiddenBackgroundCells,
        maxColors: result.maxColors,
        projectName: options.projectName,
        subjectBox: result.subjectBox,
        targetWidth: result.targetWidth,
        title: result.title,
      },
    };
    await writeJson(manifestPath, manifest);
    console.log(JSON.stringify({
      manifestPath,
      patternPath,
      previewPath,
      matrixPath,
      width: result.width,
      height: result.height,
      totalBeads: result.totalBeads,
      colorCount: result.colorCount,
    }, null, 2));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
