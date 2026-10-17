// Serves out/ on http://127.0.0.1:3100 to preview the static export (no dependencies).
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const out = new URL("../out", import.meta.url).pathname;
const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".txt": "text/plain", ".ico": "image/x-icon", ".woff2": "font/woff2", ".svg": "image/svg+xml" };
const port = Number(process.env.PORT ?? 3100);

createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  let path = normalize(join(out, decodeURIComponent(url.pathname)));
  if (!path.startsWith(out)) return res.writeHead(403).end();
  if (existsSync(path) && statSync(path).isDirectory()) path = join(path, "index.html");
  if (!existsSync(path)) path = join(out, "404.html");
  res.writeHead(path.endsWith("404.html") ? 404 : 200, { "content-type": types[extname(path)] ?? "application/octet-stream" });
  createReadStream(path).pipe(res);
}).listen(port, "127.0.0.1", () => console.log(`preview: http://127.0.0.1:${port}`));
