import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const target = env.API_PROXY_TARGET || 'http://127.0.0.1:8000';
  const timeout = Number(env.VITE_API_TIMEOUT_MS || 300000) + 15000;
  const proxy = Object.fromEntries(
    ['/api', '/health'].map((path) => [
      path,
      {
        target,
        changeOrigin: true,
        timeout,
        proxyTimeout: timeout,
      },
    ]),
  );

  return {
    plugins: [react()],
    server: { port: 5173, strictPort: true, proxy },
    preview: { port: 4173, strictPort: true, proxy },
  };
});
