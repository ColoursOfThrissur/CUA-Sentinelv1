/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: 'rgba(255,255,255,0.04)',
          hover: 'rgba(255,255,255,0.07)',
          border: 'rgba(255,255,255,0.08)',
        },
        accent: {
          DEFAULT: '#6366f1',
          hover: '#818cf8',
        },
        status: {
          running: '#22d3ee',
          completed: '#4ade80',
          failed: '#f87171',
          queued: '#facc15',
          preempted: '#fb923c',
        },
      },
      backdropBlur: { xs: '2px' },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
