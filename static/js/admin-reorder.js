/* Drag-to-reorder for admin card grids (Timeline, Projects, Toolbox, etc).
   Persists the new order as each row's sort_order via /<resource>/reorder.
   Uses SortableJS (CDN) rather than hand-rolled HTML5 drag-and-drop since
   the grid wraps into multiple columns — plain dragover math doesn't
   handle that well, and Sortable also gets touch support for free. */
(function () {
  "use strict";
  // Grouped lists (e.g. skills by category) have one grid per group. Each
  // is sortable on its own (no dragging between groups), but a drop saves
  // the order of EVERY card on the page, so groups keep their relative
  // order and sort_order stays one consistent sequence.
  var grids = document.querySelectorAll(".admin-card-grid[data-reorder-url]");
  if (!grids.length || !window.Sortable) return;

  var reorderUrl = grids[0].getAttribute("data-reorder-url");
  var csrfToken = grids[0].getAttribute("data-csrf-token");

  function saveOrder() {
    var ids = [];
    grids.forEach(function (grid) {
      grid.querySelectorAll(".admin-card-item").forEach(function (card) {
        ids.push(card.getAttribute("data-id"));
      });
    });
    var body = new URLSearchParams();
    body.append("csrf_token", csrfToken);
    ids.forEach(function (id) { body.append("id", id); });
    fetch(reorderUrl, { method: "POST", body: body });
  }

  grids.forEach(function (grid) {
    Sortable.create(grid, {
      animation: 150,
      ghostClass: "admin-card-item--ghost",
      // Touch-drag starting instantly hijacks normal page scrolling (a swipe
      // on a card becomes a drag instead of a scroll) — require a long press
      // before a touch drag begins. Mouse users aren't affected: clicking
      // and holding was never how they scroll, so delayOnTouchOnly keeps
      // mouse drags starting immediately.
      delay: 200,
      delayOnTouchOnly: true,
      touchStartThreshold: 5,
      onEnd: saveOrder
    });
  });
})();
