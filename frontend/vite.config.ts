import { defineConfig, loadEnv } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import sveltePreprocess from 'svelte-preprocess';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000';

  return {
    plugins: [
      svelte({
        preprocess: sveltePreprocess(),
        compilerOptions: {
          css: 'external', // Force CSS extraction instead of injected
        },
      }),
    ],
    server: {
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
      watch: {
        ignored: ['**/build/**'],
      },
    },
    build: {
      copyPublicDir: true,
      emptyOutDir: true,
    },
  };
});
