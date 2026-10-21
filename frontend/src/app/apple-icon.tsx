import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#0b3b3c" }}>
        <svg width="140" height="140" viewBox="0 0 64 64">
          <path d="M6 44 Q32 8 58 44" fill="none" stroke="#f5b83d" strokeWidth="6" strokeLinecap="round" />
          <path d="M4 50 H60" stroke="#ffffff" strokeWidth="6" strokeLinecap="round" />
          <path d="M18 50 V32 M32 50 V22 M46 50 V32" stroke="#ffffff" strokeWidth="5" strokeLinecap="round" />
        </svg>
      </div>
    ),
    size,
  );
}
