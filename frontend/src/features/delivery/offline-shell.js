/** Call in the platform service worker with its public HTML shell and built asset URLs.
 * Mount the worker at the origin root so direct attempt navigations are in scope.
 */
export function installDeliveryShell(worker, { version, shell, assets }) {
  const prefix = "folio-delivery-shell-";
  const name = prefix + version;
  const shellUrl = new URL(shell, worker.location.origin).href;
  const urls = [shellUrl, ...assets.map(asset => new URL(asset, worker.location.origin).href)];
  worker.addEventListener("install", event => event.waitUntil(
    caches.open(name).then(cache => cache.addAll(urls.map(url =>
      new Request(url, { credentials: "omit", cache: "reload" }))))
  ));
  worker.addEventListener("activate", event => event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith(prefix) && key !== name) await caches.delete(key);
    }
    await worker.clients.claim();
  })()));
  worker.addEventListener("fetch", event => {
    const req = event.request;
    if (req.method !== "GET") return;
    const url = new URL(req.url);
    if (url.origin !== worker.location.origin) return;
    const navigation = req.mode === "navigate" && /^\/attempts\/[^/]+\/?$/.test(url.pathname);
    if (!navigation && !urls.includes(req.url)) return;
    event.respondWith((async () => {
      const cache = await caches.open(name);
      return await cache.match(navigation ? shellUrl : req.url) || fetch(req);
    })());
  });
}
