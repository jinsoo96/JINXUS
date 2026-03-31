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
      /* z-index 스케일 시스템 — 임의 값 사용 방지 */
      zIndex: {
        'dropdown': '10',
        'sticky': '20',
        'overlay': '30',
        'modal': '40',
        'popover': '50',
        'toast': '100',
      },
      /* 일관된 트랜지션 토큰 */
      transitionDuration: {
        'micro': '150ms',   // 마이크로 인터랙션 (hover, active)
        'normal': '250ms',  // 일반 전환 (패널, 모달)
        'slow': '400ms',    // 복잡한 전환
      },
      transitionTimingFunction: {
        'enter': 'cubic-bezier(0, 0, 0.2, 1)',   // ease-out (등장)
        'exit': 'cubic-bezier(0.4, 0, 1, 1)',     // ease-in (퇴장)
        'spring': 'cubic-bezier(0.34, 1.56, 0.64, 1)', // 탄성
      },
      /* 아이콘 크기 토큰 */
      spacing: {
        'icon-sm': '16px',
        'icon-md': '20px',
        'icon-lg': '24px',
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}
