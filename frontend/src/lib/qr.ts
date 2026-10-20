import QRCode from "qrcode";

/** Self-contained SVG (no external references). Quiet zone of 2 modules, dark-on-white so scanners always work. */
export function qrSvg(text: string): Promise<string> {
  return QRCode.toString(text, {
    type: "svg",
    margin: 2,
    errorCorrectionLevel: "M",
    color: { dark: "#000000", light: "#ffffff" },
  });
}

export function qrPngDataUrl(text: string, size = 512): Promise<string> {
  return QRCode.toDataURL(text, {
    margin: 2,
    width: size,
    errorCorrectionLevel: "M",
  });
}

export function downloadHref(href: string, filename: string) {
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export function downloadSvg(svg: string, filename: string) {
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  downloadHref(url, filename);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
