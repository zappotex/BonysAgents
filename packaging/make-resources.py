#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Erzeugt Logo, Icons und Hintergrundbilder aus den Originalen in Bilder/.

    python3 packaging/make-resources.py

Braucht Pillow. Die Originale werden nicht verändert.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "Bilder"
OUT = ROOT / "src" / "bonys_agents" / "resources"
WIN = ROOT / "packaging" / "windows"
MAC = ROOT / "packaging" / "macos"


def save_jpeg_under(img: Image.Image, path: Path, max_kb: int) -> None:
    """Als JPEG speichern – mit der höchsten Qualität, die unter max_kb bleibt."""
    for quality in range(90, 40, -5):
        img.save(path, "JPEG", quality=quality, optimize=True, progressive=True)
        if path.stat().st_size <= max_kb * 1024:
            return
    raise SystemExit(f"{path.name}: auch mit niedriger Qualität größer als {max_kb} KB")


def border_color(img: Image.Image, frame: int = 4) -> str:
    """Mittlere Farbe des äußeren Rahmens (``frame`` Pixel) als #rrggbb."""
    w, h = img.size
    px = []
    for box in ((0, 0, w, frame), (0, h - frame, w, h), (0, frame, frame, h - frame), (w - frame, frame, w, h - frame)):
        px += list(img.crop(box).getdata())
    return "#" + "".join(f"{round(sum(p[i] for p in px) / len(px)):02x}" for i in range(3))


def main() -> None:
    logo = Image.open(SRC / "logo.jpg").convert("RGB")
    banner = Image.open(SRC / "hintergrund_program.png").convert("RGB")
    agent_bg = Image.open(SRC / "hintergrund_program_neu.png").convert("RGB")

    logo.resize((512, 512), Image.LANCZOS).save(OUT / "logo.png", optimize=True)
    logo.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png", optimize=True)
    sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    logo.save(OUT / "icon.ico", sizes=sizes)
    # macOS-Programmsymbol (Finder, Dock, Programme-Ordner) – Pillow erzeugt alle Größen bis 1024 px.
    MAC.mkdir(exist_ok=True)
    logo.save(MAC / "icon.icns")

    # Programm-Hintergrund: höchstens 1920 px breit (die App dunkelt ihn selbst ab).
    bg = banner
    if bg.width > 1920:
        bg = bg.resize((1920, round(bg.height * 1920 / bg.width)), Image.LANCZOS)
    save_jpeg_under(bg, OUT / "background.jpg", 400)

    # Desktop-Hintergrund im Agent-PC (ab 0.19): eigenes, dunkleres Bild – höchstens 3840 px breit, nie
    # hochgerechnet, kompakt. Die Randfarbe (dort, wo das skalierte Bild den Bildschirm nicht füllt) kommt aus dem
    # Bild selbst und steht in desktops.WALLPAPER_BORDER (ein Test prüft, dass beides zusammenpasst).
    wp = agent_bg
    if wp.width > 3840:
        wp = wp.resize((3840, round(wp.height * 3840 / wp.width)), Image.LANCZOS)
    save_jpeg_under(wp, OUT / "wallpaper.jpg", 300)
    print(f"Randfarbe des Agent-PC-Hintergrunds: {border_color(wp)}  (→ desktops.WALLPAPER_BORDER)")

    # Inno-Setup-Assistent (WizardStyle=modern): Seitenbild 164x314, kleines Bild 55x55 – je 100 % und 200 %.
    # Nachtblauer Verlauf (Farben der App) mit dem ganzen Logo – der Schriftzug passt so vollständig hinein.
    for scale in (1, 2):
        w, h = 164 * scale, 314 * scale
        tall = Image.composite(Image.new("RGB", (w, h), (6, 10, 15)), Image.new("RGB", (w, h), (22, 33, 48)),
                               Image.linear_gradient("L").resize((w, h)))
        tall.paste(logo.resize((w, w), Image.LANCZOS), (0, round(h * 0.4 - w / 2)))
        tall.save(WIN / f"wizard-{w}.bmp")
        logo.resize((55 * scale, 55 * scale), Image.LANCZOS).save(WIN / f"wizard-small-{55 * scale}.bmp")

    for p in [OUT / f for f in ("logo.png", "icon.png", "icon.ico", "background.jpg", "wallpaper.jpg")] \
            + sorted(WIN.glob("wizard-*.bmp")) + [MAC / "icon.icns"]:
        print(f"{p.name:22} {p.stat().st_size / 1024:6.0f} KB  {Image.open(p).size}")


if __name__ == "__main__":
    main()
