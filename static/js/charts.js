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

  window.GladCharts = { lineChart: lineChart, barChart: barChart };
})();
