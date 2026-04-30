/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: { 50:'#f0f4ff', 100:'#dde6ff', 500:'#3b5bdb', 600:'#2f4cc7', 700:'#2340b0', 900:'#162a7e' },
        surface: { 0:'#ffffff', 1:'#f8fafc', 2:'#f1f5f9', 3:'#e2e8f0' },
      }
    }
  },
  plugins: []
}
