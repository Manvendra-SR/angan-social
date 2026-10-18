import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // strictPort: fail loudly if 5173 is busy instead of silently moving to
  // 5174, which the backend's CORS_ORIGINS would not allow
  server: { port: 5173, strictPort: true },
});
