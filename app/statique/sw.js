// Garde une copie de la page : si le serveur ne tourne pas, la fenêtre de l'app affiche
// « Serveur injoignable » (et réessaie) au lieu d'une erreur du navigateur.
const CACHE = 'mybgremover-1';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['/', '/icone-192.png'])));
  self.skipWaiting();
});
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

// réseau d'abord : toujours la page à jour quand le serveur répond
self.addEventListener('fetch', e => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(
    fetch(e.request)
      .then(r => { const copie = r.clone(); caches.open(CACHE).then(c => c.put('/', copie)); return r; })
      .catch(() => caches.match('/'))
  );
});
