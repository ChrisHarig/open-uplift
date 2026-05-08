// Matte chart palette. Differentiable but less poppy than the previous
// saturated tailwind defaults. No pink.
//
// Use these for all Recharts <Bar />, <Cell />, <Line /> fills/strokes.

export const CHART = {
  // Primary categorical accents — pick by index for series.
  steel: "#5b7794",   // muted blue
  sage: "#5d8a6f",    // muted green
  brick: "#a1554f",   // muted red
  ochre: "#b58c5e",   // muted amber
  dusk: "#76678e",    // muted purple
  stone: "#7a7a8e",   // slate (replaces pink)
  ink: "#3a3a3a",     // near-black for primary single-series bars
  // Grid + axis chrome.
  grid: "#dcdcd6",
  axis: "#888880",
} as const;

export const CHART_SERIES: string[] = [
  CHART.steel,
  CHART.sage,
  CHART.ochre,
  CHART.dusk,
  CHART.brick,
  CHART.stone,
];
