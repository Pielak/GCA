import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: [
      "localhost",
      "127.0.0.1",
      "gpd.code-auditor.com.br",
      "gca.code-auditor.com.br",
    ],
    proxy: {
      "/api": {
        target: process.env.VITE_API_URL || "http://127.0.0.1:8000",
        changeOrigin: true,
        timeout: 600000,
        proxyTimeout: 600000,
      },
    },
  },
  build: {
    target: "es2020",
    minify: "terser",
    sourcemap: false,
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          "form-vendor": ["react-hook-form", "zod"],
          "ui-vendor": ["lucide-react", "clsx"],
        },
        entryFileNames: "js/[name].[hash].js",
        chunkFileNames: "js/[name].[hash].js",
        assetFileNames: (assetInfo) => {
          const info = assetInfo.name.split(".");
          const ext = info[info.length - 1];
          if (/png|jpe?g|gif|tiff|bmp|ico/i.test(ext)) {
            return "images/[name].[hash][extname]";
          } else if (/woff|woff2|ttf|otf|eot/i.test(ext)) {
            return "fonts/[name].[hash][extname]";
          } else if (ext === "css") {
            return "css/[name].[hash][extname]";
          }
          return "[name].[hash][extname]";
        },
      },
    },
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
  },
  optimize: {
    esbuild: {
      supported: {
        "top-level-await": true,
      },
    },
  },
});
