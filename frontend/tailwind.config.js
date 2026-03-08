/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#d4a853',
          hover: '#c9952e',
          light: '#e6c87a',
          dark: '#b8860b',
        },
        gold: {
          50: '#fefce8',
          100: '#fef9c3',
          200: '#fef08a',
          300: '#fde047',
          400: '#facc15',
          500: '#d4a853',
          600: '#b8860b',
          700: '#a16207',
          800: '#854d0e',
          900: '#713f12',
        },
        dark: {
          bg: '#0a0a0b',
          card: '#141414',
          card2: '#1a1a1c',
          border: '#2a2a2e',
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
