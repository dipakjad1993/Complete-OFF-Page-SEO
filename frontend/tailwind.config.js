/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        // On 2026 Pixel phones this resolves to the on-device Pixel typeface
        // (Google Sans / Product Sans); everywhere else it falls through to Inter.
        sans: ['Google Sans', 'Product Sans', 'Inter', 'Roboto', 'system-ui', 'Avenir', 'Helvetica', 'Arial', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
