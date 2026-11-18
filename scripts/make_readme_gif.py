"""Build the README GIFs from the screenshots and shrink the images the README shows (Pillow only).

Two GIFs, so desktop and phone screens never share one canvas:
- docs/images/tour.gif: desktop browser windows, every frame cropped to 16:10
- docs/images/tour-phone.gif: phone screens

Usage: python scripts/make_readme_gif.py   (run `npm run screenshots` in web/ first)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

IMAGES = Path(__file__).resolve().parents[1] / "docs/images"
DESKTOP_FRAMES = [
    "resume-input.png",
    "discover.png",
    "jobs.png",
    "job-match.png",
    "tour-resume.png",
    "board.png",
    "profile.png",
]
PHONE_FRAMES = ["discover-phone.png", "jobs-phone.png", "job-phone.png", "board-phone.png"]
# Shown in the README and committed; the other screenshots are only GIF frames and stay untracked.
README_IMAGES = [
    "discover.png",
    "job-match.png",
    "job-resume.png",
    "board.png",
    "resume-input.png",
    "profile-gaps.png",
]
HOLD_MS = 2200


def make_gif(names: list[str], width: int, aspect: float, out: str) -> None:
    """Scale every frame to `width`, crop it to `aspect` (height / width) from the top, and save one GIF."""
    height = round(width * aspect)
    frames = []
    for name in names:
        image = Image.open(IMAGES / name).convert("RGB")
        scaled = image.resize((width, round(image.height * width / image.width)), Image.Resampling.LANCZOS)
        page = Image.new("RGB", (width, height), scaled.getpixel((4, scaled.height - 4)))
        page.paste(scaled.crop((0, 0, width, min(height, scaled.height))), (0, 0))
        frames.append(page.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    frames[0].save(IMAGES / out, save_all=True, append_images=frames[1:], duration=HOLD_MS, loop=0, optimize=True)
    print(f"wrote {IMAGES / out} ({width}x{height}, {len(frames)} frames)")


def main() -> None:
    make_gif(DESKTOP_FRAMES, 960, 900 / 1440, "tour.gif")
    make_gif(PHONE_FRAMES, 300, 844 / 390, "tour-phone.gif")

    for name in README_IMAGES:  # a 256-colour palette is about a third of the size and looks the same
        image = Image.open(IMAGES / name)
        if image.mode != "P":
            image.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(
                IMAGES / name, optimize=True
            )


if __name__ == "__main__":
    main()
