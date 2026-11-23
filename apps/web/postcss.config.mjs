/**
 * PostCSS configuration.
 *
 * Tailwind v4 ships as a PostCSS plugin (`@tailwindcss/postcss`) and — unlike v3 — needs no
 * `tailwind.config.js` and no `autoprefixer`. Design tokens are declared in CSS itself, via
 * the `@theme` block in app/globals.css.
 *
 * If you are looking for `tailwind.config.js`: it does not exist, and that is correct for v4.
 * Its absence is a decision, not an oversight.
 */
export default {
  plugins: {
    '@tailwindcss/postcss': {},
  },
};
