import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#ff2442",
          light: "#fef2f0",
          dark: "#e02447",
        },
        bg: "#FDFBF7",
        surface: {
          DEFAULT: "#ffffff",
          hover: "#F6F3EC",
        },
        text: {
          DEFAULT: "#1C1B18",
          secondary: "#6B5E53",
        },
        border: {
          DEFAULT: "#EFECE3",
          light: "#F6F3EC",
        },
        tag: {
          bg: "#F6F3EC",
          border: "#E5DFD3",
          text: "#C04B3A",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          '"SF Pro Text"',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          '"Noto Sans SC"',
          "sans-serif",
        ],
      },
      borderRadius: {
        card: "20px",
        btn: "30px",
        chip: "20px",
        sm: "12px",
      },
      boxShadow: {
        card: "0 4px 20px rgba(180, 170, 155, 0.12), 0 1px 3px rgba(180, 170, 155, 0.06)",
        "card-hover":
          "0 20px 40px -5px rgba(197, 184, 160, 0.45), 0 4px 12px rgba(197, 184, 160, 0.15)",
        elevated: "0 8px 28px rgba(197, 184, 160, 0.18)",
      },
      spacing: {
        sidebar: "260px",
        header: "60px",
      },
    },
  },
} satisfies Config;
