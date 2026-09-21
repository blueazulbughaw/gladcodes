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

/* Icon picker (Projects/Toolbox/Community "icon" field): clicking a button
   sets the hidden input the form actually submits and highlights the
   choice. A separate IIFE from the sidebar toggle above since it has
   nothing to do with it and shouldn't bail out just because a page (there
   isn't one, but in principle) lacks a sidebar. */
(function () {
  "use strict";
  document.querySelectorAll(".icon-picker").forEach(function (picker) {
    var hidden = picker.querySelector("input[type=hidden]");
    var options = picker.querySelectorAll(".icon-picker-option");
    options.forEach(function (btn) {
      btn.addEventListener("click", function () {
        hidden.value = btn.getAttribute("data-icon");
        options.forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
      });
    });
  });
})();
