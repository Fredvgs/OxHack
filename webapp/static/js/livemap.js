// Live map: satellite, fields shaded by status, the ground cut so far, combines moving along their
// GPS tracks, Play to run through the next hours, and real weather layers (radar, rain forecast,
// wind) that zoom out to show the area around the farm.

import { $, ACTIVITY, crop, everySecond, lamp, load, makeClock, showAlerts, telemetry, toast, topbar } from "./common.js";
import { gridBounds, gridForecast, gridImage, legend, nowIndex, radarFrames, windArrows } from "./weather-data.js";

const { farm, season } = await load();
// radar is live only: a demo replaying a past week has none to show
if (farm.week) $("#layer-radar").closest("label").style.display = "none";
const live = makeClock(farm);
// Play runs this page ahead on its own clock (the other pages stay where they are)
let play = null; // {from, to, wall}: hours, and performance.now() when it started
const clock = () => (play ? Math.min(play.from + (performance.now() - play.wall) / 1000 / farm.site.map_play_seconds_per_hour, play.to) : live());
clock.live = live.live;
topbar(farm, "map.html", clock);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();

const map = L.map("map", { zoomSnap: 0.25, zoomControl: false });
L.control.zoom({ position: "bottomright" }).addTo(map);
L.tileLayer(farm.map.tiles_url, { attribution: farm.map.attribution, maxZoom: 19 }).addTo(map);
const FARM_VIEW = { paddingTopLeft: [340, 30], paddingBottomRight: [270, 70] }; // clear of the panels

// outline colour = crop, fill = status. Each field is a group of real fields: its label sits in
// the middle of the group, not on its biggest field, so the labels overlap less.
const fields = farm.fields.map((field) => L.polygon(field.outline, { color: css(field.crop), weight: 2, fillOpacity: 0.4 }).addTo(map));
const labels = farm.fields.map((field) =>
  L.tooltip({ permanent: true, direction: "center", className: "field-tag" }).setLatLng(field.centre).setContent(field.label).addTo(map),
);
// a label that would sit on another is hidden until you zoom in; the bigger group keeps its label
const labelOrder = farm.fields.map((_, f) => f).sort((a, b) => farm.fields[b].area_ha - farm.fields[a].area_ha);
function declutter() {
  const kept = [];
  labelOrder.forEach((f) => {
    const element = labels[f].getElement();
    if (!element) return;
    element.style.visibility = "";
    const box = element.getBoundingClientRect();
    const overlaps = kept.some((k) => box.left < k.right && box.right > k.left && box.top < k.bottom && box.bottom > k.top);
    if (overlaps) element.style.visibility = "hidden";
    else kept.push(box);
  });
}
map.on("zoomend", declutter);
$("#crop-key").innerHTML = [...new Set(farm.fields.map((field) => field.crop))]
  .map((name) => `<span>${crop(name)}</span>`)
  .join("");
const farmBounds = L.featureGroup(fields).getBounds();
map.fitBounds(farmBounds, FARM_VIEW);

// ---------- the cut ground: each field's passes, one pass wide, as far as it is cut ----------
// The combines' tracks follow the same passes to the same point (webapp/tracks.py), so the cut
// ground always ends under the combine.
const EARTH_M = 40_075_016.686; // round the equator: the width of the zoom 0 map tile
const cutGround = farm.fields.map(() => L.polyline([], { color: css("paper"), opacity: 0.6, interactive: false }).addTo(map));
const cutShown = farm.fields.map(() => -Infinity); // metres each line shows, so others aren't redrawn

// the passes driven up to `metres` along a field's path: [parcel][point][lat, lng], one line per
// parcel, leaving out the way along the field edges from one parcel to the next
function cutPasses(field, metres) {
  const { path, path_m: along, pass_ranges: ranges } = field;
  return ranges
    .map(([start, end]) => {
      let i = start;
      while (i < end && along[i] <= metres) i++;
      const line = path.slice(start, i);
      if (i > start && i < end) {
        const share = (metres - along[i - 1]) / (along[i] - along[i - 1]);
        line.push(path[i - 1].map((x, d) => x + (path[i][d] - x) * share));
      }
      return line;
    })
    .filter((line) => line.length > 1);
}

function drawCut(time) {
  const hour = Math.floor(time);
  farm.fields.forEach((field, f) => {
    const [before, after] = season.cut_share[f].slice(hour, hour + 2);
    const metres = (before + (after - before) * (time - hour)) * field.path_m.at(-1);
    if (Math.abs(metres - cutShown[f]) < 1) return;
    cutShown[f] = metres;
    cutGround[f].setLatLngs(cutPasses(field, metres));
  });
}

