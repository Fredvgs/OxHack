# Design rules for webapp/static/

Follow these for every page. Reference look: a railway timetable or tide table, an Ordnance
Survey map and the Met Office shipping forecast. Dense, tabular, plain, confident. Not a SaaS
landing page.

## Look
- Colours only from `css/tokens.css`: paper background, ink / ink-2 text, rule hairlines, rain
  for rain, alarm for too wet or value lost. No Tailwind palette colours (indigo, violet, slate...).
- No gradients, glows, blur, glassmorphism or box-shadows. Corner radius 0-2px.
- Separate content with 1px rules (`var(--rule)`) and space, not cards with shadows.
- Newsreader for words; IBM Plex Mono with `tabular-nums` for every number and time. Never Inter.
- Left-aligned, asymmetric layouts. No centred hero, no three-card feature row.
- Fonts are in `static/fonts/`, not loaded from Google, so the venue wifi can't break them.

## Status: a small square lamp and its word, never colour alone
| Status | Lamp | Meaning |
|---|---|---|
| ready | field green `--ready` | can be cut now |
| soon | straw `--soon` | a window opens within hours |
| wait | brick `--wait` | not today |
| done | hollow `--done` | all cut |

These four colours are only for field status (and the matching good / fair / poor hours on the
Weather page).

## Crop: the field's outline colour, and a short bar next to its word
Wheat, barley and OSR have their own colours (`--wheat`, `--barley`, `--osr`): the outline of
every field on the map, and a short bar (never a square, so it isn't read as a lamp) before the
crop's word in keys and tables. Weather maps keep their own colour scales because they are data,
always with a legend.

## Few words, big answers
- Each page opens with one sentence that answers the question, e.g. "Cut today." then one line of
  why, built from the numbers.
- Everything else is tables with short column heads, figures in mono.
- Every claim has a number, a unit, a time or a source. Format: `£1,912/ha`, `19.4%`, `Tue 14:00`.
- No algorithm words (planner, ensemble, member, optimiser). Say ready, best time, plan, forecast.
- Write like an agronomist texting a farmer. Banned words: seamless, revolutionise, unlock,
  empower, leverage, harness, cutting-edge, reimagine, effortless, powerful.
- No icons, emoji, pills, rings, avatars, badges, testimonials, invented stats, logo clouds or
  pricing. A word or a lamp does the job.
- No dead links or placeholder text. A button that doesn't work yet isn't shown.

## Controls
- Buttons: ink rectangles (main) or outlined (secondary), 44px tall, mono labels.
- Switches: a square ON / OFF box on the right of a hairline row.
- Buttons and switches on the Control page are pretend: they answer with a short message
  bottom-left and remember their state while browsing, but don't change the plan.

## Charts
- Direct labels at the right-hand end, no legend boxes.
- Straight lines between hourly points, never smoothed. Midnight ticks labelled "Tue 27".
- The "now" line is the one thing that moves when time moves.
- Charts that share an hour axis share their left and right margins, so their hours line up.
- Today's weather chart shows one thing at a time, picked by a tab (Rain, Moisture, Temperature),
  each with its own colour steps and key: rain in rain blue, moisture from straw to soil with
  alarm for too wet, temperature from rain blue through paper to alarm.

## Motion
- Only things that change with time move: combines, the cut area, the now line, the home page's
  footage. No scroll animations, no counting-up numbers, no hover lifts.
- The cut area is the field's passes in paper, one pass wide, ending under the combine.
- The Map's Play runs the next 48 h fast, with PLAY in the clock and the hours ahead counted
  next to the button, then goes back to live by itself.

## Real and pretend
- Weather is real (Open-Meteo forecast, RainViewer radar), fetched live by the browser.
- Fields, combines and GPS come from the simulated season (`source.py`).
- Machine readings (fuel, tank, speed) are pretend.

## When building with an AI assistant
After each change, list any default you fell back on (font, colour, radius, shadow, copy) so it
can be replaced. Prefer deleting things to adding them.
