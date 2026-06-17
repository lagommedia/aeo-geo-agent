import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#0f1218',
        panel: '#171b24',
        accent: '#de6a45',
        ink: '#f2f4f8',
        muted: '#9ba3b5'
      }
    }
  },
  plugins: []
};

export default config;
