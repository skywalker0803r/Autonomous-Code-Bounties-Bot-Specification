// Exists only so this is installable on the phone's home screen and opens
// in its own standalone window - PR/comment data always goes straight to
// GitHub's API, nothing here is cached.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
