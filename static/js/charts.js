/* Thin Chart.js helpers styled to the GladCodes palette (teal/ocean lines,
   aqua fills) — see CLAUDE.md: Chart.js is loaded from CDN, no build step. */
(function () {
  "use strict";
  if (typeof Chart === "undefined") return;

  var palette = {
    teal: "#0E8A8A",
    ocean: "#3F88C5",
    aqua: "rgba(94, 196, 196, 0.25)",
    navy: "#1A2E44",
  };

  Chart.defaults.font.family = "Inter, sans-serif";
  Chart.defaults.color = palette.navy;
  Chart.defaults.plugins.legend.display = false;

  function lineChart(canvasId, labels, data, label) {
    var el = document.getElementById(canvasId);
    if (!el) return null;
    return new Chart(el, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: label,
            data: data,
            borderColor: palette.teal,
            backgroundColor: palette.aqua,
            fill: true,
            tension: 0.35,
            pointBackgroundColor: palette.teal,
          },
        ],
      },
      options: { responsive: true, scales: { y: { beginAtZero: true } } },
    });
  }

  function barChart(canvasId, labels, data, label) {
    var el = document.getElementById(canvasId);
    if (!el) return null;
    return new Chart(el, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: label,
            data: data,
            backgroundColor: palette.ocean,
            borderRadius: 6,
          },
        ],
      },
      options: { responsive: true, scales: { y: { beginAtZero: true } } },
    });
  }

  // Several series on one axis (e.g. mood/energy/focus). Gaps (null) are
  // bridged so a missed day doesn't break the line. opts.min/opts.max pin
  // the y-axis, e.g. to a 1–5 scale; opts.tickLabels swaps axis numbers for
  // labels (emojis); opts.colorIndex shifts the line colour.
  function multiLineChart(canvasId, labels, series, opts) {
    var el = document.getElementById(canvasId);
    if (!el) return null;
    var colors = [palette.teal, palette.ocean, "#E7A93C", palette.navy];
    opts = opts || {};
    return new Chart(el, {
      type: "line",
      data: {
        labels: labels,
        datasets: series.map(function (s, i) {
          var color = colors[(i + (opts.colorIndex || 0)) % colors.length];
          return {
            label: s.label,
            data: s.data,
            borderColor: color,
            backgroundColor: color,
            pointBackgroundColor: color,
            tension: 0.35,
            spanGaps: true,
          };
        }),
      },
      options: {
        responsive: true,
        plugins: { legend: { display: series.length > 1, position: "bottom" } },
        scales: { y: { min: opts.min, max: opts.max, ticks: {
          stepSize: 1,
          // opts.tickLabels ({"1": "...", ...}) shows emojis on the axis instead of numbers.
          font: opts.tickLabels ? { size: 16 } : undefined,
          callback: function (value) { return opts.tickLabels ? (opts.tickLabels[String(value)] || "") : value; }
        } } },
      },
    });
  }

  window.GladCharts = { lineChart: lineChart, barChart: barChart, multiLineChart: multiLineChart };
})();
