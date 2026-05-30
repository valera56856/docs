/**
 * PostCSS configuration — Vite auto-detects and applies this to all CSS.
 *
 * Pipeline: Tailwind generates the utility classes used across components, then
 * Autoprefixer adds vendor prefixes for the mobile browsers the PWA targets.
 */
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
