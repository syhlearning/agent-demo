import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

export default defineConfig({
  plugins: [vue()],
  base: "/static/",
  build: {
    // 构建输出到 static/，FastAPI 直接提供静态文件
    outDir: path.resolve(__dirname, "../static"),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      // 开发时把请求转发，避免 CORS
      // '/chat': 'http://localhost:8000',  ← 旧版 FastAPI，已弃用
      // langgraph dev 默认端口 2024（内存模式），langgraph up 默认端口 8123（Docker+Postgres 模式）
      // 当前使用 langgraph up 启动，所以改为 8123
      "/threads": "http://localhost:8123", // LangGraph Server：thread 创建 + 流式对话
      "/upload": "http://localhost:8000",  // FastAPI：文件上传
      "/projects": "http://localhost:8000", // FastAPI：项目文件静态托管
      "/api": "http://localhost:8000",      // FastAPI：会话列表等 API
      "/auth": "http://localhost:8000",     // FastAPI：JWT 登录/刷新/退出
    },
  },
});
