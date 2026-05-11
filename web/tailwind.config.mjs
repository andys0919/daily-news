export default {
  content: ["./src/**/*.{astro,html,ts,tsx,jsx,js,md}"],
  theme: {
    extend: {
      colors: {
        bg: { 950: "#0a0c10", 900: "#0f1218", 800: "#161b24" },
        accent: { 500: "#7aa2ff", 400: "#a5c0ff" },
        ok: { 500: "#3ddc97" },
        warn: { 500: "#ffae5c" },
        bad: { 500: "#ff6b81" },
      },
      fontFamily: {
        sans: ["Inter", "SF Pro Text", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
};
