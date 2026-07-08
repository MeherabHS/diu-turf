#!/usr/bin/env node
// Banned packages list. Used by preinstall hook and install-guard.sh.

const fs = require("fs");
const path = require("path");

const BANNED = {
  "expo-av": {
    reason: "Deprecated.",
    alternative: "expo-audio for audio, expo-video for video.",
  },
  "expo-barcode-scanner": {
    reason: "Deprecated.",
    alternative: "expo-camera for barcode scanning.",
  },
  "expo-background-fetch": {
    reason: "Deprecated.",
    alternative: "expo-background-task for background fetching.",
  },
  "expo-file-system/legacy": {
    reason: "Deprecated.",
    alternative: "expo-file-system.",
  },
};

function stripUtf8Bom(buffer) {
  if (
    buffer.length >= 3 &&
    buffer[0] === 0xef &&
    buffer[1] === 0xbb &&
    buffer[2] === 0xbf
  ) {
    return buffer.subarray(3);
  }
  return buffer;
}

/** UTF-8 BOM breaks JSON.parse and Gradle/Node tooling on Windows. */
function ensureJsonNoBom(relativePath) {
  const filePath = path.join(__dirname, "..", relativePath);
  if (!fs.existsSync(filePath)) return;
  const raw = fs.readFileSync(filePath);
  const stripped = stripUtf8Bom(raw);
  if (stripped.length !== raw.length) {
    fs.writeFileSync(filePath, stripped);
    console.warn(
      `[check-pkg] Removed UTF-8 BOM from ${relativePath} (fixes Android/Expo autolinking on Windows).`,
    );
  }
}

function readJsonFile(relativePath) {
  ensureJsonNoBom(relativePath);
  const text = fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
  return JSON.parse(text.startsWith("\uFEFF") ? text.slice(1) : text);
}

function report(name, recovery) {
  const { reason, alternative } = BANNED[name];
  console.error("");
  console.error(`${name} is not allowed in this template.`);
  console.error(`  Reason:      ${reason}`);
  console.error(`  Use instead: ${alternative}`);
  if (recovery) console.error(`  Recovery:    ${recovery}`);
  console.error("");
}

// --args mode: scan CLI args for banned package names (with optional @version).
if (process.argv[2] === "--args") {
  for (const arg of process.argv.slice(3)) {
    for (const name of Object.keys(BANNED)) {
      if (arg === name || arg.startsWith(name + "@")) {
        report(name);
        process.exit(1);
      }
    }
  }
  process.exit(0);
}

// Default mode: scan package.json on disk.
ensureJsonNoBom("app.json");
const pkg = readJsonFile("package.json");
const all = { ...pkg.dependencies, ...pkg.devDependencies };
const hits = Object.keys(all).filter((name) => name in BANNED);

if (hits.length === 0) process.exit(0);

for (const name of hits) {
  report(name, "run `git checkout package.json` to undo the add.");
}
process.exit(1);