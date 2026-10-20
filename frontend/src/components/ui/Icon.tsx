import type { SVGProps } from "react";

const PATHS = {
  check: "M5 12.5l4.5 4.5L19 7.5",
  x: "M6 6l12 12M18 6L6 18",
  info: "M12 8v.01M11 12h1v5h1M12 21a9 9 0 100-18 9 9 0 000 18z",
  warn: "M12 9v4m0 4v.01M10.3 4.2L2.6 18a2 2 0 001.7 3h15.4a2 2 0 001.7-3L13.7 4.2a2 2 0 00-3.4 0z",
  shield: "M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6l8-3zM9 12l2 2 4-4",
  lock: "M7 11V8a5 5 0 0110 0v3M6 11h12v9H6z",
  ban: "M12 21a9 9 0 100-18 9 9 0 000 18zM5.6 5.6l12.8 12.8",
  circle: "M12 20a8 8 0 100-16 8 8 0 000 16z",
  clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2",
  arrow: "M5 12h14M13 6l6 6-6 6",
  menu: "M4 7h16M4 12h16M4 17h16",
  search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4",
  bell: "M6 16V11a6 6 0 1112 0v5l2 2H4l2-2zM10 21h4",
  sun: "M12 16a4 4 0 100-8 4 4 0 000 8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5",
  moon: "M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z",
  chevron: "M9 6l6 6-6 6",
  chevronDown: "M6 9l6 6 6-6",
  home: "M4 11l8-7 8 7v9h-5v-6H9v6H4z",
  box: "M3 7l9-4 9 4v10l-9 4-9-4V7zM3 7l9 4 9-4M12 11v10",
  trend: "M3 17l6-6 4 4 8-9M15 6h6v6",
  coins: "M12 8c4.4 0 8-1.1 8-2.5S16.4 3 12 3 4 4.1 4 5.5 7.6 8 12 8zM4 5.5v4C4 10.9 7.6 12 12 12s8-1.1 8-2.5v-4M4 9.5v4c0 1.4 3.6 2.5 8 2.5s8-1.1 8-2.5v-4M4 13.5v4C4 18.9 7.6 20 12 20s8-1.1 8-2.5v-4",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  file: "M7 3h7l5 5v13H7V3zM14 3v5h5M10 13h6M10 17h6",
  users: "M9 11a3 3 0 100-6 3 3 0 000 6zM3 20c0-3 2.7-5 6-5s6 2 6 5M16 11a3 3 0 000-6M18 15c2 .6 3 2.3 3 5",
  chat: "M4 5h16v11H9l-5 4V5z",
  gear: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 13a7.6 7.6 0 000-2l2-1.5-2-3.5-2.3.9a7.5 7.5 0 00-1.7-1L15 3h-4l-.4 2.9a7.5 7.5 0 00-1.7 1L6.6 6 4.6 9.5 6.6 11a7.6 7.6 0 000 2l-2 1.5 2 3.5 2.3-.9c.5.4 1.1.8 1.7 1L11 21h4l.4-2.9c.6-.2 1.2-.6 1.7-1l2.3.9 2-3.5-2-1.5z",
  globe: "M12 21a9 9 0 100-18 9 9 0 000 18zM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3zM19 16l.7 2 2 .7-2 .7L19 21l-.7-1.6-2-.7 2-.7L19 16z",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z",
  plus: "M12 5v14M5 12h14",
  external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  quote: "M6 17c0-4 1-7 4-9M14 17c0-4 1-7 4-9",
  play: "M8 5v14l11-7L8 5z",
  swap: "M4 8h14l-3-3M20 16H6l3 3",
  mail: "M3 6h18v12H3V6zM3 7l9 6 9-6",
  panel: "M4 5h16v14H4V5zM9 5v14M14 10l-2 2 2 2",
  scale: "M12 4v16M6 20h12M5 8h14M5 8l-3 7a3 3 0 006 0L5 8zm14 0l-3 7a3 3 0 006 0l-3-7z",
} as const;

export type IconName = keyof typeof PATHS;

type Props = Omit<SVGProps<SVGSVGElement>, "name"> & { name: IconName; size?: number; title?: string };

/** Self-made stroke icon set (original paths, no third-party assets). Decorative unless `title` is set. */
export function Icon({ name, size = 18, title, ...rest }: Props) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
