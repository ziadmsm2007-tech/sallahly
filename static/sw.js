const CACHE = 'drcar-v1';
const ASSETS = ['/landing', '/static/css/style.css', '/static/images/logo.svg', '/static/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(()=>self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', e => {
  // Network first for API, cache first for assets
  if (e.request.url.includes('/api/') || e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then(cached => {
      const fetched = fetch(e.request).then(resp => {
        if(resp.ok) caches.open(CACHE).then(c=>c.put(e.request, resp.clone()));
        return resp;
      }).catch(()=>cached);
      return cached || fetched;
    })
  );
});

self.addEventListener('push', e => {
  const data = e.data ? e.data.json() : {title: 'Dr. Car', body: 'لديك إشعار جديد'};
  e.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    icon: '/static/images/logo.svg',
    badge: '/static/images/logo.svg',
    vibrate: [200,100,200]
  }));
});