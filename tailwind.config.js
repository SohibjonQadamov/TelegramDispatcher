/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: '#00000b',
        'on-primary': '#ffffff',
        'primary-container': '#1a1a2e',
        secondary: '#af2b3e',
        'on-secondary': '#ffffff',
        'secondary-fixed': '#ffdada',
        tertiary: '#695d3c',
        surface: '#fcf8fa',
        'on-surface': '#1c1b1d',
        'on-surface-variant': '#47464c',
        'surface-container': '#f1edef',
        'surface-container-low': '#f6f2f4',
        'surface-container-highest': '#e5e1e3',
        outline: '#78767d',
        'outline-variant': '#c8c5cd',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
};