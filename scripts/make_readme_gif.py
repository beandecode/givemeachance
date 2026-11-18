"""Build docs/images/tour.gif from the screenshots and shrink the ones the README shows (Pillow only).

Usage: python scripts/make_readme_gif.py   (run `npm run screenshots` in web/ first)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

IMAGES = Path(__file__).resolve().parents[1] / "docs/images"
FRAMES = ["resume-input.png", "discover.png", "jobs.png", "job-match.png", "job-resume.png", "board.png", "profile.png"]
# Shown in the README and committed; the other screenshots are only GIF frames and stay untracked.
README_IMAGES = [
    "discover.png",
    "job-match.png",
    "job-resume.png",
    "board.png",
    "resume-input.png",
    "profile-gaps.png",
    "discover-phone.png",
    "job-phone.png",
]
WIDTH = 960
HOLD_MS = 2200


def main() -> None:
    frames = []
    for name in FRAMES:
        image = Image.open(IMAGES / name).convert("RGB")
        height = round(image.height * WIDTH / image.width)
        frames.append(image.resize((WIDTH, height), Image.Resampling.LANCZOS))
    height = max(frame.height for frame in frames)
    canvas = []
    for frame in frames:  # same size for every frame; centre shorter shots on the page background
        page = Image.new("RGB", (WIDTH, height), frame.getpixel((4, frame.height - 4)))
        page.paste(frame, (0, (height - frame.height) // 2))
        canvas.append(page.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    canvas[0].save(
        IMAGES / "tour.gif", save_all=True, append_images=canvas[1:], duration=HOLD_MS, loop=0, optimize=True
    )
    print(f"wrote {IMAGES / 'tour.gif'}")

    for name in README_IMAGES:  # a 256-colour palette is about a third of the size and looks the same
        image = Image.open(IMAGES / name)
        if image.mode != "P":
            image.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(
                IMAGES / name, optimize=True
            )


if __name__ == "__main__":
    main()
