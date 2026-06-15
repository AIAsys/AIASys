const http = require("http");
const fs = require("fs");
const path = require("path");
const url = require("url");

const PORT = process.env.PORT || 13007;
const BACKEND = process.env.API_BASE || "http://localhost:13006";
const STATIC_ROOT = path.resolve(__dirname, "../dist");

const MIME_TYPES = {
  ".html": "text/html",
  ".js": "application/javascript",
  ".mjs": "application/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".otf": "font/otf",
  ".wasm": "application/wasm",
};

function getContentType(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  return MIME_TYPES[ext] || "application/octet-stream";
}

function serveStatic(req, res) {
  const parsed = url.parse(req.url);
  let pathname = parsed.pathname;
  if (pathname === "/") pathname = "/index.html";
  const filePath = path.join(STATIC_ROOT, pathname);

  fs.stat(filePath, (err, stats) => {
    if (!err && stats.isFile()) {
      res.writeHead(200, { "Content-Type": getContentType(filePath) });
      fs.createReadStream(filePath).pipe(res);
      return;
    }
    // SPA fallback for unknown GET routes
    if (req.method === "GET") {
      res.writeHead(200, { "Content-Type": "text/html" });
      fs.createReadStream(path.join(STATIC_ROOT, "index.html")).pipe(res);
      return;
    }
    res.writeHead(404);
    res.end("Not found");
  });
}

function proxyRequest(req, res) {
  const target = new URL(req.url, BACKEND);
  const options = {
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port,
    path: target.pathname + target.search,
    method: req.method,
    headers: { ...req.headers },
  };
  // Let backend determine host/content-length
  delete options.headers.host;
  delete options.headers["content-length"];

  const proxyReq = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res);
  });

  proxyReq.on("error", (err) => {
    console.error("proxy error", err.message);
    if (!res.headersSent) {
      res.writeHead(502);
      res.end(JSON.stringify({ error: "Bad Gateway", message: err.message }));
    }
  });

  req.pipe(proxyReq);
}

const server = http.createServer((req, res) => {
  const parsed = url.parse(req.url);
  if (parsed.pathname.startsWith("/api/") || parsed.pathname === "/health") {
    proxyRequest(req, res);
  } else {
    serveStatic(req, res);
  }
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Proxy preview listening on http://127.0.0.1:${PORT} -> ${BACKEND}`);
});
