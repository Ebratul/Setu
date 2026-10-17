"""Fabric "production photo" swatches (Pillow + numpy), with a known colour and width label."""

import io

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from synthetic.models import PhotoDoc

SIZE = (640, 480)


def render_photo(photo: PhotoDoc) -> bytes:
    """JPEG bytes. The dominant colour is `photo.rgb`; a tape measure shows the width label."""
    rng = np.random.default_rng(photo.seed)
    w, h = SIZE
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # weave: two thread directions plus a slight wave, then grain noise and a soft vignette
    wave = np.sin(xx / 2.1 + np.sin(yy / 37.0) * 1.5) + np.sin(yy / 1.9)
    grain = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
    shade = 1.0 + 0.045 * wave + 0.03 * grain
    cx, cy = w / 2, h / 2
    vignette = 1.0 - 0.28 * (((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / 2
    shade = (shade * vignette)[..., None]
    base = np.array(photo.rgb, dtype=np.float32)[None, None, :]
    pixels = np.clip(base * shade, 0, 255).astype(np.uint8)
    img = Image.fromarray(pixels, "RGB")

    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=13)
    # tape measure along the bottom
    top = h - 58
    draw.rectangle((0, top, w, h), fill=(236, 214, 120))
    span = photo.width_cm or 100
    for i in range(0, 61):
        x = 20 + i * (w - 40) / 60
        long_tick = i % 10 == 0
        draw.line((x, top, x, top + (22 if long_tick else 11)), fill=(40, 40, 40), width=1)
        if long_tick:
            draw.text((x - 8, top + 24), str(round(i / 60 * span)), font=small, fill=(40, 40, 40))
    label = f"Width: {photo.width_cm} cm" if photo.width_cm else "Colour swatch"
    draw.rectangle((10, 10, 330, 62), fill=(255, 255, 255))
    draw.text((16, 14), f"{photo.color_name}  |  {label}", font=font, fill=(20, 20, 20))
    draw.text((16, 38), "SIMULATED - FOR TESTING", font=small, fill=(110, 110, 110))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=False, progressive=False)
    return buf.getvalue()
