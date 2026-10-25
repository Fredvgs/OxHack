"""The web app: two JSON endpoints and the pages in webapp/static/.

uv run --group web uvicorn webapp.server:app    then open http://localhost:8000
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from webapp import source

app = FastAPI(title="Time to Harvest")


@app.get("/api/farm")
def farm():
    """Fields, yard, combines, map and site settings."""
    return source.farm()


@app.get("/api/season")
def season():
    """Field status, combines and GPS tracks for every hour of the season."""
    return source.season()


# after the routes above; html=True serves index.html (the home page) at /
app.mount("/", StaticFiles(directory=source.WEBAPP / "static", html=True), name="static")
