/* Drag-to-reorder for admin card grids (Timeline, Projects, Toolbox, etc).
   Persists the new order as each row's sort_order via /<resource>/reorder.
   Uses SortableJS (CDN) rather than hand-rolled HTML5 drag-and-drop since
   the grid wraps into multiple columns — plain dragover math doesn't
   handle that well, and Sortable also gets touch support for free. */
(function () {
  "use strict";
  var grid = document.querySelector(".admin-card-grid[data-reorder-url]");
  if (!grid || !window.Sortable) return;

  var reorderUrl = grid.getAttribute("data-reorder-url");
  var csrfToken = grid.getAttribute("data-csrf-token");

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
    onEnd: function () {
      var ids = Array.prototype.map.call(
        grid.querySelectorAll(".admin-card-item"),
        function (card) { return card.getAttribute("data-id"); }
      );
      var body = new URLSearchParams();
      body.append("csrf_token", csrfToken);
      ids.forEach(function (id) { body.append("id", id); });
      fetch(reorderUrl, { method: "POST", body: body });
    }
  });
})();
