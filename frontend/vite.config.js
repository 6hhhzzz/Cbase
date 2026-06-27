import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import http from 'http'

/**
 * SSE 流式代理插件 — 在 Vite 内置 proxy 之前拦截 /api/chat，
 * 用原生 http.request 转发，保证 SSE token 逐块到达浏览器。
 */
function sseProxyPlugin() {
  return {
    name: 'sse-proxy',
    enforce: 'pre',  // 关键：在 Vite 内置 proxy 之前注册
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        // 只拦截 SSE 问答请求
        if (req.url !== '/api/chat' || req.method !== 'POST') {
          return next()
        }

        // 收集请求 body
        const chunks = []
        for await (const chunk of req) {
          chunks.push(chunk)
        }
        const body = Buffer.concat(chunks)

        const proxyReq = http.request({
          hostname: '127.0.0.1',
          port: 8080,
          path: '/api/chat',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': String(body.length),
            'Authorization': req.headers['authorization'] || '',
          },
        }, (proxyRes) => {
          // 透传响应头，SSE 时加禁用缓冲头
          const headers = { ...proxyRes.headers }
          if (headers['content-type']?.includes('text/event-stream')) {
            headers['cache-control'] = 'no-cache, no-transform'
            headers['connection'] = 'keep-alive'
            headers['x-accel-buffering'] = 'no'
          }
          res.writeHead(proxyRes.statusCode, headers)

          // 禁用 Nagle 算法，确保 SSE 每个 chunk 立即发出
          if (res.socket) {
            res.socket.setNoDelay(true)
          }

          // 逐块转发，不使用 pipe（pipe 在某些 Node.js 版本可能缓冲）
          proxyRes.on('data', (chunk) => {
            res.write(chunk)
            // 每个 chunk 之后显式 flush，确保浏览器逐块接收
            if (typeof res.flush === 'function') {
              res.flush()
            }
          })
          proxyRes.on('end', () => res.end())
          proxyRes.on('error', () => { if (!res.writableEnded) res.end() })
        })

        proxyReq.on('error', () => {
          if (!res.headersSent) {
            res.writeHead(502, { 'Content-Type': 'application/json' })
          }
          res.end('{"error":"ai_service_unavailable","message":"AI 服务暂不可用"}')
        })

        proxyReq.write(body)
        proxyReq.end()
      })
    },
  }
}

export default defineConfig({
  plugins: [sseProxyPlugin(), vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
