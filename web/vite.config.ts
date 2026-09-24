import { defineConfig } from "vite";

// Two builds share this config:
//  - `npm run build`      -> served by FastAPI at "/" (fieldproof serve)
//  - `npm run build:demo` -> static Pages demo at "/fieldproof/", talking to
//    bundled fixture data instead of a live API (see src/datasource.ts)
export default defineConfig(({ mode }) => ({
  base: mode === "demo" ? "/fieldproof/" : "/",
  build: {
    outDir: mode === "demo" ? "dist-demo" : "dist",
    emptyOutDir: true,
    sourcemap: true,
  },
}));
