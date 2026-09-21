/* Sidebar toggle for the admin panel. .nav-toggled means "flipped away
   from the breakpoint's default" — desktop defaults to expanded (toggled
   = collapsed), mobile defaults to collapsed (toggled = expanded) — so
   aria-expanded has to be computed per breakpoint rather than read
   straight off the class. */
(function () {
  "use strict";
  var toggle = document.querySelector(".admin-nav-toggle");
  var sidebar = document.querySelector(".admin-sidebar");
  if (!toggle || !sidebar) return;

  var isDesktop = function () {
    return window.matchMedia("(min-width: 861px)").matches;
  };

  var updateAria = function () {
    var toggled = sidebar.classList.contains("nav-toggled");
    var expanded = isDesktop() ? !toggled : toggled;
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
  };

  toggle.addEventListener("click", function () {
    sidebar.classList.toggle("nav-toggled");
    updateAria();
  });

  sidebar.querySelectorAll("nav a").forEach(function (link) {
    link.addEventListener("click", function () {
      sidebar.classList.remove("nav-toggled");
      updateAria();
    });
  });

  updateAria();
})();
