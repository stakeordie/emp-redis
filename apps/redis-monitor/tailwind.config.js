/** @type {import('tailwindcss').Config} */
module.exports = {
  // Configure content paths for the project structure
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/lib/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      // Update font family to use Inter font variable
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      // Add any additional theme customizations here
    },
  },
  // Add any Tailwind CSS plugins if needed
  plugins: [],
};