// one pass wide at every zoom: a pixel is EARTH_M x cos(latitude) / (256 x 2^zoom) metres
function passWidth() {
  const metresPerPixel = (EARTH_M * Math.cos((farm.centre[0] * Math.PI) / 180)) / 2 ** (map.getZoom() + 8);
  const weight = Math.max(1, farm.map.pass_width_m / metresPerPixel);
  cutGround.forEach((line) => line.setStyle({ weight }));
}
passWidth();
map.on("zoomend", passWidth);

// the yard label and the combines sit above the field labels (Leaflet's tooltip pane is 650)
map.createPane("top").style.zIndex = 700;
L.marker(farm.yard, { pane: "top", interactive: false, icon: L.divIcon({ className: "yard-tag", html: "Yard", iconSize: [40, 18], iconAnchor: [46, 9] }) }).addTo(map);

const trails = farm.machines.map(() => L.polyline([], { color: css("straw"), weight: 3, opacity: 0.95 }).addTo(map));
const markers = farm.machines.map((machine, m) =>
  L.marker(farm.yard, {
    pane: "top",
    icon: L.divIcon({ className: "", html: `<div class="marker" id="marker-${m}">${machine.letter}</div>`, iconSize: [26, 26] }),
  })
    .bindPopup(() => combinePopup(m))
    .addTo(map),
);

// ---------- combines: GPS positions, smooth between the positions sent 6 times an hour ----------
function position(m, frame) {
  const track = season.tracks[m];
  const i = Math.min(Math.floor(frame), track.length - 2);
  const share = frame - i;
  return [track[i][0] + (track[i + 1][0] - track[i][0]) * share, track[i][1] + (track[i + 1][1] - track[i][1]) * share];
}

function moveCombines() {
  const time = clock();
  if (play && time >= play.to) stopPlay();
  drawCut(time);
  const frame = time * farm.steps_per_hour;
  farm.machines.forEach((_, m) => {
    const now = position(m, frame);
    markers[m].setLatLng(now);
    trails[m].setLatLngs($("#layer-trails").checked ? roadTrail(m, frame, now) : []);
  });
  requestAnimationFrame(moveCombines);
}

// the way a combine came on the road in the last trail_minutes: [stretch][point]. Its cutting
// shows as cut ground instead, which a trail drawn over the passes would hide.
function roadTrail(m, frame, now) {
  const steps = farm.steps_per_hour;
  const onRoad = (i) => season.activity[m][Math.floor(i / steps)] === "driving";
  const stretches = [[]];
  for (let i = Math.max(0, Math.ceil(frame - (farm.site.trail_minutes / 60) * steps)); i <= frame; i++) {
    if (onRoad(i) || (i > 0 && onRoad(i - 1))) stretches.at(-1).push(season.tracks[m][i]); // to where it arrived
    else if (stretches.at(-1).length) stretches.push([]);
  }
  if (onRoad(frame)) stretches.at(-1).push(now);
  return stretches.filter((stretch) => stretch.length > 1);
}
requestAnimationFrame(moveCombines);

function combinePopup(m) {
  const hour = Math.floor(clock());
  const machine = farm.machines[m];
  const reading = telemetry(farm, season, m, clock());
  const activity = season.activity[m][hour];
  return `<h2>${machine.label}</h2>
    <div class="muted">${activity === "yard" ? ACTIVITY.yard : season.doing[hour][m]}</div>
    <div class="readings">
      <div><b>${Math.round(reading.fuel_pct)}%</b><span>fuel</span></div>
      <div><b>${Math.round(reading.tank_pct)}%</b><span>tank</span></div>
      <div><b>${reading.speed_kmh.toFixed(1)}</b><span>km/h</span></div>
    </div>
    <div class="popup-actions">
      <select class="button small" id="send-${m}" aria-label="Field">${farm.fields.map((f, i) => `<option value="${i}">${f.label}</option>`).join("")}</select>
      <button class="button small" data-send="${m}">Send there</button>
      <button class="button small secondary" data-toast="${machine.label} heading to the yard.">Back to yard</button>
      <button class="button small secondary" data-toast="Calling the driver of ${machine.label}…" style="grid-column:1/-1">Call driver</button>
    </div>`;
}
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-send]");
  if (!button) return;
  const m = Number(button.dataset.send);
  toast(`${farm.machines[m].label} sent to ${farm.fields[$(`#send-${m}`).value].label}.`);
  map.closePopup();
});

// ---------- once an hour: field shading, marker borders, the combines list ----------
function showHour(hour) {
  const shade = $("#layer-status").checked;
  farm.fields.forEach((field, f) => {
    const status = season.status[f][hour];
    fields[f].setStyle({ fillColor: css(status), fillOpacity: shade && status !== "done" ? 0.4 : 0 });
    labels[f].setContent(`${field.label} · ${lamp(status)}`);
  });
  declutter(); // the words changed, so the labels' widths did too
  farm.machines.forEach((_, m) => {
    const element = document.getElementById(`marker-${m}`);
    if (element) element.className = `marker ${season.activity[m][hour]}`;
  });
  $("#combine-list").innerHTML = farm.machines
    .map((machine, m) => {
      const activity = season.activity[m][hour];
      return `<div class="combine-row" data-combine="${m}"><span class="marker ${activity}">${machine.letter}</span>
        <div>${activity === "yard" ? ACTIVITY.yard : season.doing[hour][m]}<small>next: ${season.next[hour][m]}</small></div></div>`;
    })
    .join("");
  showAlerts(farm, season, hour);
  if (play) $("#play-note").textContent = `+${hour - Math.floor(play.from)} h`;
}
everySecond(clock, season, { hour: showHour });

