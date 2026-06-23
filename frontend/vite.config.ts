import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import sveltePreprocess from 'svelte-preprocess';

export default defineConfig({
  plugins: [
    svelte({
      preprocess: sveltePreprocess(),
      compilerOptions: {
        css: 'external', // Force CSS extraction instead of injected
      },
    }),
  ],
  build: {
    copyPublicDir: true,
    emptyOutDir: true,
  },
});
