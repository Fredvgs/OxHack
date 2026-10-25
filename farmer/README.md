# farmer/: the website for farmers

The same simulated season as the demo control panel (`webapp/`), shown the way a farmer wants it:
in the demo panel's look (one brand: its colours and fonts are read from `webapp/static`), few
words, no algorithm in sight. Four pages, phone and desktop.

```
uv run --group web uvicorn farmer.server:app --port 8001    then open http://localhost:8001
uv run pytest farmer/tests -q                               tests (no internet, no server)
```

Runs next to the demo (port 8000). Restart the server after changing Python files or `site.yaml`.

## Pages

| Page | What it shows |
|---|---|
| **Today** (`index.html`) | One big answer (Cut now / Wait a little / Not today), the real weather now and for the next 12 h, every field (Ready / Soon / Wait / Done, % cut, grain moisture, best time), every combine (what it's doing, next move) |
| **Map** (`map.html`) | Satellite map, fields filled by status, combines moving along their GPS tracks with a trail, a card per combine (readings, Send there / Back to yard / Call driver). Layer switches for live rain radar, rain forecast and wind, which zoom out to the area around the farm |
| **Weather** (`weather.html`) | Forecast maps (rain, temperature, wind, clouds, radar) with a time slider and play, the next 7 days, and the next 48 h rated for harvesting (good / fair / poor) with the best window |
| **Control** (`control.html`) | Each combine: fuel, grain tank, speed, switches (engine, header, auto-steer, lights), Send / Yard / Call. Plan switches and Update plan, alert switches, fields with Skip and priority |

## Real and pretend

- **Real:** the weather. The browser fetches it live from [Open-Meteo](https://open-meteo.com)
  (forecast at the farm and on a 9 x 9 grid around it, for the maps) and
  [RainViewer](https://www.rainviewer.com/api.html) (radar, last 2 hours, up to zoom 7). No keys.
- **From the model:** fields, combines and GPS tracks come from the simulated season through
  `source.py`, which reads `webapp.demo_state`.
- **Pretend:** machine readings (fuel, tank, speed) and every button and switch on the control
  panel. They respond (a switch stays switched, a toast says what happened) but don't change the plan.

The fields' weather in the model is the Met Office forecast for the farm, but one forecast member
plays the real weather (see the demo's caveats), so a field can show "Wait" while the real sky is dry.

## The clock

The site follows real time through the season (`forecast_start` in `params.yaml` is hour 0).
`?t=30` starts at hour 30 and `&speed=60` runs 60 times faster; both are remembered while you
browse. Click the red clock to go back to live. The weather always shows the real now.

## Files

| File | Job |
|---|---|
| `source.py` | **the only file importing the rest of the repo** (`webapp.demo_state`, read-only): the season in farmer terms |
| `server.py` | FastAPI: `GET /api/farm`, `GET /api/season`, the pages in `static/`, and the demo's colours and fonts at `/brand/` (read-only from `webapp/static`) |
| `site.yaml` | every number the site uses (status rules, weather grid, map, pretend readings) |
| `DESIGN.md` | **the site's design rules (on top of `webapp/DESIGN.md`): status lamps, one sentence per page, tables. Read before changing a page** |
| `static/js/common.js` | top bar, clock, alerts, toasts, pretend switches and readings |
| `static/js/weather-data.js` | fetching the real weather, colour scales, drawing forecast maps |
| `static/js/today.js`, `livemap.js`, `weather.js`, `control.js` | one per page |
