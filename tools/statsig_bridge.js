// Node bridge: evaluate the obfuscated grok.com statsig-id chunk
// and call its default export to compute x-statsig-id for (path, method).
//
// Usage: node statsig_bridge.js <chunk.js> <pathname> <method>
// Output: JSON {statsig_id: "<base64>"} on stdout

const fs = require("fs");
const path = require("path");

process.on("unhandledRejection", (r) => {
  console.error("[bridge] UNHANDLED REJECTION:", r && r.stack || r);
  process.exit(99);
});
process.on("uncaughtException", (r) => {
  console.error("[bridge] UNCAUGHT:", r && r.stack || r);
  process.exit(99);
});

const chunkPath = process.argv[2];
const reqPath = process.argv[3];
const method = process.argv[4] || "POST";

if (!chunkPath || !reqPath) {
  console.error("usage: node statsig_bridge.js <chunk.js> <pathname> [METHOD]");
  process.exit(2);
}

const src = fs.readFileSync(chunkPath, "utf8");

// Capture the registered Turbopack module function for id 645000 / 645e3
let capturedModuleFn = null;
const turbopackArr = [];
turbopackArr.push = function (entry) {
  Array.prototype.push.call(this, entry);
  // entry shape: [currentScript, modId, modFn, modId, modFn, ...]
  for (let i = 1; i < entry.length; i += 2) {
    if (entry[i] === 645000 || entry[i] === 645e3) {
      capturedModuleFn = entry[i + 1];
    }
  }
};
globalThis.TURBOPACK = turbopackArr;

// Minimal browser-y globals the obfuscator may peek at
globalThis.document = { currentScript: null };
globalThis.window = globalThis;
globalThis.self = globalThis;

// btoa/atob (Node 16+ has these globally; ensure)
if (typeof globalThis.btoa !== "function") {
  globalThis.btoa = (s) => Buffer.from(s, "binary").toString("base64");
  globalThis.atob = (s) => Buffer.from(s, "base64").toString("binary");
}

// Run the chunk
try {
  // wrap in IIFE-style eval to allow strict-mode
  // eslint-disable-next-line no-eval
  (0, eval)(src);
} catch (e) {
  console.error("[bridge] chunk eval error:", e.message);
  process.exit(3);
}

if (!capturedModuleFn) {
  console.error("[bridge] module 645000 not registered");
  process.exit(4);
}

// Module API mock: x.s(["default", fn])
const moduleExports = {};
const x = {
  s: (entries) => {
    for (let i = 0; i < entries.length; i += 2) {
      moduleExports[entries[i]] = entries[i + 1];
    }
  },
};

try {
  capturedModuleFn(x);
} catch (e) {
  console.error("[bridge] module fn error:", e.message);
  process.exit(5);
}

(async () => {
  try {
    const factory = moduleExports.default;
    console.error("[bridge] export keys:", Object.keys(moduleExports));
    console.error("[bridge] default type:", typeof factory);
    if (typeof factory !== "function") {
      console.error("[bridge] no default export, got:", typeof factory,
        "; full exports:", JSON.stringify(moduleExports, (_, v) =>
          typeof v === "function" ? "[Function]" : v));
      process.exit(6);
    }
    // Outer wrapper does:  e.A(629918).then(e => t(e.default()))
    // i.e. call default() to get the actual hashing function, then call it.
    let fn = factory();
    console.error("[bridge] factory() returned type:", typeof fn);
    if (fn && typeof fn.then === "function") {
      fn = await fn;
      console.error("[bridge] awaited factory(), got:", typeof fn);
    }
    if (typeof fn !== "function") {
      console.error("[bridge] factory() result is not a function. value:", fn);
      process.exit(8);
    }
    console.error("[bridge] factory.toString():", factory.toString().slice(0, 400));
    console.error("[bridge] fn.toString():", fn.toString().slice(0, 400));
    let cur = fn;
    let idValue;
    for (let depth = 0; depth < 6; depth++) {
      try {
        const result = cur(reqPath, method);
        console.error(`[bridge] depth=${depth} cur(...) ->`, typeof result,
          "isPromise:", result && typeof result.then === "function");
        const awaited = await result;
        console.error(`[bridge] depth=${depth} awaited ->`, typeof awaited,
          "preview:", typeof awaited === "string" ? awaited.slice(0, 100) : awaited);
        if (typeof awaited === "string") {
          idValue = awaited;
          break;
        }
        if (typeof awaited !== "function") {
          // Maybe it's an object with a token field
          if (awaited && typeof awaited === "object") {
            console.error("[bridge] object keys:", Object.keys(awaited));
          }
          idValue = awaited;
          break;
        }
        cur = awaited;
      } catch (innerErr) {
        console.error(`[bridge] depth=${depth} threw:`, innerErr && innerErr.stack || innerErr);
        throw innerErr;
      }
    }
    process.stdout.write(JSON.stringify({ statsig_id: idValue }) + "\n");
  } catch (e) {
    console.error("[bridge] runtime error:", e && e.stack || e);
    process.exit(7);
  }
})();
