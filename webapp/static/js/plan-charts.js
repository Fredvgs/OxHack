// The Today page's two charts, plain SVG in the site's colours (webapp/DESIGN.md), on one hour
// axis for the whole season: the weather each field gets each hour (rain, grain moisture or
// temperature, one tab at a time), with where the plan sends each combine; and each combine's
// hours, what it did so far and what the plan has it do next.

const SVG = "http://www.w3.org/2000/svg";
const LEFT = 150; // px for the row names
const RIGHT = 120; // px for the labels at the right-hand end
const AXIS = 22; // px under the rows for the day labels

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim();

function add(parent, tag, attrs, text) {
  const node = document.createElementNS(SVG, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  if (text !== undefined) node.textContent = text;
  parent.append(node);
  return node;
}

// the plan made at or before this hour
const planInForce = (season, hour) => season.plans.filter((p) => p.hour <= hour).at(-1);

// ---------- the weather tabs: what colours each field-hour ----------
function rgb(hex) {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function mix(a, b, t) {
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")})`;
}

// Each tab: the plan's number for field f at plan column c, steps(f) the lower edge of each colour
// step for that field, a colour and a key label per step. A value under the first step is blank.
export function weatherLayers(farm, season) {
  const [paper, straw, soil, rain, alarm] = ["paper", "straw", "soil", "rain", "alarm"].map((name) => rgb(css(name)));
  // grain moisture: drying is free up to a limit that depends on the crop (one per field, or one
  // number for all), and no crop can be cut above too_wet_pct
  const { free_drying_pct: free, too_wet_pct: wet } = season.limits;
  const freeOf = (f) => (Array.isArray(free) ? free[f] : free);
  const cropsAt = {}; // limit -> crops with it, for the key: "15% wheat, barley · 9% OSR"
  farm.fields.forEach((field, f) => {
    const name = field.crop === "osr" ? "OSR" : field.crop;
    cropsAt[freeOf(f)] = [...new Set([...(cropsAt[freeOf(f)] ?? []), name])];
  });
  const freeText = Object.entries(cropsAt)
    .sort(([a], [b]) => b - a)
    .map(([limit, crops]) => `${Number(limit)}% ${crops.join(", ")}`)
    .join(" · ");
  const rainSteps = farm.site.chart_rain_steps_pct; // e.g. [20, 40, 60, 80]
  const tempSteps = farm.site.chart_temp_steps_c; // e.g. [5, 10, 15, 20, 25]
  const nTemp = tempSteps.length + 1; // one step below the first edge too
  return {
    rain: {
      word: "Rain",
      value: (p, f, c) => p.rain_pct[f][c],
      steps: () => rainSteps,
      colours: rainSteps.map((_, i) => mix(paper, rain, (i + 1) / rainSteps.length)),
      labels: rainSteps.map((low) => `${low}%+`),
      blank: `under ${rainSteps[0]}% chance of rain`,
    },
    moisture: {
      word: "Moisture",
      value: (p, f, c) => p.moisture_pct[f][c],
      // heavy drying from halfway between the field's free-drying limit and too wet
      steps: (f) => [-Infinity, freeOf(f), (freeOf(f) + wet) / 2, wet],
      colours: [mix(paper, straw, 0.45), mix(straw, soil, 0.15), mix(straw, soil, 0.85), mix(alarm, paper, 0.1)],
      labels: [`no drying charge (under ${freeText})`, "drying charged", "heavy drying", `over ${wet}%, too wet to cut`],
      blank: "",
    },
    temperature: {
      word: "Temperature",
      value: (p, f, c) => p.temp_c[f][c],
      steps: () => [-Infinity, ...tempSteps],
      // cold to warm: rain blue, through paper, to brick
      colours: [...Array(nTemp).keys()].map((i) => {
        const t = i / (nTemp - 1);
        return t < 0.5 ? mix(rain, paper, t * 2 * 0.85) : mix(paper, alarm, (t - 0.5) * 2 * 0.85);
      }),
      labels: [`under ${tempSteps[0]}°C`, ...tempSteps.map((low, i) => (i + 1 < tempSteps.length ? `${low}-${tempSteps[i + 1]}°C` : `${low}°C+`))],
      blank: "",
    },
  };
}

function stepIndex(steps, value) {
  if (value === undefined || value === null || value < steps[0]) return -1; // left blank
  let i = 0;
  while (i < steps.length - 1 && value >= steps[i + 1]) i++;
  return i;
}

// ---------- the shared frame: night shading, midnight ticks, the now line ----------
function frame(element, season, rows, rowHeight) {
  element.innerHTML = "";
  const nHours = season.labels.length - 1;
  const width = Math.max(element.clientWidth, 760);
  const height = rows * rowHeight + AXIS;
  const svg = add(element, "svg", { width, height, viewBox: `0 0 ${width} ${height}`, class: "chart" });
  const x = (hour) => LEFT + (hour / nHours) * (width - LEFT - RIGHT);
  season.night.forEach((dark, h) => {
    if (dark) add(svg, "rect", { x: x(h), y: 0, width: x(h + 1) - x(h) + 0.5, height: rows * rowHeight, fill: css("rule"), opacity: 0.35 });
  });
  season.days.forEach((day) => {
    add(svg, "line", { x1: x(day.hour), x2: x(day.hour), y1: rows * rowHeight, y2: rows * rowHeight + 5, stroke: css("ink-2") });
    add(svg, "text", { x: x(day.hour) + 3, y: rows * rowHeight + 16, class: "tick" }, day.label);
  });
  return { svg, x, nHours, width };
}

function nowLine(svg, x, hour, bottom) {
  add(svg, "line", { x1: x(hour), x2: x(hour), y1: 0, y2: bottom, stroke: css("ink"), "stroke-width": 1.5 });
}

// runs of equal keys along an array: [{start, end, key}]
function runs(keys) {
  const out = [];
  keys.forEach((key, h) => {
    const last = out.at(-1);
    if (last && last.key === key) last.end = h + 1;
    else out.push({ start: h, end: h + 1, key });
  });
  return out;
}

// The weather each field gets each hour, coloured by one tab (layer, from weatherLayers). Before
// now (pale): as the plan of that hour forecast it. From now: the plan in force. Ink boxes: where
// it sends each combine (its letter at the start). Ink bar along the bottom of a row: hours a
// combine really cut there.
export function drawWeather(element, farm, season, hour, layer) {
  const rowHeight = 18;
  const nFields = farm.fields.length;
  const { svg, x, nHours } = frame(element, season, nFields, rowHeight);
  const now = planInForce(season, hour);

  farm.fields.forEach((field, f) => {
    const top = f * rowHeight;
    const shade = [...Array(nHours).keys()].map((h) => {
      const p = h < hour ? planInForce(season, h) : now;
      const value = layer.value(p, f, h - p.hour); // undefined past the end of the plan
      return `${stepIndex(layer.steps(f), value)}|${h < hour ? "past" : "plan"}`;
    });
    runs(shade).forEach(({ start, end, key }) => {
      const [i, when] = key.split("|");
      if (Number(i) < 0) return;
      add(svg, "rect", { x: x(start), y: top + 1, width: x(end) - x(start) + 0.3, height: rowHeight - 2, fill: layer.colours[Number(i)], opacity: when === "past" ? 0.4 : 1 });
    });
    add(svg, "line", { x1: LEFT, x2: x(nHours), y1: top + rowHeight, y2: top + rowHeight, stroke: css("rule") });
    add(svg, "text", { x: LEFT - 8, y: top + 13, class: "row-name", "text-anchor": "end" }, field.label);
    const planned = season.cut_pct[f][hour] >= 100 ? "done" : (season.planned[f][hour] ?? "not this week");
    add(svg, "text", { x: x(nHours) + 8, y: top + 13, class: "row-end" }, planned);
  });

  // where the combines really cut, up to now
  farm.machines.forEach((_, m) => {
    const cutting = [...Array(hour).keys()].map((h) => (season.activity[m][h] === "cutting" ? season.place[m][h] : -1));
    runs(cutting).forEach(({ start, end, key }) => {
      if (key < 0) return;
      add(svg, "rect", { x: x(start), y: key * rowHeight + rowHeight - 5, width: x(end) - x(start), height: 3, fill: css("ink") });
    });
  });

  // where the plan in force sends each combine from now on
  const column = hour - now.hour;
  farm.machines.forEach((machine, m) => {
    const ahead = now.schedule[m].slice(column).map((target) => (target >= 0 && target < nFields ? target : -1));
    runs(ahead).forEach(({ start, end, key }) => {
      if (key < 0) return;
      const [left, right] = [x(hour + start), x(Math.min(hour + end, nHours))];
      add(svg, "rect", { x: left, y: key * rowHeight + 1.5, width: right - left, height: rowHeight - 3, fill: "none", stroke: css("ink"), "stroke-width": 1.5 });
      add(svg, "text", { x: left + 3, y: key * rowHeight + 13, class: "letter" }, machine.letter);
    });
  });
  nowLine(svg, x, hour, nFields * rowHeight);
}

// Each combine's hours: cutting, on the road, waiting, at the yard. Solid up to now (what it did),
// dashed from now (what the plan in force has it do). The field's name sits in each stretch.
export function drawRoutes(element, farm, season, hour) {
  const rowHeight = 30;
  const nFields = farm.fields.length;
  const { svg, x, nHours } = frame(element, season, farm.machines.length, rowHeight);
  const now = planInForce(season, hour);
  const fill = { cutting: css("straw"), driving: css("soil"), waiting: css("paper"), yard: "none" };

  farm.machines.forEach((machine, m) => {
    const top = m * rowHeight;
    // [hour] "kind|field|done or plan"
    const hours = [];
    let field = season.place[m][Math.max(hour - 1, 0)];
    for (let h = 0; h < nHours; h++) {
      if (h < hour) {
        hours.push(`${season.activity[m][h]}|${season.place[m][h]}|done`);
        continue;
      }
      const column = h - now.hour;
      if (column >= now.schedule[m].length) break; // the plan ends with the forecast
      const target = now.schedule[m][column];
      if (target !== season.wait) field = target;
      const kind = field === nFields ? "yard" : target !== season.wait && now.value_gbp_per_ha[field][column] > 0 ? "cutting" : "waiting";
      hours.push(`${kind}|${field}|plan`);
    }
    runs(hours).forEach(({ start, end, key }) => {
      const [kind, f, when] = key.split("|");
      if (kind === "yard") return;
      const [left, right] = [x(start), x(end)];
      add(svg, "rect", {
        x: left, y: top + 3, width: Math.max(right - left - 0.5, 0.5), height: rowHeight - 6, fill: fill[kind],
        opacity: when === "plan" ? 0.55 : 1, stroke: kind === "waiting" || when === "plan" ? css("ink-2") : "none",
        "stroke-dasharray": when === "plan" ? "3 2" : "none",
      });
      const name = Number(f) < nFields ? farm.fields[Number(f)].label : "";
      if (kind !== "driving" && name && right - left > name.length * 6.6 + 8) {
        add(svg, "text", { x: left + 4, y: top + rowHeight / 2 + 4, class: "stretch" }, name);
      }
    });
    add(svg, "line", { x1: LEFT, x2: x(nHours), y1: top + rowHeight, y2: top + rowHeight, stroke: css("rule") });
    add(svg, "text", { x: LEFT - 8, y: top + rowHeight / 2 + 4, class: "row-name", "text-anchor": "end" }, machine.label);
    const next = season.next[hour][m]; // "Eriswell, Mon 12:00" or "No change planned."
    add(svg, "text", { x: x(nHours) + 8, y: top + rowHeight / 2 + 4, class: "row-end" }, next.includes(",") ? `next ${next.split(",")[0]}` : "");
  });
  nowLine(svg, x, hour, farm.machines.length * rowHeight);
}
