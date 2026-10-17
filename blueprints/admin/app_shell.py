"""Makes the admin installable as an app ("Today") with check-in reminders.

The manifest and service worker are served from /gc-admin/ rather than
/static/ on purpose: a public static file naming /gc-admin/today would
disclose the admin URL. Both are exempt from the auth gate (see
routes.PUBLIC_ENDPOINTS) so installs and the browser's background service
worker updates keep working after the 30-minute JWT expires; neither
contains anything beyond the app's name and start URL.
"""
from flask import Response, jsonify, request, url_for

from services.push import delete_subscription, enabled, save_subscription, send_to_all

from . import admin_bp

SERVICE_WORKER_JS = """
// Check-in reminders (sent by services/push.py). No offline caching:
// every admin page needs a live, authenticated response.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) {}
  e.waitUntil(self.registration.showNotification(data.title || "Today", {
    body: data.body || "",
    icon: "%(icon)s",
    badge: "%(icon)s",
    tag: data.tag || "checkin",
    renotify: true,
    data: { url: data.url || "%(start)s" },
  }));
});

// Tapping it focuses the open app window (or opens one) on the check-in.
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = new URL((e.notification.data && e.notification.data.url) || "%(start)s", self.location.origin).href;
  e.waitUntil((async () => {
    const open = await clients.matchAll({ type: "window", includeUncontrolled: true });
    const win = open.find((c) => c.url.startsWith(self.registration.scope));
    if (win) { await win.focus(); return win.navigate ? win.navigate(url) : undefined; }
    return clients.openWindow(url);
  })());
});
"""


@admin_bp.route("/manifest.webmanifest")
def manifest():
    icon = lambda name: url_for("static", filename=f"icons/{name}")  # noqa: E731
    data = {
        "id": url_for("admin.today"),
        "name": "GladCodes Today",
        "short_name": "Today",
        "description": "Daily check-in: mood, reading, gratitude, and the one thing to ship.",
        "start_url": url_for("admin.today"),
        "scope": url_for("admin.index"),
        "display": "standalone",
        "background_color": "#FAF6EF",
        "theme_color": "#1A2E44",
        "icons": [
            {"src": icon("app-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": icon("app-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": icon("app-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    response = jsonify(data)
    response.mimetype = "application/manifest+json"
    return response


@admin_bp.route("/sw.js")
def service_worker():
    js = SERVICE_WORKER_JS % {
        "icon": url_for("static", filename="icons/app-192.png"),
        "start": url_for("admin.today"),
    }
    response = Response(js, mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


def _valid_subscription(endpoint, p256dh, auth):
    return (
        endpoint.startswith("https://") and len(endpoint) <= 500
        and 0 < len(p256dh) <= 255 and 0 < len(auth) <= 255
    )


@admin_bp.route("/push/subscribe", methods=["POST"])
def push_subscribe():
    endpoint = request.form.get("endpoint", "")
    p256dh = request.form.get("p256dh", "")
    auth = request.form.get("auth", "")
    if not _valid_subscription(endpoint, p256dh, auth):
        return jsonify({"ok": False}), 400
    save_subscription(endpoint, p256dh, auth, request.user_agent.string or "")
    return jsonify({"ok": True})


@admin_bp.route("/push/unsubscribe", methods=["POST"])
def push_unsubscribe():
    endpoint = request.form.get("endpoint", "")
    if endpoint:
        delete_subscription(endpoint[:500])
    return jsonify({"ok": True})


@admin_bp.route("/push/test", methods=["POST"])
def push_test():
    if not enabled():
        return jsonify({"ok": False, "sent": 0}), 503
    sent = send_to_all("It works ✨", "This is where your check-in reminders will show up.", url_for("admin.today"), tag="test")
    return jsonify({"ok": sent > 0, "sent": sent})