// ---------- Play: the next hours of the season in under a minute, then back to live ----------
const playHours = farm.site.map_play_hours;
const playIdle = `${playHours} h in ${Math.round(playHours * farm.site.map_play_seconds_per_hour)} s`;
$("#play-label").textContent = `Next ${playHours} h`;
$("#play-note").textContent = playIdle;

function startPlay() {
  const from = live();
  play = { from, to: Math.min(from + playHours, farm.hours - 0.001), wall: performance.now() };
  $("#play").textContent = "Stop";
  $("#play-note").textContent = "+0 h";
  $("#clock-box .mode").textContent = "PLAY";
}

function stopPlay() {
  play = null;
  $("#play").textContent = "Play";
  $("#clock-box .mode").textContent = live.live ? "LIVE" : "REPLAY";
  $("#play-note").textContent = playIdle;
}
$("#play").addEventListener("click", () => (play ? stopPlay() : startPlay()));

$("#combine-list").addEventListener("click", (event) => {
  const row = event.target.closest("[data-combine]");
  if (!row) return;
  const m = Number(row.dataset.combine);
  map.flyTo(markers[m].getLatLng(), 17, { duration: 0.8 });
  setTimeout(() => markers[m].openPopup(), 850);
});

// links from Today: map.html#field-3 or #combine-1
const [kind, index] = location.hash.slice(1).split("-");
if (kind === "field" && fields[index]) map.fitBounds(fields[index].getBounds(), { ...FARM_VIEW, maxZoom: 17 });
if (kind === "combine" && markers[index]) setTimeout(() => $(`[data-combine="${index}"]`)?.click(), 300);

// ---------- real weather layers ----------
let grid = null;
let radar = null; // {layers, timer}
const weatherLayers = { rain: null, wind: null };
const getGrid = async () => (grid ??= await gridForecast(farm));

async function showRadar(on) {
  if (radar) {
    clearInterval(radar.timer);
    radar.layers.forEach((layer) => layer.remove());
    radar = null;
  }
  if (!on) return;
  const frames = await radarFrames();
  const options = { maxNativeZoom: farm.site.radar_max_zoom, maxZoom: 19, opacity: 0, zIndex: 400 };
  const layers = frames.map((frame) => L.tileLayer(frame.url, options).addTo(map));
  let k = 0;
  const timer = setInterval(() => {
    layers.forEach((layer, i) => layer.setOpacity(i === k ? 0.75 : 0));
    $("#weather-note").textContent = `radar ${frames[k].time.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
    k = (k + 1) % layers.length;
  }, 700);
  radar = { layers, timer };
}

async function showRain(on) {
  weatherLayers.rain?.remove();
  weatherLayers.rain = null;
  if (!on) return;
  const g = await getGrid();
  weatherLayers.rain = L.imageOverlay(gridImage(g, "precipitation", nowIndex(g.times)), gridBounds(g), { opacity: 0.85 }).addTo(map);
}

async function showWind(on) {
  weatherLayers.wind?.remove();
  weatherLayers.wind = null;
  if (!on) return;
  const g = await getGrid();
  weatherLayers.wind = L.layerGroup(windArrows(g, nowIndex(g.times))).addTo(map);
}

// weather is about the area around the farm: zoom out while a weather layer is on
async function weatherView() {
  const any = ["#layer-radar", "#layer-rain", "#layer-wind"].some((id) => $(id).checked);
  if (any) map.flyToBounds(gridBounds(await getGrid()), { duration: 0.8 });
  else map.flyToBounds(farmBounds, { ...FARM_VIEW, duration: 0.8 });
  $("#layer-legend").innerHTML = $("#layer-rain").checked ? legend("precipitation") : "";
  if (!$("#layer-radar").checked) $("#weather-note").textContent = any ? "forecast for this hour" : "";
}

const offline = () => toast("Weather unavailable right now.");
$("#layer-status").addEventListener("change", () => showHour(Math.floor(clock())));
$("#layer-radar").addEventListener("change", (e) => showRadar(e.target.checked).then(weatherView).catch(offline));
$("#layer-rain").addEventListener("change", (e) => showRain(e.target.checked).then(weatherView).catch(offline));
$("#layer-wind").addEventListener("change", (e) => showWind(e.target.checked).then(weatherView).catch(offline));
