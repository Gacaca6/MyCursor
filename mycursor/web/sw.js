'use strict';
// Cache only the UI, never credentials, commands, or WebSocket traffic.
const CACHE = 'mycursor-shell-v4';
const FILES = ['/', '/style.css', '/app.js', '/scanner.js', '/zxing.js', '/zxing_reader.wasm', '/icon-180.png', '/icon-192.png', '/icon-512.png'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES))); self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k.startsWith('mycursor-shell-') && k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !FILES.includes(url.pathname)) return;
  event.respondWith(fetch(event.request).then(response => {
    if (response.ok) { const copy = response.clone(); caches.open(CACHE).then(cache => cache.put(url.pathname, copy)); }
    return response;
  }).catch(() => caches.match(url.pathname)));
});
