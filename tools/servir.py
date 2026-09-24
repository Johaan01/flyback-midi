#!/usr/bin/env python3
"""Servidor local para testar o site antes de publicar.

    python tools/servir.py          (porta 8000)
    python tools/servir.py 8080

Atualiza musicas/index.json e serve a pasta do projeto. No computador, abra
http://localhost:8000. No celular, na mesma rede Wi-Fi, abra o endereço
http://IP-DO-COMPUTADOR:8000 que aparece ao iniciar (o Windows pode pedir
para liberar o Python no firewall).
"""
import socket
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gerar_acervo  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
        '.html': 'text/html; charset=utf-8', '.webmanifest': 'application/manifest+json',
        '.svg': 'image/svg+xml', '.mid': 'audio/midi', '.midi': 'audio/midi', '.wasm': 'application/wasm',
    }

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def do_GET(self):
        if self.path.split('?')[0].endswith('/musicas/index.json'):
            gerar_acervo.gerar()
        super().do_GET()


def ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


if __name__ == '__main__':
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    n = len(gerar_acervo.gerar())
    srv = ThreadingHTTPServer(('0.0.0.0', porta), partial(Handler, directory=str(RAIZ)))
    print(f'{n} músicas no acervo')
    print(f'  neste computador: http://localhost:{porta}/')
    ip = ip_local()
    if ip:
        print(f'  no celular (mesma rede Wi-Fi): http://{ip}:{porta}/')
    print('Ctrl+C para parar.')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
