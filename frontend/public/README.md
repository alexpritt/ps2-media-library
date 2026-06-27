Frontend Public Assets

Static assets in this folder are published by Cloudflare Pages.

- Keep `ps2-intro.en.vtt` here so the boot-video captions are available at `/ps2-intro.en.vtt`.
- The boot screen supports separate desktop and mobile intro sources.
- `VITE_BOOT_INTRO_SRC` should point at the full hosted intro, typically `https://media.theavenoircollection.com/ps2-intro1080.mp4`.
- `VITE_BOOT_MOBILE_SRC` should point at a smaller mobile-optimized clip, for example `https://media.theavenoircollection.com/ps2-intro720.mp4`.
