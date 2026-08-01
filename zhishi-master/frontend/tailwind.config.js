/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // 主色 - 紫色强调
        primary: {
          DEFAULT: "hsl(var(--color-primary))",
          hover: "hsl(var(--color-primary-hover))",
          active: "hsl(var(--color-primary-active))",
          soft: "hsl(var(--color-primary-soft))",
          subtle: "hsl(var(--color-primary-subtle))",
          foreground: "0 0% 100%",
        },
        // 中性色 - 背景
        bg: {
          DEFAULT: "hsl(var(--color-bg))",
          subtle: "hsl(var(--color-bg-subtle))",
        },
        surface: {
          DEFAULT: "hsl(var(--color-surface))",
          soft: "hsl(var(--color-surface-soft))",
        },
        // 中性色 - 文字
        ink: {
          primary: "hsl(var(--color-text-primary))",
          secondary: "hsl(var(--color-text-secondary))",
          tertiary: "hsl(var(--color-text-tertiary))",
          disabled: "hsl(var(--color-text-disabled))",
        },
        // 边框
        line: {
          DEFAULT: "hsl(var(--color-border))",
          soft: "hsl(var(--color-border-soft))",
        },
        // 功能色
        success: {
          DEFAULT: "hsl(var(--color-success))",
          soft: "hsl(var(--color-success-soft))",
          foreground: "0 0% 100%",
        },
        warning: {
          DEFAULT: "hsl(var(--color-warning))",
          soft: "hsl(var(--color-warning-soft))",
          foreground: "0 0% 100%",
        },
        danger: {
          DEFAULT: "hsl(var(--color-danger))",
          soft: "hsl(var(--color-danger-soft))",
          foreground: "0 0% 100%",
        },
        info: {
          DEFAULT: "hsl(var(--color-info))",
          soft: "hsl(var(--color-info-soft))",
          foreground: "0 0% 100%",
        },
        // 兼容 shadcn 既有令牌
        border: "hsl(var(--color-border))",
        input: "hsl(var(--color-border))",
        ring: "hsl(var(--color-primary))",
        background: "hsl(var(--color-bg))",
        foreground: "hsl(var(--color-text-primary))",
        card: {
          DEFAULT: "hsl(var(--color-surface))",
          foreground: "hsl(var(--color-text-primary))",
        },
        popover: {
          DEFAULT: "hsl(var(--color-surface))",
          foreground: "hsl(var(--color-text-primary))",
        },
        secondary: {
          DEFAULT: "hsl(var(--color-surface-soft))",
          foreground: "hsl(var(--color-text-primary))",
        },
        muted: {
          DEFAULT: "hsl(var(--color-surface-soft))",
          foreground: "hsl(var(--color-text-secondary))",
        },
        accent: {
          DEFAULT: "hsl(var(--color-primary-soft))",
          foreground: "hsl(var(--color-primary-active))",
        },
        destructive: {
          DEFAULT: "hsl(var(--color-danger))",
          foreground: "0 0% 100%",
        },
        sidebar: {
          DEFAULT: "0 0% 100%",
          foreground: "hsl(var(--color-text-secondary))",
          primary: "hsl(var(--color-primary))",
          "primary-foreground": "0 0% 100%",
          accent: "hsl(var(--color-primary-soft))",
          "accent-foreground": "hsl(var(--color-primary-active))",
          border: "hsl(var(--color-border-soft))",
          ring: "hsl(var(--color-primary))",
        },
      },
      borderRadius: {
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        "2xl": "var(--radius-xl)",
        full: "var(--radius-full)",
      },
      boxShadow: {
        xs: "var(--shadow-sm)",
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
        primary: "var(--shadow-primary)",
      },
      fontSize: {
        "page-title": ["28px", { lineHeight: "36px", fontWeight: "700" }],
        "section-title": ["20px", { lineHeight: "28px", fontWeight: "650" }],
        "card-title": ["16px", { lineHeight: "24px", fontWeight: "600" }],
        "body": ["14px", { lineHeight: "22px", fontWeight: "400" }],
        "caption": ["13px", { lineHeight: "20px", fontWeight: "400" }],
        "small": ["12px", { lineHeight: "18px", fontWeight: "400" }],
      },
      fontFamily: {
        sans: ['Inter', 'SF Pro Display', 'PingFang SC', 'Microsoft YaHei', 'sans-serif'],
      },
      transitionDuration: {
        "160": "160ms",
        "180": "180ms",
        "220": "220ms",
      },
      keyframes: {
        "page-in": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "panel-in": {
          from: { opacity: "0", transform: "translateX(16px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        "msg-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "page-in": "page-in 180ms ease-out both",
        "panel-in": "panel-in 220ms ease-out both",
        "msg-in": "msg-in 240ms ease-out both",
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
