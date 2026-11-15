"""Render the README screenshots and hero image with flow-render.

Usage (from the repo root):

    uv run --no-project --with flow-render==0.15.0 --with pip --with wheel python docs/flow-render/render.py

Each ``<shot>.json`` here is a flow-render config, rendered once per Windows 11
theme into ``.github/assets/<shot>-<theme>.png``. ``hero.json`` is rendered once
with ``hero.css`` on top of the dark theme. The posters used as result icons are
fetched by ``fetch_posters.py`` on the first run. Pass shot names (``search``,
``hero``, ``install``, ...) to render only those.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import fetch_posters

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ASSETS_DIR = ROOT / ".github" / "assets"
THEMES = ("light", "dark")
HERO = "hero"


def flow_render(args, out_path: Path) -> None:
    with tempfile.TemporaryDirectory() as out_dir:
        subprocess.run(["flow-render", *args, "-o", out_dir], check=True, cwd=HERE)
        (rendered,) = Path(out_dir).glob("*.png")
        shutil.move(str(rendered), out_path)
    print(f"Wrote {out_path.relative_to(ROOT)}")


def absolute(path: str) -> str:
    candidate = HERE / path
    return str(candidate.resolve()) if candidate.exists() else path


def render_config(shot: str, css, out_path: Path, work: Path) -> None:
    config = json.loads((HERE / f"{shot}.json").read_text(encoding="utf-8"))
    config["icon"] = absolute(config["icon"])
    for result in config["results"]:
        result["icon"] = absolute(result["icon"])
    config["css"] = css
    config_path = work / f"{shot}-{out_path.stem}.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    flow_render(["-c", str(config_path)], out_path)


def main(only=()) -> None:
    if not fetch_posters.ICONS.is_dir() or not any(fetch_posters.ICONS.glob("*.png")):
        fetch_posters.main()
    shots = sorted(path.stem for path in HERE.glob("*.json") if path.stem != HERO)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for shot in shots:
            if only and shot not in only:
                continue
            for theme in THEMES:
                render_config(shot, f"win11-{theme}.css", ASSETS_DIR / f"{shot}-{theme}.png", work)
        if not only or HERO in only:
            hero_css = json.loads((HERE / f"{HERO}.json").read_text(encoding="utf-8"))["css"]
            render_config(HERO, hero_css, ASSETS_DIR / "hero.png", work)
        if only and "install" not in only:
            return

        package = subprocess.run(
            [str(ROOT / "scripts" / "package.sh"), str(work / "dist")], check=True, capture_output=True, text=True
        )
        plugin_zip = package.stdout.strip().splitlines()[-1]
        for theme in THEMES:
            flow_render(["-u", plugin_zip, "-i", "-s", f"win11-{theme}", "--hide-caret"], ASSETS_DIR / f"install-{theme}.png")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
