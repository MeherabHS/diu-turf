#!/usr/bin/env node
/**
 * npm may auto-install react-native@latest as a nested peer under react-native@0.81.x.
 * Metro then codegen-processes VirtualViewExperimentalNativeComponent and fails with:
 *   Unable to determine event arguments for "onModeChange"
 */
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const nested = path.join(
  __dirname,
  "..",
  "node_modules",
  "react-native",
  "node_modules",
  "react-native",
);

if (!fs.existsSync(nested)) {
  process.exit(0);
}

try {
  // Windows long-path safe delete (PowerShell Remove-Item often fails on deep RN trees).
  if (process.platform === "win32") {
    const winPath = nested.replace(/\//g, "\\");
    execSync(`cmd /c rmdir /s /q "${winPath}"`, { stdio: "ignore" });
  } else {
    fs.rmSync(nested, { recursive: true, force: true });
  }
  console.log("[postinstall] removed nested react-native copy:", nested);
} catch (error) {
  console.warn(
    "[postinstall] could not remove nested react-native (Metro blockList still protects bundling):",
    error instanceof Error ? error.message : error,
  );
}
