// The time charts (Observable Plot): the decision map in the plan block, and rain, humidity and
// grain moisture in the weather block. Charts in one block share their margins, so the same hour
// sits at the same x on each; the scrubber (css .scrub-track) lines up with the decision map.

import { colours, dataFont } from "./theme.js";

// [left, right]: room for field names / axis numbers, and for direct labels at the right-hand end
const PLAN_MARGINS = [96, 64];
const WEATHER_MARGINS = [40, 104];

// dayLabels: false for the upper charts of a stack, which share the bottom chart's day labels
function frame(element, plan, height, extra, margins, dayLabels = true) {
  return {
    width: element.clientWidth,
    height,
    marginLeft: margins[0],
    marginRight: margins[1],
    marginBottom: dayLabels ? 24 : 6,
    style: { fontFamily: dataFont, fontSize: "11px", background: "transparent", color: colours.ink, overflow: "visible" },
    x: {
      domain: [0, plan.hours],
      ticks: plan.days.map((day) => day.hour),
      tickFormat: (hour) => (dayLabels ? (plan.days.find((day) => day.hour === hour)?.label ?? "") : ""),
      label: null,
    },
    ...extra,
  };
}

// consecutive night hours as [{x1, x2}] spans, shaded on every chart
function nights(plan) {
  const spans = [];
  plan.night.forEach((dark, hour) => {
    if (!dark) return;
    const last = spans.at(-1);
    if (last && last.x2 === hour) last.x2 = hour + 1;
    else spans.push({ x1: hour, x2: hour + 1 });
  });
  return Plot.rect(spans, { x1: "x1", x2: "x2", fill: colours.rule, fillOpacity: 0.35 });
}

const nowLine = (hour) => Plot.ruleX([hour], { stroke: colours.ink, strokeWidth: 1.5 });

// The colour of a cell or field: what cutting it in that hour is worth (or how likely it can be
// cut), in a few steps from pale to dark, like a printed table. null = can't be cut: no colour.
export function valueColour(plan, layer) {
  const steps = layerSteps(plan, layer);
  const shades = d3.quantize(d3.piecewise(d3.interpolateLab, [colours.paper, colours.straw, colours.soil]), steps.length + 2).slice(2);
  return (value) => (value > 0 ? shades[Math.max(0, d3.bisectRight(steps, value) - 1)] : null);
}

// lower edge of each colour step: £/ha rounded to 50s, or chance in 20% steps
export function layerSteps(plan, layer) {
  if (layer === "chance") return [0, 0.2, 0.4, 0.6, 0.8];
  const step = Math.ceil(plan.value_max_gbp_per_ha / 5 / 50) * 50;
  return d3.range(5).map((i) => i * step);
}

// value (or chance) of one field in one hour, as one plan saw it
export const layerValue = (p, layer, field, column) => (layer === "chance" ? p.cut_chance : p.value_gbp_per_ha)[field][column];

