import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "path";
import AutoImport from "unplugin-auto-import/vite";
import Components from "unplugin-vue-components/vite";
import { ElementPlusResolver } from "unplugin-vue-components/resolvers";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 组件按需自动导入
    AutoImport({
      resolvers: [ElementPlusResolver()],
      imports: ["vue", "vue-router", "pinia"],
      dts: "src/auto-imports.d.ts",
    }),
    Components({
      resolvers: [ElementPlusResolver()],
      dts: "src/components.d.ts",
    }),
  ],

  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },

  css: {
    preprocessorOptions: {
      less: {
        javascriptEnabled: true,
        additionalData: `@import "@/styles/variables.less";`,
      },
    },
  },

  server: {
    port: 5173,
    host: "0.0.0.0",
    proxy: {
      // 开发环境代理 API 请求到后端
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        // SSE 流式接口需要禁用缓冲
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            if (req.url?.includes("/rag/chat-stream")) {
              proxyReq.setHeader("Connection", "keep-alive");
            }
          });
          // 上游 (后端) 中途断开时强制终结客户端响应:
          // 后端挂掉后 chunked 流没有结束块, 若代理不透传断开事件,
          // 浏览器 fetch 的 reader.read() 会永远挂起 (表现为无错误提示)
          proxy.on("proxyRes", (proxyRes, req, res) => {
            if (!req.url?.includes("/rag/chat-stream")) return;
            proxyRes.on("end", () => res.end());
            proxyRes.on("close", () => {
              if (!res.writableEnded) res.destroy();
            });
            proxyRes.on("error", () => {
              if (!res.writableEnded) res.destroy();
            });
          });
        },
      },
    },
  },

  build: {
    outDir: "dist",
    sourcemap: false,
    // element-plus 单 chunk 约 1.08MB (已按需引入, 再拆收益有限), 阈值放宽到 1.2MB
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          "element-plus": ["element-plus"],
          echarts: ["echarts", "vue-echarts"],
          vendor: ["vue", "vue-router", "pinia", "axios"],
        },
      },
    },
  },
});
