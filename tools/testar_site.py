"""Abre o index.html num Chrome de verdade e exercita o player: os dois modos de saída, o
roteamento, a separação do WAV e a serial com uma porta simulada.

    python tools/testar_site.py            # roda tudo e diz o que falhou
    python tools/testar_site.py --telas    # e guarda capturas de tela em quatro tamanhos

Opcional, como o transcrever.py: precisa de `pip install playwright` e de um Chrome ou Edge
instalado (não baixa navegador; usa o do sistema). Nada no site depende disto.

Existe porque a página é um arquivo único de JavaScript escrito à mão, sem build e sem
tipagem: um erro de digitação num caminho pouco usado só aparece quando alguém clica ali.
Rode antes de publicar qualquer mudança no index.html.
"""
import argparse
import functools
import http.server
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
falhas = []

# Porta Web Serial falsa: guarda o texto que a página escreve, para conferir o protocolo
# sem ESP32 nenhum ligado.
SERIAL_FALSA = """
(() => {
  const dec = new TextDecoder();
  window.__serial = { bytes: '', aberta: null, fechada: false };
  const porta = {
    async open(o){ window.__serial.aberta = o; },
    async close(){ window.__serial.fechada = true; },
    writable: { getWriter(){ return {
      async write(b){ window.__serial.bytes += dec.decode(b); }, releaseLock(){} }; } }
  };
  const alvo = new EventTarget();
  alvo.requestPort = async () => porta;
  Object.defineProperty(navigator, 'serial', { value: alvo });
})();
"""


def confere(cond, msg):
    print(('  ok     ' if cond else '  FALHA  ') + msg)
    if not cond:
        falhas.append(msg)


def servir():
    """Servidor HTTP numa porta livre, em segundo plano, na raiz do repositório."""
    class Calado(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Calado, directory=str(RAIZ)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}/'


def estado(pg):
    return pg.evaluate("""() => ({
        modo, n: nCanais(), faixas: tracks.length, assign: assign.slice(), nomes: tracks.map(t => t.name),
        segs: ch.slice(0, nCanais()).map(c => c.segs.length),
        pistas: document.querySelectorAll('#lanes .lane').length,
        canais: document.querySelectorAll('#strips .strip').length,
        presets: [...document.querySelectorAll('#presets button')].map(b => b.textContent),
        tocando: playing, pos: position() })""")


def abrir(pg, base, caminho):
    pg.goto(base + '?m=' + caminho)
    pg.wait_for_selector('#tracks .trk', timeout=30000)
    time.sleep(.3)


def player(nav, base, telas):
    pg = nav.new_page(viewport={'width': 1920, 'height': 1080})
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.on('console', lambda m: erros.append(m.text) if m.type == 'error' else None)
    pg.goto(base)
    pg.evaluate('localStorage.clear()')

    print('estéreo')
    abrir(pg, base, 'exemplos/Korobeiniki.mid')
    e = estado(pg)
    confere(e['modo'] == 'estereo' and e['pistas'] == 2 and e['canais'] == 2, 'abre no estéreo, duas pistas e dois canais')
    confere(e['faixas'] == 4 and any(e['segs']), f'MIDI formato 0 separado por canal: {e["faixas"]} faixas')
    confere(len(e['presets']) == 6, 'os seis presets do estéreo')
    pg.click('#play'); time.sleep(1.5)
    e = estado(pg)
    confere(e['tocando'] and e['pos'] > 1, f'toca ({e["pos"]:.1f} s)')
    confere(any(t != '—' for t in pg.eval_on_selector_all('#lanes .nota', 'x => x.map(e => e.textContent)')), 'pista mostra a nota')
    pg.keyboard.press('Space'); time.sleep(.2)
    confere(not estado(pg)['tocando'], 'espaço pausa')
    r = pg.evaluate("""async () => {
        assign = assign.map(() => 0); assign[0] = 1; rebuild();
        const b = await renderWav(), pico = c => b.getChannelData(c).reduce((m, v) => Math.max(m, Math.abs(v)), 0);
        return [b.numberOfChannels, pico(0), pico(1)]; }""")
    confere(r[0] == 2 and r[1] > .1 and r[2] == 0, f'WAV estéreo com separação dura: o lado sem faixa sai zero ({r})')

    print('ESP32')
    abrir(pg, base, 'transcritas/Borboletas.mid')
    pg.click('#modo button[data-modo=esp]'); time.sleep(.3)
    e = estado(pg)
    confere(e['pistas'] == 6 and e['canais'] == 6, 'seis pistas e seis canais')
    rotas = {e['nomes'][k]: [i + 1 for i in range(6) if m >> i & 1] for k, m in enumerate(e['assign'])}
    confere(rotas.get('voice') == [1] and rotas.get('electric_bass') == [2] and rotas.get('drums') == [],
            f'um por flyback: voz no 1, baixo no 2, bateria fora ({rotas})')
    pg.select_option('#espN', '4'); time.sleep(.2)
    e = estado(pg)
    confere(e['pistas'] == 4 and all(m < 16 for m in e['assign']), 'quatro flybacks: nenhuma rota além do canal 4')
    antes = e['assign'][1]
    pg.click('#tracks .trk:nth-child(2) .seg button:nth-child(5)')
    confere(estado(pg)['assign'][1] == antes | 8, 'uma faixa em dois canais')
    pg.click('#modo button[data-modo=estereo]'); time.sleep(.2)
    confere(all(m <= 3 for m in estado(pg)['assign']), 'estéreo tem configuração própria')
    pg.click('#modo button[data-modo=esp]'); time.sleep(.2)
    confere(estado(pg)['assign'][1] == antes | 8, 'ESP recupera a rota manual')
    pg.click('#strips .strip:nth-child(2) .strip-h button:nth-child(2)')
    confere(pg.evaluate('!soa(1) && soa(0)'), 'silenciar um canal')
    pg.click('#strips .strip:nth-child(2) .strip-h button:nth-child(2)')
    n = pg.evaluate('(async () => (await renderWav()).numberOfChannels)()')
    confere(n == 4, f'WAV com um canal por flyback ({n})')

    print('outros arquivos')
    gp = pg.evaluate("lib.filter(it => it.tipo === 'GP').map(it => it.arquivo)")
    if gp:
        try:
            abrir(pg, base, gp[0])
            confere(estado(pg)['faixas'] > 0, 'Guitar Pro abre: ' + gp[0])
        except Exception:
            print('  (Guitar Pro não abriu: o leitor vem de CDN e precisa de internet)')
    banda = sorted((RAIZ / 'musicas' / 'bandas' / 'AC-DC').glob('*.mid'))
    if banda:
        abrir(pg, base, 'bandas/AC-DC/' + banda[0].name)
        confere(estado(pg)['faixas'] >= 6, f'arranjo de banda: {banda[0].name}')

    if telas:
        destino = Path(tempfile.gettempdir()) / 'flyback-telas'
        destino.mkdir(exist_ok=True)
        abrir(pg, base, 'transcritas/Borboletas.mid')
        for w, h in [(1920, 1080), (1366, 768), (1280, 720), (900, 1000)]:
            pg.set_viewport_size({'width': w, 'height': h}); time.sleep(.3)
            larg = pg.evaluate('document.documentElement.scrollWidth')
            confere(larg <= w, f'{w}x{h} sem rolagem horizontal')
            pg.screenshot(path=str(destino / f'{w}x{h}.png'), full_page=w < 1100)
        print(f'  capturas em {destino}')
    confere(not erros, 'nenhum erro no console' + ('' if not erros else ': ' + '; '.join(erros[:3])))
    pg.close()


