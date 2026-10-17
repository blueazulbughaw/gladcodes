/* Scroll-driven animation for the /resume career timeline: a page-wide
   scroll progress bar, a scrubbed fill line down the timeline spine,
   dramatic staggered card entrances (scale + rotate + slide, alternating
   by side), pulsing "active" dots, and a floating badge showing which era
   is currently in view. Needs GSAP + ScrollTrigger (loaded via CDN in
   resume.html) — everything here no-ops if either is missing.

   prefers-reduced-motion skips every scroll-linked/animated effect below
   and just shows the final state, same policy as animations.js. */
(function () {
  "use strict";
  if (!window.gsap || !window.ScrollTrigger) return;

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var track = document.getElementById("careerTimeline");
  var items = document.querySelectorAll(".career-timeline-item");
  var heroEls = document.querySelectorAll(".hero-fade");

  var skillGroups = document.querySelectorAll("[data-skills-group]");

  if (reduceMotion) {
    heroEls.forEach(function (el) { el.style.opacity = 1; });
    items.forEach(function (item) {
      var card = item.querySelector(".career-timeline-card");
      if (card) card.style.opacity = 1;
    });
    skillGroups.forEach(function (group) { group.style.opacity = 1; });
    return;
  }

  gsap.registerPlugin(ScrollTrigger);

  if (heroEls.length) {
    gsap.from(heroEls, { opacity: 0, y: 24, duration: 0.7, stagger: 0.12, ease: "power3.out" });
  }

  var progressBar = document.getElementById("scrollProgress");
  if (progressBar) {
    gsap.to(progressBar, {
      width: "100%",
      ease: "none",
      scrollTrigger: { start: 0, end: "max", scrub: true },
    });
  }

  // Skills: each category card pops in, then its tags cascade in one after
  // another — independent of the timeline below, so it still runs even on
  // a page that somehow has no timeline rows.
  skillGroups.forEach(function (group) {
    var tags = group.querySelectorAll(".skills-tags span");
    gsap.from(group, {
      opacity: 0,
      y: 30,
      scale: 0.92,
      duration: 0.5,
      ease: "power2.out",
      scrollTrigger: { trigger: group, start: "top 88%", toggleActions: "play none none none" },
    });
    if (tags.length) {
      gsap.from(tags, {
        opacity: 0,
        scale: 0.6,
        duration: 0.35,
        stagger: 0.04,
        delay: 0.15,
        ease: "back.out(1.7)",
        scrollTrigger: { trigger: group, start: "top 88%", toggleActions: "play none none none" },
      });
    }
  });

  if (!track || !items.length) return;

  var progressFill = document.getElementById("careerTimelineProgress");
  if (progressFill) {
    gsap.to(progressFill, {
      height: "100%",
      ease: "none",
      scrollTrigger: { trigger: track, start: "top 75%", end: "bottom 60%", scrub: true },
    });
  }

  var indicator = document.getElementById("careerIndicator");
  var indicatorLabel = indicator ? indicator.querySelector("span") : null;

  if (indicator) {
    ScrollTrigger.create({
      trigger: track,
      start: "top 80%",
      end: "bottom 20%",
      onEnter: function () { indicator.classList.add("is-visible"); },
      onEnterBack: function () { indicator.classList.add("is-visible"); },
      onLeave: function () { indicator.classList.remove("is-visible"); },
      onLeaveBack: function () { indicator.classList.remove("is-visible"); },
    });
  }

  var isDesktop = window.matchMedia("(min-width: 760px)").matches;

  items.forEach(function (item, index) {
    var card = item.querySelector(".career-timeline-card");
    var dot = item.querySelector(".career-timeline-dot");
    var fromRight = isDesktop && index % 2 === 1;

    if (card) {
      gsap.from(card, {
        opacity: 0,
        y: 50,
        scale: 0.88,
        rotate: fromRight ? 2 : -2,
        duration: 0.7,
        ease: "power3.out",
        scrollTrigger: { trigger: item, start: "top 85%", toggleActions: "play none none none" },
      });
    }
    if (dot) {
      gsap.from(dot, {
        scale: 0,
        duration: 0.5,
        delay: 0.1,
        ease: "back.out(2.5)",
        scrollTrigger: { trigger: item, start: "top 85%", toggleActions: "play none none none" },
      });
    }

    ScrollTrigger.create({
      trigger: item,
      start: "top center",
      end: "bottom center",
      onToggle: function (self) {
        if (dot) dot.classList.toggle("is-active", self.isActive);
        if (self.isActive && indicatorLabel) indicatorLabel.textContent = item.dataset.period || "";
      },
    });
  });
})();