// What each field is worth if cut in each hour, and where each combine goes.
// Before now (pale): what each plan believed for the hours it was followed. From now: the plan in
// force. Solid lines: where the combines really were. Dashed: where the plan sends them.
export function drawDecisionMap(element, farm, plan, hour, planIndex, layer) {
  const nFields = farm.fields.length;
  const colour = valueColour(plan, layer);
  const cells = [];
  plan.plans.slice(0, planIndex + 1).forEach((p, k) => {
    const end = k < planIndex ? plan.plans[k + 1].hour : p.hour + p.value_gbp_per_ha[0].length;
    for (let field = 0; field < nFields; field++) {
      for (let h = p.hour; h < Math.min(end, plan.hours); h++) {
        const standing = plan.standing_ha[field][Math.min(h, hour)]; // the future can't uncut a field
        const value = layerValue(p, layer, field, h - p.hour);
        if (standing > 0 && value > 0) cells.push({ field, h, value, past: h < hour, made: p.hour });
      }
    }
  });

  const nMachines = farm.machines.length;
  const offset = (m) => 0.25 + (0.5 * m) / Math.max(1, nMachines - 1); // each combine its own lane in a row
  const done = [];
  const planned = [];
  const now = [];
  const planNow = plan.plans[planIndex];
  farm.machines.forEach((machine, m) => {
    for (let h = 0; h < hour; h++) {
      const [activity, place] = [plan.activity[m][h], plan.place[m][h]];
      if (activity === "cutting" || activity === "waiting") done.push({ m, x: h, y: place + offset(m) }, { m, x: h + 1, y: place + offset(m) });
      else if (activity === "yard" || place === nFields) done.push({ m, x: h, y: NaN }); // gap: off the map
    }
    let target = plan.place[m][Math.min(hour, plan.hours - 1)];
    if (target < nFields) now.push({ x: hour, y: target + offset(m), letter: machine.letter });
    planNow.schedule[m].forEach((next, j) => {
      const h = planNow.hour + j;
      if (next !== plan.wait) target = next; // wait = stay where you are
      if (h < hour) return;
      if (target < nFields) planned.push({ m, x: h, y: target + offset(m) }, { m, x: h + 1, y: target + offset(m) });
      else planned.push({ m, x: h, y: NaN });
    });
  });

  const format = (value) => (layer === "chance" ? `${Math.round(100 * value)}% of forecasts can cut` : `£${value.toLocaleString("en-GB")}/ha`);
  const chart = Plot.plot(
    frame(element, plan, 30 + 28 * nFields, {
      y: { domain: [nFields, 0], ticks: farm.fields.map((_, f) => f + 0.5), tickFormat: (y) => farm.fields[Math.floor(y)].label, tickSize: 0, label: null },
      marks: [
        // midnights instead of night shading, which would muddy the colours
        Plot.ruleX(plan.days, { x: "hour", stroke: colours.rule, strokeWidth: 0.75 }),
        Plot.rect(cells, {
          x1: "h",
          x2: (c) => c.h + 1,
          y1: "field",
          y2: (c) => c.field + 1,
          fill: (c) => colour(c.value),
          fillOpacity: (c) => (c.past ? 0.5 : 1),
          shapeRendering: "crispEdges", // no hairline seams between neighbouring hours
          title: (c) => `${farm.fields[c.field].label}, ${plan.labels[c.h]}\n${format(c.value)}\nplan made ${plan.labels[c.made]}`,
          tip: true,
        }),
        Plot.ruleY(d3.range(nFields + 1), { stroke: colours.rule, strokeWidth: 0.75 }),
        // routes: a pale halo under each line keeps it readable on the darkest cells
        Plot.line([...done, { x: NaN, y: NaN }, ...planned], { x: "x", y: "y", z: "m", stroke: colours.paper, strokeWidth: 4.5 }),
        Plot.line(done, { x: "x", y: "y", z: "m", stroke: colours.ink, strokeWidth: 2 }),
        Plot.line(planned, { x: "x", y: "y", z: "m", stroke: colours.ink, strokeWidth: 1.75, strokeDasharray: "4 2" }),
        Plot.text(now, { x: "x", y: "y", text: "letter", fill: colours.ink, stroke: colours.paper, strokeWidth: 3, fontWeight: 500, fontSize: 12 }),
        Plot.text(farm.fields, {
          x: plan.hours,
          y: (_, f) => f + 0.5,
          text: (field, f) => {
            const left = plan.standing_ha[f][hour];
            return left <= 0 ? "all cut" : `${Math.round(100 * (1 - left / field.area_ha))}% cut`;
          },
          textAnchor: "start",
          dx: 6,
          fill: colours.ink2,
        }),
        nowLine(hour),
      ],
    }, PLAN_MARGINS),
  );
  element.replaceChildren(chart);
}

// A forecast band (10th-90th percentile of members) from the plan in force, its middle dashed,
// and what really happened up to now as a solid line. bands: [low, middle, high] of [hour].
function bandMarks(bands, actual, planNow) {
  const [low, middle, high] = bands;
  const band = middle.map((mid, j) => ({ x: planNow.hour + j, low: low[j], mid, high: high[j] }));
  return {
    band,
    marks: [
      Plot.areaY(band, { x: "x", y1: "low", y2: "high", fill: colours.ink, fillOpacity: 0.12 }),
      Plot.lineY(band, { x: "x", y: "mid", stroke: colours.ink2, strokeDasharray: "3 3" }),
      Plot.lineY(actual, { x: "x", y: "y", stroke: colours.ink, strokeWidth: 1.5 }),
    ],
  };
}

const rightLabel = (point, text, fill, extra = {}) =>
  Plot.text([point], { x: "x", y: "y", text: () => text, textAnchor: "start", dx: 6, fill, ...extra });

const forecastLabel = (plan) => `forecast ${plan.band_percentiles[0]}–${plan.band_percentiles.at(-1)}%`;

