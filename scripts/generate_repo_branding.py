from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)

ROOT = Path(__file__).resolve().parents[1]


def _round_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def _draw_background(p: QPainter, width: int, height: int) -> None:
    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0.0, QColor("#11162b"))
    gradient.setColorAt(0.45, QColor("#141d34"))
    gradient.setColorAt(1.0, QColor("#0a1221"))
    p.fillRect(0, 0, width, height, gradient)

    # Diagonal atmospheric bands.
    band_pen = QPen(QColor(255, 255, 255, 8))
    band_pen.setWidth(max(1, width // 900))
    p.setPen(band_pen)
    spacing = max(34, width // 16)
    for x in range(-height, width + height, spacing):
        p.drawLine(x, 0, x + height, height)

    p.setPen(Qt.NoPen)
    p.setBrush(QColor(79, 203, 255, 22))
    p.drawEllipse(QRectF(-width * 0.16, -height * 0.15, width * 0.58, height * 0.7))
    p.setBrush(QColor(176, 120, 255, 18))
    p.drawEllipse(QRectF(width * 0.44, -height * 0.22, width * 0.64, height * 0.68))


def _draw_card(
    p: QPainter,
    image: QImage,
    rect: QRectF,
    radius: float,
    label: str | None = None,
) -> None:
    # Shadow
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 84))
    shadow_rect = QRectF(rect)
    shadow_rect.translate(0, max(4.0, rect.height() * 0.02))
    p.drawPath(_round_path(shadow_rect, radius))

    # Frame
    p.setBrush(QColor("#20273f"))
    p.drawPath(_round_path(rect, radius))

    if not image.isNull():
        src = QRectF(0, 0, image.width(), image.height())
        target_ratio = rect.width() / rect.height()
        src_ratio = src.width() / src.height()
        if src_ratio > target_ratio:
            crop_w = src.height() * target_ratio
            x = (src.width() - crop_w) / 2.0
            src = QRectF(x, 0, crop_w, src.height())
        else:
            crop_h = src.width() / target_ratio
            y = (src.height() - crop_h) / 2.0
            src = QRectF(0, y, src.width(), crop_h)

        p.save()
        p.setClipPath(_round_path(rect, radius))
        p.drawImage(rect, image, src)
        overlay = QLinearGradient(0, rect.top(), 0, rect.bottom())
        overlay.setColorAt(0.0, QColor(12, 18, 32, 22))
        overlay.setColorAt(1.0, QColor(8, 12, 24, 95))
        p.fillRect(rect, overlay)
        p.restore()

    p.setPen(QPen(QColor("#4fd8ff"), max(1.0, rect.height() * 0.012)))
    p.setBrush(Qt.NoBrush)
    p.drawPath(_round_path(rect.adjusted(1.0, 1.0, -1.0, -1.0), max(2.0, radius - 2.0)))

    if label:
        label_h = rect.height() * 0.15
        label_rect = QRectF(rect.left(), rect.bottom() - label_h, rect.width(), label_h)
        p.fillRect(label_rect, QColor(11, 18, 33, 185))
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPointSizeF(max(8.0, rect.height() * 0.038))
        p.setFont(font)
        p.setPen(QColor("#dff6ff"))
        p.drawText(label_rect.adjusted(12, 0, -12, 0), Qt.AlignVCenter | Qt.AlignLeft, label)


def _draw_chips(p: QPainter, rect: QRectF, labels: Sequence[str]) -> None:
    font = QFont("Segoe UI")
    font.setPointSizeF(max(8.0, rect.height() * 0.055))
    font.setBold(True)
    p.setFont(font)
    fm = QFontMetrics(font)

    x = rect.left()
    y = rect.top()
    for label in labels:
        text_w = fm.horizontalAdvance(label)
        chip_w = text_w + max(20, int(rect.height() * 0.08))
        chip_h = max(18, int(rect.height() * 0.16))
        if x + chip_w > rect.right():
            x = rect.left()
            y += chip_h + max(8, int(rect.height() * 0.06))
        chip = QRectF(x, y, chip_w, chip_h)
        p.setPen(QPen(QColor(79, 216, 255, 160), 1))
        p.setBrush(QColor(20, 36, 58, 150))
        p.drawRoundedRect(chip, chip_h / 2.0, chip_h / 2.0)
        p.setPen(QColor("#a6ecff"))
        p.drawText(chip, Qt.AlignCenter, label)
        x += chip_w + max(8, int(rect.height() * 0.05))


def _draw_logo_text(p: QPainter, rect: QRectF, logo: QImage) -> None:
    logo_size = min(rect.width() * 0.22, rect.height() * 0.24)
    logo_rect = QRectF(rect.left(), rect.top(), logo_size, logo_size)

    p.setPen(Qt.NoPen)
    p.setBrush(QColor(79, 216, 255, 48))
    p.drawEllipse(
        QRectF(
            logo_rect.left() - logo_size * 0.15,
            logo_rect.top() - logo_size * 0.15,
            logo_size * 1.3,
            logo_size * 1.3,
        )
    )

    if not logo.isNull():
        p.drawImage(logo_rect, logo)

    title_font = QFont("Segoe UI")
    title_font.setBold(True)
    title_font.setPointSizeF(max(22.0, rect.height() * 0.102))
    p.setFont(title_font)
    p.setPen(QColor("#f5f8ff"))
    p.drawText(
        QRectF(
            logo_rect.right() + rect.width() * 0.03,
            logo_rect.top(),
            rect.width() - logo_rect.width() - rect.width() * 0.03,
            logo_rect.height() * 0.62,
        ),
        Qt.AlignLeft | Qt.AlignVCenter,
        "GameHub",
    )

    subtitle_font = QFont("Segoe UI")
    subtitle_font.setPointSizeF(max(10.0, rect.height() * 0.04))
    p.setFont(subtitle_font)
    p.setPen(QColor("#a8bdd8"))
    p.drawText(
        QRectF(
            logo_rect.right() + rect.width() * 0.03,
            logo_rect.top() + logo_rect.height() * 0.54,
            rect.width() - logo_rect.width() - rect.width() * 0.03,
            logo_rect.height() * 0.46,
        ),
        Qt.AlignLeft | Qt.AlignTop,
        "Stylový launcher logických her, AI módů a PDF exportů.",
    )

    body_font = QFont("Segoe UI")
    body_font.setPointSizeF(max(10.0, rect.height() * 0.038))
    p.setFont(body_font)
    p.setPen(QColor("#d3e2f7"))
    description = (
        "9 her v jednotném design systému, plynulé UI, tisk/PDF, plugin architektura "
        "a release-ready desktop build pipeline."
    )
    p.drawText(
        QRectF(rect.left(), logo_rect.bottom() + rect.height() * 0.06, rect.width(), rect.height() * 0.22),
        Qt.TextWordWrap,
        description,
    )

    _draw_chips(
        p,
        QRectF(rect.left(), rect.bottom() - rect.height() * 0.2, rect.width(), rect.height() * 0.2),
        [
            "PySide6",
            "9 Games",
            "AI + Solvers",
            "PDF Export",
            "Plugin API",
            "Windows + Linux",
        ],
    )


def _load_image(path: Path) -> QImage:
    image = QImage(str(path))
    return image


def _render_composition(
    output: Path,
    width: int,
    height: int,
    logo_path: Path,
    home_path: Path,
    game_paths: Sequence[tuple[str, Path]],
) -> None:
    canvas = QImage(width, height, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    _draw_background(p, width, height)

    left = QRectF(width * 0.05, height * 0.11, width * 0.39, height * 0.78)
    _draw_logo_text(p, left, _load_image(logo_path))

    # Main home card
    home_rect = QRectF(width * 0.48, height * 0.13, width * 0.46, height * 0.48)
    _draw_card(p, _load_image(home_path), home_rect, radius=max(10.0, height * 0.02), label="Hub")

    # Lower cards
    card_y = height * 0.65
    card_h = height * 0.23
    gap = width * 0.015
    card_w = (width * 0.46 - gap * 2) / 3
    x = width * 0.48
    for i, (label, path) in enumerate(game_paths[:3]):
        rect = QRectF(x + i * (card_w + gap), card_y, card_w, card_h)
        _draw_card(p, _load_image(path), rect, radius=max(8.0, height * 0.016), label=label)

    p.end()
    output.parent.mkdir(parents=True, exist_ok=True)
    if not canvas.save(str(output)):
        raise RuntimeError(f"Failed to save branding image: {output}")


def _make_showcase_gif(output: Path, frames: Sequence[Path], size: tuple[int, int]) -> bool:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False

    width, height = size
    images: list[Image.Image] = []
    labels = {
        "home": "Hub",
        "sudoku": "Sudoku",
        "kenken": "KenKen",
        "slitherlink": "Slitherlink",
        "othello": "Othello",
        "game2048": "2048",
    }
    for source in frames:
        base = Image.open(source).convert("RGB")
        src_ratio = base.width / base.height
        dst_ratio = width / height
        if src_ratio > dst_ratio:
            crop_w = int(base.height * dst_ratio)
            left = (base.width - crop_w) // 2
            box = (left, 0, left + crop_w, base.height)
        else:
            crop_h = int(base.width / dst_ratio)
            top = (base.height - crop_h) // 2
            box = (0, top, base.width, top + crop_h)
        frame = base.crop(box).resize((width, height), Image.Resampling.LANCZOS)

        # Bottom gradient bar + caption.
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for y in range(int(height * 0.22)):
            alpha = int((y / max(1, int(height * 0.22))) * 170)
            draw.rectangle([(0, height - int(height * 0.22) + y), (width, height - int(height * 0.22) + y)], fill=(8, 12, 24, alpha))
        draw.rectangle([(22, 20), (300, 66)], outline=(79, 216, 255, 190), fill=(16, 32, 56, 120), width=2)
        label = labels.get(source.stem, source.stem.title())
        draw.text((36, 33), f"GameHub | {label}", fill=(223, 246, 255, 240))
        frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("P", palette=Image.Palette.ADAPTIVE)
        images.append(frame)

    output.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        output,
        save_all=True,
        append_images=images[1:],
        duration=[700] * len(images),
        loop=0,
        optimize=True,
    )
    return True


def generate(output_dir: Path) -> list[Path]:
    media = ROOT / "docs" / "media"
    logo = ROOT / "hub" / "assets" / "brainhub.png"
    home = media / "home.png"
    cards = [
        ("Sudoku", media / "sudoku.png"),
        ("Othello", media / "othello.png"),
        ("KenKen", media / "kenken.png"),
    ]
    outputs = [
        output_dir / "repo_hero.png",
        output_dir / "social_preview.png",
    ]

    for path in (logo, home, *(card for _, card in cards)):
        if not path.exists():
            raise FileNotFoundError(f"Missing required source image: {path}")

    _render_composition(
        output=output_dir / "repo_hero.png",
        width=1600,
        height=900,
        logo_path=logo,
        home_path=home,
        game_paths=cards,
    )
    _render_composition(
        output=output_dir / "social_preview.png",
        width=1280,
        height=640,
        logo_path=logo,
        home_path=home,
        game_paths=cards,
    )

    gif_sources = [
        media / "home.png",
        media / "sudoku.png",
        media / "kenken.png",
        media / "slitherlink.png",
        media / "othello.png",
        media / "game2048.png",
    ]
    if all(path.exists() for path in gif_sources):
        gif_path = output_dir / "showcase.gif"
        created = _make_showcase_gif(gif_path, gif_sources, size=(1280, 720))
        if created:
            outputs.append(gif_path)

    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate visual assets for GitHub repository branding.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "media",
        help="Destination for generated branding media.",
    )
    args = parser.parse_args()

    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication([])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated = generate(args.output_dir)
    for path in generated:
        if path.exists():
            print(f"[ok] {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
