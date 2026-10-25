"""The farmer site: two JSON endpoints and the pages in farmer/static/.

uv run --group web uvicorn farmer.server:app --port 8001    then open http://localhost:8001
(the demo control panel in webapp/ keeps port 8000; the two run side by side)
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from farmer import source

app = FastAPI(title="Time to Harvest: farmer site")


@app.get("/api/farm")
def farm():
    """Fields, yard, combines, map and site settings."""
    return source.farm()


@app.get("/api/season")
def season():
    """Field status, combines and GPS tracks for every hour of the season."""
    return source.season()


# one brand with the demo panel: its colours and fonts, read-only
# (/brand/css/tokens.css, /brand/fonts/)
app.mount("/brand", StaticFiles(directory=source.FARMER.parent / "webapp" / "static"), name="brand")
# after the routes above; html=True serves index.html at /
app.mount("/", StaticFiles(directory=source.FARMER / "static", html=True), name="static")
