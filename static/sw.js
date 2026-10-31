/* BILMAGAZINE · 渐进式 Web 应用 service worker
   策略：页面网络优先（离线回落到缓存），静态资源 stale-while-revalidate。
   控制台与写入接口永远走网络，不缓存。 */
const VERSION = 'bilmag-v6';
const SHELL = `${VERSION}-shell`;
const PAGES = `${VERSION}-pages`;

const PRECACHE = [
  '/',
  '/manifest.webmanifest',
  '/static/app.css',
  '/static/shell.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/maskable-512.png',
  '/static/icons/apple-touch-icon.png',
  '/offline.html'
];

const BYPASS = ['/manage', '/run', '/run-demo', '/subscriptions', '/subscribe-wechat', '/subscribe-rss', '/subs', '/api'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== SHELL && key !== PAGES).map((key) => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

function isBypass(url) {
  return BYPASS.some((path) => url.pathname === path || url.pathname.startsWith(path + '/'));
}

function cachePut(name, request, response) {
  if (!response || !response.ok) return response;
  const copy = response.clone();
  caches.open(name).then((cache) => cache.put(request, copy)).catch(() => {});
  return response;
}

async function pageResponse(request) {
  try {
    const response = await fetch(request);
    return cachePut(PAGES, request, response);
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    const offline = await caches.match('/offline.html');
    if (offline) return offline;
    return caches.match('/');
  }
}

async function assetResponse(request) {
  const cached = await caches.match(request);
  const network = fetch(request)
    .then((response) => cachePut(SHELL, request, response))
    .catch(() => null);
  if (cached) {
    network.catch(() => {});
    return cached;
  }
  const response = await network;
  return response || caches.match('/offline.html');
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isBypass(url) || url.pathname === '/sw.js') return;

  if (request.mode === 'navigate') {
    event.respondWith(pageResponse(request));
    return;
  }

  if (url.pathname.startsWith('/static/') || url.pathname.startsWith('/thumbs/') || url.pathname.startsWith('/icons/')) {
    event.respondWith(assetResponse(request));
  }
});

self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting();
});
