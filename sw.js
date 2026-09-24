/* Service worker: deixa o site abrir sem internet depois da primeira visita.
   Arquivos do próprio site: rede primeiro, cópia guardada se estiver sem conexão,
   assim uma música nova ou uma correção aparecem assim que houver rede.
   Fontes e bibliotecas de CDN (endereços com versão fixa): cópia guardada primeiro. */
const SITE = 'flyback-site-v1';
const MANTER = [SITE, 'flyback-acervo', 'flyback-cdn'];
const BASE = ['./', 'index.html', 'stems.html', 'manifest.webmanifest',
  'icones/icone.svg', 'icones/icone-180.png', 'icones/icone-192.png', 'icones/icone-512.png'];
const CDN = /^https:\/\/(fonts\.googleapis\.com|fonts\.gstatic\.com|cdn\.jsdelivr\.net)\//;

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SITE).then(c => c.addAll(BASE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => !MANTER.includes(k)).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  if (url.origin === location.origin){
    const destino = url.pathname.includes('/musicas/') ? 'flyback-acervo' : SITE;
    e.respondWith(fetch(req).then(res => {
      if (res.ok){ const copia = res.clone(); caches.open(destino).then(c => c.put(req, copia)); }
      return res;
    }).catch(() => caches.match(req, { ignoreSearch: true, ignoreVary: true })
      .then(r => r || (req.mode === 'navigate' ? caches.match('index.html') : Response.error()))));
    return;
  }

  if (CDN.test(req.url)){
    e.respondWith(caches.match(req, { ignoreVary: true }).then(r => r || fetch(req).then(res => {
      if (res.ok || res.type === 'opaque'){ const copia = res.clone(); caches.open('flyback-cdn').then(c => c.put(req, copia)); }
      return res;
    })));
  }
});
