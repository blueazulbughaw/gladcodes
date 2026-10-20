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

  var spread = ["#0E8A8A", "#3F88C5", "#E7A93C", "#5EC4C4", "#1A2E44", "#3BA55D", "#C0638E", "#8C6BC2", "#D9774B", "#7A8B99", "#B5A642", "#4FA3A3", "#9A6A12"];

  // Spending by category. `currency` prefixes tooltip amounts.
  function doughnutChart(canvasId, labels, data, currency) {
    var el = document.getElementById(canvasId);
    if (!el) return null;
    return new Chart(el, {
      type: "doughnut",
      data: { labels: labels, datasets: [{ data: data, backgroundColor: spread, borderWidth: 2, borderColor: "#fff" }] },
      options: {
        responsive: true, cutout: "62%",
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: function (ctx) { return " " + ctx.label + ": " + (currency || "") + ctx.parsed.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }); } } }
        }
      }
    });
  }

  // Side-by-side bars per label (e.g. earned vs spent per month).
  function groupedBarChart(canvasId, labels, series) {
    var el = document.getElementById(canvasId);
    if (!el) return null;
    var colors = [palette.teal, "#E7A93C", palette.ocean];
    return new Chart(el, {
      type: "bar",
      data: { labels: labels, datasets: series.map(function (s, i) { return { label: s.label, data: s.data, backgroundColor: colors[i % colors.length], borderRadius: 6 }; }) },
      options: { responsive: true, plugins: { legend: { display: true, position: "bottom" } }, scales: { y: { beginAtZero: true } } }
    });
  }

  window.GladCharts = { lineChart: lineChart, barChart: barChart, multiLineChart: multiLineChart, doughnutChart: doughnutChart, groupedBarChart: groupedBarChart };
})();
