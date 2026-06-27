import { defineConfig, loadEnv } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import sveltePreprocess from 'svelte-preprocess';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiProxyTarget = env.VITE_API_PROXY_TARGET
    || env.VITE_API_BASE_URL
    || 'https://ps2-media-library-api.fly.dev';

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
    preview: {
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      copyPublicDir: true,
      emptyOutDir: true,
    },
  };
});
