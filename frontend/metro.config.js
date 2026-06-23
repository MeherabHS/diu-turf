// metro.config.js
const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");
const { FileStore } = require("metro-cache");

const projectRoot = __dirname;
const config = getDefaultConfig(projectRoot);

// Pin singletons so Metro never resolves the stray nested react-native@0.86 copy
// (causes VirtualViewExperimentalNativeComponent codegen / onModeChange failures).
config.resolver.extraNodeModules = {
  react: path.resolve(projectRoot, "node_modules/react"),
  "react-native": path.resolve(projectRoot, "node_modules/react-native"),
};

config.resolver.blockList = [
  ...(Array.isArray(config.resolver.blockList) ? config.resolver.blockList : []),
  /[\\/]node_modules[\\/]react-native[\\/]node_modules[\\/]react-native[\\/].*/,
];

// Use a stable on-disk store (shared across web/android)
const root = process.env.METRO_CACHE_ROOT || path.join(projectRoot, ".metro-cache");
config.cacheStores = [
  new FileStore({ root: path.join(root, "cache") }),
];

// Reduce the number of workers to decrease resource usage
config.maxWorkers = 2;

module.exports = config;
