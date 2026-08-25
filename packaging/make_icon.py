"""Генератор иконки Codex Switcher.

Запуск из корня репозитория:  python packaging/make_icon.py
Создаёт assets/icon.png (мастер 1024 + 512 для рантайма),
assets/icon.ico (Windows) и assets/icon.icns (macOS).
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

# Палитра из theme.py
BG_TOP = (0x1C, 0x1C, 0x1F, 0xFF)
BG_BOTTOM = (0x05, 0x05, 0x05, 0xFF)
BORDER = (0x26, 0x26, 0x26, 0xFF)
ARROW_UP = (0xED, 0xED, 0xED, 0xFF)   # text_primary
ARROW_DOWN = (0x00, 0x70, 0xF3, 0xFF)  # accent_blue

S = 4  # суперсэмплинг: рисуем в S раз больше и уменьшаем
CANVAS = 1024 * S


def rounded_gradient_bg(size: int) -> Image.Image:
    """Чёрный скруглённый квадрат с лёгким вертикальным градиентом."""
    # вертикальный градиент
    grad = Image.linear_gradient("L").resize((size, size))
    bg_top = Image.new("RGBA", (size, size), BG_TOP)
    bg_bottom = Image.new("RGBA", (size, size), BG_BOTTOM)
    img = Image.composite(bg_bottom, bg_top, grad)

    mask = Image.new("L", (size, size), 0)
    radius = int(size * 0.22)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=255
    )
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)

    # тонкая рамка для читаемости на светлом фоне
    draw = ImageDraw.Draw(out)
    inset = max(1, size // 512)
    draw.rounded_rectangle(
        [inset, inset, size - 1 - inset, size - 1 - inset],
        radius=radius - inset,
        outline=BORDER,
        width=inset,
    )
    return out


def arrow(draw: ImageDraw.ImageDraw, y: int, x_from: int, x_to: int,
          color, shaft: int) -> None:
    """Горизонтальная стрелка ⇄ со скруглённым торцом и треугольным наконечником."""
    head_len = int(shaft * 2.2)
    half_head = int(shaft * 1.35)
    direction = 1 if x_to > x_from else -1
    body_end = x_to - direction * head_len

    draw.line([x_from, y, body_end, y], fill=color, width=shaft)
    r = shaft // 2
    draw.ellipse([min(x_from, x_from) - r, y - r, x_from + r, y + r], fill=color)
    draw.polygon(
        [
            (body_end, y - half_head),
            (body_end, y + half_head),
            (x_to, y),
        ],
        fill=color,
    )


def build_icon() -> Image.Image:
    img = rounded_gradient_bg(CANVAS)
    draw = ImageDraw.Draw(img)

    shaft = 74 * S
    top_y = 402 * S
    bottom_y = 622 * S
    margin = 236 * S

    # верхняя: слева направо (белая), нижняя: справа налево (синяя)
    arrow(draw, top_y, margin, CANVAS - margin, ARROW_UP, shaft)
    arrow(draw, bottom_y, CANVAS - margin, margin, ARROW_DOWN, shaft)

    return img.resize((1024, 1024), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    master = build_icon()

    master.save(ASSETS / "icon.png")                       # мастер 1024
    master.resize((512, 512), Image.LANCZOS).save(
        ASSETS / "icon-512.png"
    )                                                      # рантайм (iconphoto)
    base_256 = master.resize((256, 256), Image.LANCZOS)
    base_256.save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
               (64, 64), (128, 128), (256, 256)],
    )                                                      # Windows exe/инсталлятор
    base_256.save(ASSETS / "icon.icns")                    # macOS бандл
    print("written:", ", ".join(sorted(p.name for p in ASSETS.iterdir())))


if __name__ == "__main__":
    main()
