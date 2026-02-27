import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f3f2ed',
        panel: '#fffdf8',
        accent: '#c3472c',
        ink: '#1b1b1b',
        muted: '#5f5c56'
      }
    }
  },
  plugins: []
};

export default config;