// Air humidity in one field: it drives how fast the grain dries (Henderson equilibrium moisture).
export function drawHumidity(element, farm, plan, field, hour, planNow, height) {
  const actual = plan.true_humidity_pct[field].slice(0, hour + 1).map((y, x) => ({ x, y }));
  const { band, marks } = bandMarks(planNow.humidity_pct.map((b) => b[field]), actual, planNow);
  const lowest = Math.min(...band.map((d) => d.low), ...actual.map((d) => d.y));
  const end = band.at(-1);
  const chart = Plot.plot(
    frame(element, plan, height, {
      y: { domain: [Math.floor(lowest / 10) * 10, 100], ticks: 3, label: "air humidity %", labelAnchor: "top" },
      marks: [nights(plan), ...marks, rightLabel({ x: end.x, y: end.mid }, forecastLabel(plan), colours.ink2), nowLine(hour)],
    }, WEATHER_MARGINS, false),
  );
  element.replaceChildren(chart);
}

// Grain moisture in one field: the forecast band from the latest reading, and what really happened.
export function drawMoisture(element, farm, plan, field, hour, planNow, height) {
  const actual = plan.true_moisture_pct[field].slice(0, hour + 1).map((y, x) => ({ x, y }));
  const { band, marks } = bandMarks(planNow.moisture_pct.map((b) => b[field]), actual, planNow);
  const readings = actual.filter((point) => point.x % plan.limits.sensor_every_hours === 0);
  const tooWet = plan.limits.too_wet_pct;
  const freeDrying = plan.limits.free_drying_pct[field]; // per crop, so one per field
  const values = [...band.flatMap((d) => [d.low, d.high]), ...actual.map((d) => d.y), tooWet, freeDrying];
  const end = band.at(-1);

  const chart = Plot.plot(
    frame(element, plan, height, {
      y: { domain: [Math.floor(Math.min(...values)) - 1, Math.ceil(Math.max(...values)) + 1], ticks: 4, label: "grain moisture %, from the weather above", labelAnchor: "top" },
      marks: [
        nights(plan),
        Plot.ruleY([tooWet], { stroke: colours.alarm }),
        Plot.ruleY([freeDrying], { stroke: colours.ink2, strokeDasharray: "1 3" }),
        ...marks,
        Plot.dot(readings, { x: "x", y: "y", r: 2.5, fill: colours.ink }),
        rightLabel({ x: end.x, y: end.mid }, forecastLabel(plan), colours.ink2),
        rightLabel({ x: plan.hours, y: tooWet }, `too wet >${tooWet}%`, colours.alarm, { dy: -6 }),
        rightLabel({ x: plan.hours, y: freeDrying }, `drying >${freeDrying}%`, colours.ink2, { dy: 6 }),
        Plot.text(hour >= 6 ? actual.slice(-1) : [], { x: "x", y: "y", text: () => "actual", textAnchor: "end", dx: -6, dy: -8, fill: colours.ink }),
        nowLine(hour),
      ],
    }, WEATHER_MARGINS),
  );
  element.replaceChildren(chart);
}

// Chance of rain in one field from now (share of forecast members), and the hours it really rained.
export function drawRain(element, farm, plan, field, hour, planNow, height) {
  const future = planNow.rain_chance[field]
    .map((chance, j) => ({ x1: planNow.hour + j, x2: planNow.hour + j + 1, pct: 100 * chance }))
    .filter((bar) => bar.x1 >= hour);
  const rained = plan.true_rain_mm[field]
    .map((mm, h) => ({ x1: h, x2: h + 1, mm }))
    .filter((bar) => bar.x1 < hour && bar.mm > plan.limits.rain_mm);

  const chart = Plot.plot(
    frame(element, plan, height, {
      y: { domain: [0, 100], ticks: [0, 50, 100], label: `chance of rain > ${plan.limits.rain_mm} mm/h, % of forecasts`, labelAnchor: "top" },
      marks: [
        nights(plan),
        Plot.rect(rained, { x1: "x1", x2: "x2", y1: 0, y2: 100, fill: colours.rain, fillOpacity: 0.3 }),
        Plot.rectY(future, { x1: "x1", x2: "x2", y: "pct", fill: colours.rain, fillOpacity: 0.85 }),
        Plot.ruleY([plan.limits.rain_chance_pct], { stroke: colours.rain, strokeDasharray: "2 3" }),
        rightLabel({ x: plan.hours, y: plan.limits.rain_chance_pct }, "rain likely", colours.rain),
        Plot.text([{ x: 0, y: 100 }], { x: "x", y: "y", text: () => (rained.length ? "pale: it rained" : ""), textAnchor: "start", dy: 10, dx: 4, fill: colours.rain }),
        Plot.ruleY([0], { stroke: colours.rule }),
        nowLine(hour),
      ],
    }, WEATHER_MARGINS, false),
  );
  element.replaceChildren(chart);
}
