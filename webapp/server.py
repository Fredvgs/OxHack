"""The web server: two JSON endpoints and the pages in webapp/static/.

uv run --group web uvicorn webapp.server:app    then open http://localhost:8000
"""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from webapp import demo_state

app = FastAPI(title="Time to Harvest")


@app.get("/api/farm")
def farm():
    """Fields, yard, combines and map settings: what doesn't change during the season."""
    return demo_state.farm()


@app.get("/api/plan")
def plan():
    """The simulated season: combine positions, cards, forecasts and what really happened."""
    return demo_state.plan()


@app.get("/")
def home():
    return RedirectResponse("/panel.html")  # the home page comes later


# after the routes above, so /api/... is never looked up as a file
app.mount("/", StaticFiles(directory=demo_state.bridge.WEBAPP / "static"), name="static")
