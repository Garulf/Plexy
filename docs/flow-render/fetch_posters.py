"""Download the posters used as result icons in the README screenshots.

The posters are non-free artwork, so they're fetched from Wikipedia into icons/ (git-ignored)
instead of being committed. Run with flow-render's Python, which has Pillow, then render:

    python fetch_posters.py
    flow-render -c search.json -o out    # from this directory, so hero.css resolves
"""
import json
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"
SIZE = 128
USER_AGENT = "plexy-readme-screenshots/1.0 (https://github.com/Garulf/Plexy)"

POSTERS = {
    "mi": "Mission: Impossible (film)",
    "mi-2": "Mission: Impossible 2",
    "mi-ghost-protocol": "Mission: Impossible – Ghost Protocol",
    "mi-fallout": "Mission: Impossible – Fallout",
    "mi-dead-reckoning": "Mission: Impossible – Dead Reckoning Part One",
    "toy-story": "Toy Story",
    "toy-story-2": "Toy Story 2",
    "toy-story-3": "Toy Story 3",
    "toy-story-logo": "Toy Story (franchise)",
    "cars": "Cars (film)",
    "cars-2": "Cars 2",
    "cars-3": "Cars 3",
    # TV series pages only have logos, so use a season page's poster
    "stranger-things": "Stranger Things season 1",
}
# Plex shows automatic collections as a mosaic of their films' posters
COLLECTIONS = {
    "mi-collection": ["mi", "mi-2", "mi-ghost-protocol", "mi-fallout"],
    "toy-story-collection": ["toy-story", "toy-story-2", "toy-story-3", "toy-story-logo"],
}


def get(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT})).read()


def fetch_sources() -> dict:
    query = urllib.parse.urlencode({
        "action": "query", "prop": "pageimages", "piprop": "thumbnail", "pilicense": "any",
        "pithumbsize": 400, "redirects": 1, "format": "json", "titles": "|".join(POSTERS.values()),
    })
    result = json.loads(get(f"https://en.wikipedia.org/w/api.php?{query}"))["query"]
    renamed = {item["from"]: item["to"] for item in result.get("normalized", []) + result.get("redirects", [])}
    pages = {page["title"]: page for page in result["pages"].values()}
    images = {}
    for slug, title in POSTERS.items():
        while title in renamed:
            title = renamed[title]
        images[slug] = Image.open(BytesIO(get(pages[title]["thumbnail"]["source"])))
    return images


def square(image: Image.Image, size: int = SIZE) -> Image.Image:
    image = image.convert("RGB")
    width, height = image.size
    side = min(width, height)
    # keep the upper middle of a poster, where the title art usually is
    left, top = (width - side) // 2, int((height - side) * 0.35)
    return image.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)


def main() -> None:
    ICONS.mkdir(exist_ok=True)
    images = fetch_sources()
    for slug, image in images.items():
        square(image).save(ICONS / f"{slug}.png")
    half = SIZE // 2
    for slug, members in COLLECTIONS.items():
        mosaic = Image.new("RGB", (SIZE, SIZE))
        for index, member in enumerate(members):
            mosaic.paste(square(images[member], half), ((index % 2) * half, (index // 2) * half))
        mosaic.save(ICONS / f"{slug}.png")
    print(f"Saved {len(list(ICONS.glob('*.png')))} icons to {ICONS}")


if __name__ == "__main__":
    main()