def serial(nav, base):
    print('serial, com porta simulada')
    pg = nav.new_page(viewport={'width': 1600, 'height': 1000})
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.add_init_script(SERIAL_FALSA)
    pg.goto(base)
    pg.evaluate("localStorage.clear(); localStorage.setItem('flyback:modo', JSON.stringify('esp'))")
    abrir(pg, base, 'exemplos/Korobeiniki.mid')
    linhas = lambda: pg.evaluate('window.__serial.bytes').splitlines()
    confere(pg.is_disabled('#pinos button'), '"testar" desabilitado antes de conectar')
    pg.click('#serGo'); time.sleep(.2)
    confere(linhas()[:7] == ['X', 'P 0 4', 'P 1 5', 'P 2 6', 'P 3 7', 'P 4 15', 'P 5 16'], 'ao conectar: X e os seis pinos')
    pg.click('#pinos .pino:nth-child(3) button')
    confere(linhas()[-3:] == ['R', 'N 2 0 440.00', 'F 2 600'], 'testar o canal 3')
    pg.select_option('#pinos .pino:nth-child(2) select', '21')
    confere('P 1 21' in linhas()[-6:], 'trocar o pino reenvia o mapa')
    pg.evaluate('window.__serial.bytes = ""')
    pg.click('#play'); time.sleep(1.2); pg.click('#play'); time.sleep(.2)
    l = linhas()
    t = [int(x.split()[2]) for x in l if x.startswith('N ')]
    confere(l[0] == 'R' and l[-1] == 'X' and len(t) > 5 and t == sorted(t), f'tocar: R, {len(t)} notas em ordem, X')
    pg.evaluate('window.__serial.bytes = ""')
    pg.click('#modo button[data-modo=estereo]')
    pg.click('#play'); time.sleep(.4); pg.click('#play')
    confere(linhas() == ['X'], 'no estéreo nada vai pela serial além do X de saída')
    pg.click('#modo button[data-modo=esp]')
    pg.click('#serGo'); time.sleep(.2)
    confere(pg.evaluate('window.__serial.fechada'), 'desconectar fecha a porta')
    confere(not erros, 'nenhum erro na página')
    pg.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--telas', action='store_true', help='guardar capturas de tela')
    args = ap.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit('precisa do playwright:  pip install playwright')
    if not (RAIZ / 'musicas' / 'index.json').is_file():
        sys.exit('falta musicas/index.json — rode antes:  python tools/gerar_acervo.py')
    srv, base = servir()
    try:
        with sync_playwright() as p:
            nav = None
            for canal in ('chrome', 'msedge'):
                try:
                    nav = p.chromium.launch(channel=canal, headless=True, args=['--autoplay-policy=no-user-gesture-required'])
                    break
                except Exception:
                    continue
            if not nav:
                sys.exit('não achei Chrome nem Edge instalados')
            player(nav, base, args.telas)
            serial(nav, base)
            nav.close()
    finally:
        srv.shutdown()
    print('\n' + ('tudo certo' if not falhas else f'{len(falhas)} falha(s):\n  ' + '\n  '.join(falhas)))
    sys.exit(1 if falhas else 0)


if __name__ == '__main__':
    if os.name == 'nt':
        sys.stdout.reconfigure(encoding='utf-8')
    main()
