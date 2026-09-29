// Exists only so Chrome considers the app installable ("Add to Home
// Screen") and opens it in its own standalone window - this is a live
// dashboard, so every request always goes to the network. Nothing is
// cached; a naive cache-first worker here would show stale PR/run status
// instead of the whole point of the app.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
