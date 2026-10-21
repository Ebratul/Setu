import { ImageResponse } from "next/og";

export const alt = "Setu — LC-grade protection for small importers";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background: "#0b3b3c",
          color: "#ffffff",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20, fontSize: 40, fontWeight: 700 }}>
          <svg width="72" height="72" viewBox="0 0 64 64">
            <path d="M6 44 Q32 8 58 44" fill="none" stroke="#f5b83d" strokeWidth="6" strokeLinecap="round" />
            <path d="M4 50 H60" stroke="#ffffff" strokeWidth="6" strokeLinecap="round" />
            <path d="M18 50 V32 M32 50 V22 M46 50 V32" stroke="#ffffff" strokeWidth="5" strokeLinecap="round" />
          </svg>
          Setu
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ fontSize: 68, fontWeight: 800, lineHeight: 1.1, maxWidth: 1000 }}>
            LC-grade protection for small importers
          </div>
          <div style={{ fontSize: 32, color: "#bfe3e0" }}>
            Bangladesh – China trade, with milestone escrow and human approval
          </div>
        </div>
        <div style={{ display: "flex", fontSize: 26, color: "#f5b83d" }}>
          Simulated sandbox · fictional data · FinTechathon 2026
        </div>
      </div>
    ),
    size,
  );
}
