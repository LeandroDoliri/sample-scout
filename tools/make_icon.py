"""Genera icon.ico (multi-tamaño) e icon.png. Uso: python tools/make_icon.py  (requiere Pillow)"""
import os

from PIL import Image, ImageDraw, ImageFilter

TOP, BOTTOM = (20, 184, 166), (15, 118, 110)   # teal-500 -> teal-700
# Alturas relativas de las barras de la forma de onda
BARS = (0.28, 0.55, 0.85, 1.0, 0.7, 0.45, 0.25)


def lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def render(size):
    S = 8  # supersampling
    W = size * S
    small = size <= 32
    margin = (0.03 if small else 0.06) * W
    radius = (0.22 if small else 0.235) * W
    grad = Image.new("RGB", (W, W))
    gd = ImageDraw.Draw(grad)
    for y in range(W):
        gd.line([(0, y), (W, y)], fill=lerp(TOP, BOTTOM, y / W))
    glow = Image.new("L", (W, W), 0)
    ImageDraw.Draw(glow).ellipse([-0.4 * W, -0.55 * W, 0.9 * W, 0.55 * W], fill=38)
    glow = glow.filter(ImageFilter.GaussianBlur(W * 0.08))
    grad = Image.composite(Image.new("RGB", (W, W), (255, 255, 255)), grad, glow)
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, W - margin, W - margin], radius, fill=255)
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    # Forma de onda: barras redondeadas centradas (en tamaños chicos, menos y más gruesas)
    bars = BARS[1:-1] if small else BARS
    layer = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    span = (0.66 if small else 0.58) * W
    step = span / len(bars)
    bar_w = step * (0.62 if small else 0.55)
    max_h = (0.62 if small else 0.54) * W
    x0 = W / 2 - span / 2 + (step - bar_w) / 2
    for i, h in enumerate(bars):
        x = x0 + i * step
        bh = max(bar_w, h * max_h)
        d.rounded_rectangle([x, W / 2 - bh / 2, x + bar_w, W / 2 + bh / 2], bar_w / 2,
                            fill=(255, 255, 255, 255))

    shadow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    shadow.putalpha(layer.getchannel("A").point(lambda a: a * 0.28))
    shadow = shadow.filter(ImageFilter.GaussianBlur(W * 0.012))
    img.alpha_composite(shadow, (0, round(W * 0.012)))
    img.alpha_composite(layer)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    images = [render(s) for s in sizes]
    images[-1].save(os.path.join(root, "icon.ico"), sizes=[(s, s) for s in sizes],
                    append_images=images[:-1])
    render(512).save(os.path.join(root, "icon.png"))
    print("icon.ico e icon.png generados")
