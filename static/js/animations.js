/* Scroll reveal, animated count-up, and progress-bar fill.
   All skipped in favor of final-state-immediately when the user has
   prefers-reduced-motion set. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function animateCount(el) {
    var target = parseFloat(el.dataset.countTo || "0");
    var suffix = el.dataset.countSuffix || "";
    var duration = 1200;
    var start = null;

    function step(timestamp) {
      if (start === null) start = timestamp;
      var progress = Math.min((timestamp - start) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      var value = Math.round(target * eased);
      el.textContent = value.toLocaleString() + suffix;
      if (progress < 1) window.requestAnimationFrame(step);
    }
    window.requestAnimationFrame(step);
  }

  function revealElement(el) {
    el.classList.add("is-visible");

    if (el.dataset.countTo !== undefined) {
      reduceMotion ? (el.textContent = el.dataset.countTo + (el.dataset.countSuffix || "")) : animateCount(el);
    }

    var bar = el.matches(".progress-fill") ? el : el.querySelector(".progress-fill");
    if (bar && bar.dataset.progress !== undefined) {
      var pct = bar.dataset.progress + "%";
      if (reduceMotion) {
        bar.style.width = pct;
      } else {
        window.requestAnimationFrame(function () {
          bar.style.width = pct;
        });
      }
    }
  }

  var targets = document.querySelectorAll(".reveal");

  if (reduceMotion || !("IntersectionObserver" in window)) {
    targets.forEach(revealElement);
    return;
  }

  var observer = new IntersectionObserver(
    function (entries, obs) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          revealElement(entry.target);
          obs.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.2 }
  );

  targets.forEach(function (el) {
    observer.observe(el);
  });
})();
