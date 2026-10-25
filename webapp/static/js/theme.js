// The colours from css/tokens.css, as values the map and chart libraries can use.

const css = getComputedStyle(document.documentElement);
const token = (name) => css.getPropertyValue(`--${name}`).trim();

export const colours = {
  paper: token("paper"),
  ink: token("ink"),
  ink2: token("ink-2"),
  rule: token("rule"),
  straw: token("straw"),
  soil: token("soil"),
  rain: token("rain"),
  alarm: token("alarm"),
};

export const dataFont = token("font-data");
