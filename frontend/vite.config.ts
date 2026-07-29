import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API is same-origin through this proxy, so the browser never makes a
// cross-origin request and no CORS relaxation is needed. Applied to `preview` as well
// as `dev` because the Definition of Done is verified against the *built* bundle, and
// a proxy that existed only in dev would make that check impossible to run.
const proxy = {
  "/api": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/api/, ""),
  },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, proxy },
});
