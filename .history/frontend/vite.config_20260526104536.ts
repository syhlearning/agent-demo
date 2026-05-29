import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

export default defineConfig({
  plugins: [vue()],
  build: {
    // 构建输出到 static/，FastAPI 直接提供静态文件
    outDir: path.resolve(__dirname, "../static"),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      // 开发时把请求转发到 FastAPI
      // '/chat': 'http://localhost:8000',
      "/upload": "http://localhost:8000",
    },
  },
});
