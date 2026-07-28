const CACHE = 'mercatini-v1';
const OFFLINE = [
  '/',
  '/static/css/main.css',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(OFFLINE)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then(r => { const c = r.clone(); caches.open(CACHE).then(ch => ch.put(e.request, c)); return r; })
      .catch(() => caches.match(e.request).then(r => r || caches.match('/')))
  );
});
