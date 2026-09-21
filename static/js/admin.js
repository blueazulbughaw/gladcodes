/* Mobile sidebar toggle for the admin panel. */
(function () {
  "use strict";
  var toggle = document.querySelector(".admin-nav-toggle");
  var sidebar = document.querySelector(".admin-sidebar");
  if (!toggle || !sidebar) return;

  toggle.addEventListener("click", function () {
    var isOpen = sidebar.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });

  sidebar.querySelectorAll("nav a").forEach(function (link) {
    link.addEventListener("click", function () {
      sidebar.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
    });
  });
})();
