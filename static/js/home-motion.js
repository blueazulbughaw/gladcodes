/* Home page motion (GSAP + ScrollTrigger from CDN, no build step).
   - Hero entrance: headline lines, lede, buttons stagger in; the NOW card
     floats up and drifts with a little parallax as you scroll.
   - Pinned split: the timeline title stays pinned while months scroll by.
   - Chapters, bento cards and milestones ease in as they enter.
   Does nothing under prefers-reduced-motion or if GSAP fails to load —
   the page is fully readable in its static state either way. */
(function () {
  "use strict";
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!window.gsap || !window.ScrollTrigger) return;
  gsap.registerPlugin(ScrollTrigger);

  var ease = "power3.out";

  // Hero entrance.
  var hero = gsap.timeline({ defaults: { ease: ease } });
  hero.from(".hero-line", { yPercent: 60, opacity: 0, duration: 1, stagger: 0.12 })
      .from(".hero-lede", { y: 24, opacity: 0, duration: 0.8 }, "-=0.55")
      .from(".hero-actions .btn", { y: 18, opacity: 0, duration: 0.6, stagger: 0.08 }, "-=0.5")
      .from(".now-card", { y: 80, rotate: 8, opacity: 0, duration: 1.1, ease: "power4.out" }, "-=0.9");

  var mm = gsap.matchMedia();

  mm.add("(min-width: 1001px)", function () {
    // NOW card parallax: drifts up and straightens as the hero scrolls away.
    gsap.to(".now-card", {
      yPercent: -18, rotate: -1, ease: "none",
      scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true }
    });
  });

  mm.add("(min-width: 901px)", function () {
    // Pinned split: hold the timeline title while the month list scrolls.
    var flow = document.querySelector(".split-flow");
    var pin = document.querySelector(".split-pin");
    if (flow && pin && flow.offsetHeight > pin.offsetHeight + 200) {
      pin.style.position = "static";  // let GSAP own pinning instead of CSS sticky
      ScrollTrigger.create({
        trigger: ".split",
        start: "top 110",
        end: function () { return "+=" + (flow.offsetHeight - pin.offsetHeight); },
        pin: pin,
        pinSpacing: false
      });
    }
  });

  // Milestones rise in one after another.
  gsap.utils.toArray(".timeline-month").forEach(function (month) {
    gsap.from(month.querySelectorAll(".milestone"), {
      y: 40, opacity: 0, duration: 0.7, stagger: 0.08, ease: ease,
      scrollTrigger: { trigger: month, start: "top 85%" }
    });
  });

  // Chapter titles, bento cards and accordion slices ease in.
  gsap.utils.toArray(".chapter-title:not(#timelineTitle), .cta-title").forEach(function (el) {
    gsap.from(el, { y: 50, opacity: 0, duration: 1, ease: ease, scrollTrigger: { trigger: el, start: "top 88%" } });
  });
  // (Journal cards are left to the site-wide .reveal fade: animating both clashes.)
  [".bento-card", ".accordion-slice"].forEach(function (selector) {
    var items = gsap.utils.toArray(selector);
    if (!items.length) return;
    gsap.from(items, {
      y: 60, scale: 0.96, opacity: 0, duration: 0.9, stagger: 0.1, ease: ease,
      scrollTrigger: { trigger: items[0], start: "top 88%" }
    });
  });

  // Charts/images resized by layout shifts: recompute trigger positions once
  // fonts and the chart have settled.
  window.addEventListener("load", function () { ScrollTrigger.refresh(); });
})();
