// Verifies the public site stays a static, engine-free export and meets accessibility basics.
// Run after `npm run build`. Exits non-zero with one line per problem.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const out = join(root, "out");
const problems = [];

function files(dir, filter) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "node_modules" ? [] : files(path, filter);
    return filter(path) ? [path] : [];
  });
}

// 1. Configuration: static export only, nothing that could forward requests.
const config = readFileSync(join(root, "next.config.ts"), "utf8");
if (!/output:\s*"export"/.test(config)) problems.push("next.config.ts: output must be \"export\"");
for (const key of ["rewrites", "redirects", "headers"]) {
  if (new RegExp(`\\b${key}\\s*[(:]`).test(config)) problems.push(`next.config.ts: ${key} is not allowed`);
}

// 2. Source: no server code, no network calls, no engine addresses.
const src = join(root, "src");
for (const path of files(src, (p) => /\.(ts|tsx|mjs|js)$/.test(p) && !p.endsWith(".test.tsx"))) {
  const rel = relative(root, path);
  if (/(^|\/)(route|middleware|proxy)\.(ts|js)$/.test(path)) problems.push(`${rel}: server entry points are not allowed`);
  const text = readFileSync(path, "utf8");
  if (/^\s*["']use server["']/m.test(text)) problems.push(`${rel}: server actions are not allowed`);
  for (const pattern of [/\bfetch\s*\(/, /XMLHttpRequest/, /new WebSocket/, /EventSource/, /sendBeacon/]) {
    if (pattern.test(text)) problems.push(`${rel}: network call ${pattern} is not allowed`);
  }
}

// 3. Build output.
const ENGINE = [/localhost:\d+/, /127\.0\.0\.1/, /0\.0\.0\.0/, /:8000\b/, /\/api\/backend/, /AUTORESILIENCE_API/];
if (!existsSync(out)) {
  problems.push("out/ is missing: run `npm run build` first");
} else {
  for (const path of files(out, (p) => /\.(html|js|txt|css)$/.test(p))) {
    const text = readFileSync(path, "utf8");
    for (const pattern of ENGINE) {
      if (pattern.test(text)) problems.push(`${relative(root, path)}: engine address ${pattern} in build output`);
    }
  }
  const pages = files(out, (p) => p.endsWith(".html"));
  for (const path of pages) {
    const rel = relative(root, path);
    const html = readFileSync(path, "utf8");
    const h1 = (html.match(/<h1[\s>]/g) ?? []).length;
    if (!/<html[^>]*\blang="en"/.test(html)) problems.push(`${rel}: <html lang> missing`);
    if (!/<title>[^<]+<\/title>/.test(html)) problems.push(`${rel}: <title> missing`);
    if (!/<meta name="description"/.test(html)) problems.push(`${rel}: meta description missing`);
    if (!/<meta name="viewport"/.test(html)) problems.push(`${rel}: viewport meta missing`);
    if (h1 !== 1) problems.push(`${rel}: expected exactly one <h1>, found ${h1}`);
    if (!/<main[\s>]/.test(html)) problems.push(`${rel}: <main> landmark missing`);
    if (!/href="#content"/.test(html)) problems.push(`${rel}: skip link missing`);
    if (!/http-equiv="Content-Security-Policy"[^>]*connect-src &#x27;self&#x27;/.test(html)) {
      problems.push(`${rel}: CSP with connect-src 'self' missing`);
    }
    for (const img of html.match(/<img\b[^>]*>/g) ?? []) {
      if (!/\balt=/.test(img)) problems.push(`${rel}: <img> without alt`);
    }
    for (const svg of html.match(/<svg\b[^>]*>/g) ?? []) {
      if (!/aria-hidden="true"|role="img"/.test(svg)) problems.push(`${rel}: <svg> needs aria-hidden or role="img"`);
    }
    for (const a of html.match(/<a\b[^>]*target="_blank"[^>]*>/g) ?? []) {
      if (!/rel="[^"]*noreferrer/.test(a)) problems.push(`${rel}: target=_blank link without rel=noreferrer`);
    }
    for (const button of html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g) ?? []) {
      if (!/aria-label=|<span class="sr-only">[^<]+|>[^<\s][^<]*</.test(button)) problems.push(`${rel}: button without a name`);
    }
  }
  if (pages.length < 10) problems.push(`out/: expected at least 10 pages, found ${pages.length}`);
}

if (problems.length) {
  console.error(problems.map((p) => `FAIL ${p}`).join("\n"));
  process.exit(1);
}
console.log("ok   static export: no server code, no engine addresses, accessibility basics present");
