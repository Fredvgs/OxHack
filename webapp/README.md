# webapp/: the website for farmers

The simulated season from `harvest/`, shown the way a farmer wants it: few words, no algorithm in
sight. A home page, then four dashboard pages, phone and desktop. It only reads from the rest of
the repo, never changes it.

```
uv run --group web uvicorn webapp.server:app    then open http://localhost:8000
uv run pytest webapp/tests -q                   tests (no internet, no server)
```

Restart the server after changing Python files, `site.yaml` or `demo.yaml` (`--reload` hung on
Windows); pages and scripts in `static/` only need a browser refresh. The map tiles and the
weather load from the internet; record a backup video.

## Pages

| Page | What it shows |
|---|---|
| **Home** (`index.html`) | The title, the slogan and **Log in**, which opens the dashboard on the Map (no account check), next to b-roll of the harvest: three aerial clips of machines at work, no people in shot, taking turns, each with its credit (`static/media/CREDITS.md`) |
| **Map** (`map.html`) | Satellite map, fields filled by status and outlined by crop (labels that would overlap hide until you zoom in), combines moving along their GPS tracks with a trail, a card per combine (readings, Send there / Back to yard / Call driver). Layer switches for live rain radar, rain forecast and wind, which zoom out to the area around the farm |
| **Today** (`today.html`) | One big answer (Cut now / Wait a little / Not today), the real weather now and for the next 12 h, every field (Ready / Soon / Wait / Done, % cut, grain moisture, which combine the plan sends and when, best time), every combine (what it's doing, next move), and two charts of the plan in force on one hour axis: what each field is worth hour by hour (with where each combine is sent) and where each combine goes (done so far, then the plan) |
| **Weather** (`weather.html`) | Forecast maps (rain, temperature, wind, clouds, radar) with a time slider and play, the next 7 days, and the next 48 h rated for harvesting (good / fair / poor) with the best window |
| **Control** (`control.html`) | Each combine: fuel, grain tank, speed, switches (engine, header, auto-steer, lights), Send / Yard / Call. Plan switches and Update plan, alert switches, fields with Skip and priority |

## Real and pretend

- **Real:** the weather. The browser fetches it live from [Open-Meteo](https://open-meteo.com)
  (forecast at the farm and on a 9 x 9 grid around it, for the maps) and
  [RainViewer](https://www.rainviewer.com/api.html) (radar, last 2 hours, up to zoom 7). No keys.
  When the demo replays a past week (`season_start` in `demo.yaml`), it shows that week's real
  weather instead: Open-Meteo's record of the Met Office 2 km model the demo's weather comes from,
  with the chance of rain from the demo's own forecast (the record has none). Radar only exists
  live, so its switches are hidden then.
- **From the model:** fields, combines, GPS tracks, field status and the plan come from the
  simulated season (`bridge.py` runs it, `demo_state.py` and `source.py` shape it).
- **Pretend:** machine readings (fuel, tank, speed) and every button and switch on the Control
  page. They respond (a switch stays switched, a toast says what happened) but don't change the plan.

On today's forecast, one forecast member plays the real weather, so a field can show "Wait" while
the real sky is dry. A past week plays the weather that really followed, the same record the
weather pages show.

## The demo's week

`season_start` in `demo.yaml` picks it. A date (e.g. `"2024-06-09"`) replays that week as
`replay.py` does: the ECMWF ensemble forecasts as issued then, and the weather that really
followed (`harvest/past_data.py`; the first start downloads them into `data/`, after that it runs
offline). Empty: today's forecast, `data/forecast.csv`, one member playing the real weather, as
`run.py` does. The tests always use today's forecast, so they never go online
(`tests/conftest.py`).

## The clock

The site follows real time through the season. On today's forecast, `forecast_start` in
`params.yaml` is hour 0. A past week is played on today's date: the clock shows the week's date at
today's time of day (at 08:20 it says Sun 09 Jun 08:20) and runs on from there
(`bridge.clock_start`). `?t=30` starts at hour 30 and `&speed=60` runs 60 times faster; both are
remembered while you browse. Click the red clock to go back to live. The weather always shows the
live hour.

## The demo farm

`data/demo_farm.geojson` has one MultiPolygon per field and a point for the yard. A field in the
model is a group of real fields around Elveden, Suffolk, traced from the Esri imagery the map shows
(one polygon each, listed in the order a combine works them; their ids, matching
`../data/fields.csv`, are in `"fields"`). Each feature has `"name"` (the field's name in
`params.yaml`, which links them), `"label"` (what the farmer sees: Field 1, Field 2, ...) and
`"crop"`. To redraw them, open the file at [geojson.io](https://geojson.io), move the corners onto
the hedgerows, keep the properties, and save it back. The model still uses `area_ha` and
`travel_hours` from `params.yaml`, not the drawn shapes.

## Files

| File | Job |
|---|---|
| `bridge.py` | **the only file that imports `harvest/`**. Runs the season, adds the forecast each plan saw and the share of forecasts in which each field can be cut |
| `tracks.py` | field outline → passes up and down; the season → where each combine is, 6 times an hour |
| `explain.py` | the combine cards and what each replan changed, in words, from the model's numbers |
| `demo_state.py` | the demo farm and its season in memory, as plain data |
| `source.py` | that season in farmer terms: each field Ready / Soon / Wait / Done, best time, moisture, what each combine does next |
| `server.py` | FastAPI: `GET /api/farm`, `GET /api/season`, and the pages in `static/` |
| `demo.yaml` | how the season is run (planner, the demo's week, map tiles, ...) |
| `site.yaml` | what the pages show (status rules, weather grid, map, pretend readings) |
| `data/demo_farm.geojson` | field outlines and the yard |
| `DESIGN.md` | **design rules for everything in `static/`: read before changing a page** |
| `static/css/tokens.css`, `app.css` | the colours and fonts; the layout and components |
| `static/js/common.js` | top bar, clock, alerts, toasts, pretend switches and readings |
| `static/js/weather-data.js` | fetching the real weather, colour scales, drawing forecast maps |
| `static/js/home.js`, `today.js`, `livemap.js`, `weather.js`, `control.js` | one per page |
| `static/js/plan-charts.js` | Today's two plan charts, plain SVG in the site's colours |
| `static/fonts/`, `static/media/` | the fonts (with their licences); the home page's footage (with `CREDITS.md`) |
