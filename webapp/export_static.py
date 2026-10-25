"""Save the two API answers as files, so the site runs on a static host (Vercel) with no Python.

uv run --group web python -m webapp.export_static

Writes static/saved/farm.json and season.json; static/vercel.json sends /api/farm and
/api/season to them. Run it again and commit the files after changing the model, site.yaml or
demo.yaml. The browser moves the saved season's start to today (common.js), as the server does.
"""

import json
from pathlib import Path

from webapp import source

SAVED = source.WEBAPP / "static" / "saved"


def export(folder=SAVED):
    """Write farm.json and season.json into folder; returns their paths."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    answers = {"farm": {**source.farm(), "saved": True}, "season": source.season()}
    paths = []
    for name, answer in answers.items():
        path = folder / f"{name}.json"
        path.write_text(json.dumps(answer, separators=(",", ":")), encoding="utf-8")
        paths.append(path)
    return paths


if __name__ == "__main__":
    for path in export():
        print(f"{path}  {path.stat().st_size / 1e6:.1f} MB")
