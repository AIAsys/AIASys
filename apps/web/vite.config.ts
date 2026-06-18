import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig, loadEnv } from "vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const DEFAULT_API_TARGET = 'http://localhost:13001';
  const apiTarget = env.VITE_API_TARGET || DEFAULT_API_TARGET;

  return {
    plugins: [
      react(),
      tailwindcss(),
      // SPA 历史回退插件
      {
        name: 'spa-fallback',
        configureServer(server) {
          return () => {
            server.middlewares.use((req, res, next) => {
              void res;
              // 只处理 GET 请求
              if (req.method !== 'GET' || !req.url) {
                return next();
              }
              // 跳过 API 请求
              if (req.url.startsWith('/api')) {
                return next();
              }
              // 跳过 Vite 内部请求（@vite, @react-refresh 等）
              if (req.url.startsWith('/@') || req.url.includes('__webpack')) {
                return next();
              }
              // 跳过静态资源（带扩展名的文件）
              if (path.extname(req.url)) {
                return next();
              }
              // 其他请求返回 index.html
              req.url = '/';
              next();
            });
          };
        },
      },
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      host: true,
      port: 13000,
      strictPort: true,  // 端口冲突时报错，禁止自动增长
      hmr: false,  // 禁用热刷新，避免多 agent 并行调试时相互干扰
      watch: {
        usePolling: true,
      },
      proxy: {
        // SSE 流式端点 —— 必须单独配置以防止代理缓冲
        '/api/agent/execute/stream': {
          target: apiTarget,
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              // 确保浏览器不会等待解压才渲染
              proxyRes.headers['content-encoding'] = 'identity';
              proxyRes.headers['x-accel-buffering'] = 'no';
              proxyRes.headers['cache-control'] = 'no-cache, no-transform';
            });
          },
        },
        // 所有其他 API 请求代理到后端 (包括 /api/auth)
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/health': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: apiTarget,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    preview: {
      host: true,
      port: 13000,
      strictPort: true,
      proxy: {
        // SSE 流式端点 —— 必须单独配置以防止代理缓冲
        '/api/agent/execute/stream': {
          target: apiTarget,
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('proxyRes', (proxyRes) => {
              proxyRes.headers['content-encoding'] = 'identity';
              proxyRes.headers['x-accel-buffering'] = 'no';
              proxyRes.headers['cache-control'] = 'no-cache, no-transform';
            });
          },
        },
        '/api': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/health': {
          target: apiTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: apiTarget,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    build: {
      chunkSizeWarningLimit: 1400,
    },
  };
});
