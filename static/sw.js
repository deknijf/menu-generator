/* Service worker voor de Meal Planner.
 *
 * Bestaansreden: de boodschappenlijst wordt in de supermarkt gebruikt, waar het
 * mobiele bereik vaak wegvalt. Zonder deze worker toont de app daar een foutpagina
 * precies op het moment dat je hem nodig hebt.
 *
 * Strategie:
 *   - app-shell (CSS/JS/iconen): cache-first, want die veranderen alleen bij een release
 *   - navigaties en API-GETs: network-first met cache als vangnet, zodat je online
 *     altijd verse data ziet en offline de laatst bekende
 *   - alles wat muteert (POST/PUT/DELETE): nooit cachen; app.js zet die in een
 *     wachtrij als het netwerk weg is
 *
 * Bump CACHE_VERSION bij elke wijziging aan de gecachte assets.
 */

const CACHE_VERSION = "mp-v1";
const SHELL_CACHE = `${CACHE_VERSION}-shell`;
const DATA_CACHE = `${CACHE_VERSION}-data`;

const SHELL_ASSETS = [
  "/static/styles.css",
  "/static/app.js",
  "/static/logo-mark.svg",
  "/static/logo-wordmark.svg",
  "/static/favicon.svg",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/manifest.webmanifest",
];

// API-GETs die offline zinvol zijn om terug te tonen.
const CACHEABLE_API = [
  "/api/shopping-list",
  "/api/calendar",
  "/api/custom-meals",
  "/api/profile",
  "/api/settings",
  "/api/session",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      // addAll faalt in zijn geheel als één bestand mist; per stuk is robuuster.
      .then((cache) => Promise.allSettled(SHELL_ASSETS.map((url) => cache.add(url))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => !key.startsWith(CACHE_VERSION)).map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

function isShellAsset(url) {
  return url.origin === self.location.origin && url.pathname.startsWith("/static/");
}

function isCacheableApi(url) {
  return (
    url.origin === self.location.origin &&
    CACHEABLE_API.some((path) => url.pathname === path || url.pathname.startsWith(path + "?"))
  );
}

async function networkFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) {
      // Markeer het antwoord, zodat app.js weet dat dit uit de cache komt.
      const headers = new Headers(cached.headers);
      headers.set("X-From-Cache", "1");
      return new Response(cached.body, {
        status: cached.status,
        statusText: cached.statusText,
        headers,
      });
    }
    throw err;
  }
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.ok) {
    const cache = await caches.open(cacheName);
    cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;

  // Mutaties nooit onderscheppen: die horen bij de wachtrij in app.js.
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Uitloggen moet altijd het netwerk raken, anders blijf je in een cache hangen.
  if (url.pathname === "/logout" || url.pathname.startsWith("/auth/")) return;

  if (isShellAsset(url)) {
    event.respondWith(cacheFirst(request, SHELL_CACHE));
    return;
  }

  if (isCacheableApi(url)) {
    event.respondWith(networkFirst(request, DATA_CACHE));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      networkFirst(request, DATA_CACHE).catch(() =>
        caches.match("/").then((cached) => cached || Response.error())
      )
    );
  }
});

// app.js vraagt hierom bij het uitloggen, zodat er geen data van een vorige
// gebruiker in de cache achterblijft.
self.addEventListener("message", (event) => {
  if (event.data === "clear-caches") {
    event.waitUntil(caches.keys().then((keys) => Promise.all(keys.map((key) => caches.delete(key)))));
  }
});
