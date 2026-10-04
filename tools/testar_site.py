"""Abre o index.html num Chrome de verdade e exercita o player: 2 e 6 flybacks, o
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
import urllib.parse
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
        n: nCanais(), faixas: tracks.length, assign: assign.slice(), nomes: tracks.map(t => t.name),
        segs: ch.slice(0, nCanais()).map(c => c.segs.length),
        pistas: document.querySelectorAll('#lanes .lane').length,
        canais: document.querySelectorAll('#strips .strip').length,
        presets: [...document.querySelectorAll('#presets button')].map(b => b.textContent),
        tocando: playing, pos: position() })""")


def abrir(pg, base, caminho):
    pg.goto(base + '?m=' + urllib.parse.quote(caminho))
    pg.wait_for_selector('#tracks .trk', timeout=30000)
    time.sleep(.3)


def player(nav, base, telas):
    pg = nav.new_page(viewport={'width': 1920, 'height': 1080})
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.on('console', lambda m: erros.append(m.text) if m.type == 'error' else None)
    pg.goto(base)
    pg.evaluate('localStorage.clear()')

    print('dois flybacks, pelo P2')
    abrir(pg, base, 'exemplos/Korobeiniki.mid')
    e = estado(pg)
    confere(e['n'] == 2 and e['pistas'] == 2 and e['canais'] == 2, 'começa com dois flybacks, duas pistas e dois canais')
    confere(e['faixas'] == 4 and any(e['segs']), f'MIDI formato 0 separado por canal: {e["faixas"]} faixas')
    confere(len(e['presets']) == 6, 'os seis presets de dois canais')
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

    print('seis flybacks')
    abrir(pg, base, 'transcritas/Victor & Leo - Borboletas (Mirelo).mid')
    pg.select_option('#espN', '6'); time.sleep(.3)
    e = estado(pg)
    confere(e['pistas'] == 6 and e['canais'] == 6, 'seis pistas e seis canais')
    rotas = {e['nomes'][k]: [i + 1 for i in range(6) if m >> i & 1] for k, m in enumerate(e['assign'])}
    confere(rotas.get('voice', [0])[0] == 1 and rotas.get('electric_bass') == [2] and rotas.get('acoustic_guitar', [0])[0] == 3
            and rotas.get('drums') == [4] and 5 in rotas.get('synth_pad', []) + rotas.get('acoustic_piano', []),
            f'montagem fixa: 1 voz, 2 baixo, 3 violão, 4 bateria, 5 teclado ({rotas})')
    env = pg.evaluate("ch.slice(0, 6).map(c => c.ctl.env)")
    confere(env[0] == 'medio' and env[2] == 'corda' and env[3] == 'percussivo',
            f'som padrão da montagem: voz em médio, violão em corda, bateria em batida ({env})')
    ritmo = pg.evaluate("ch[3].segs.map(s => s.n)")
    confere(ritmo and set(ritmo) <= {33, 40, 45, 50, 55, 60},
            f'bateria vira estouros de bumbo, caixa e tons, sem chimbal nem prato ({sorted(set(ritmo))})')
    # o som segue o instrumento: o da guitarra vale para todas as músicas e todo arco com guitarra
    pg.select_option('#env2', 'sustentado')
    abrir(pg, base, 'transcritas/AC-DC - Thunderstruck.mid')
    r = pg.evaluate("ch.slice(0, 6).map(c => [c.som, c.ctl.env])")
    confere(all(e == 'sustentado' for f, e in r if f == 'guitarra') and r[0] == ['voz', 'medio'],
            f'o envelope da guitarra mudado numa música vale em outra, em todo arco com guitarra ({r})')
    pg.evaluate("sons.guitarra.agudo = 400; rebuild()")
    alto = pg.evaluate("Math.max(...ch[2].segs.map(s => s.f))")
    confere(alto <= 400, f'limite de agudo desce as notas de oitava até caber ({alto:.0f} Hz)')
    pg.evaluate("sons.guitarra.agudo = AGUDO_LIVRE; sons.guitarra.env = 'corda'; store.set('sons', sons); rebuild()")
    pg.select_option('#env2', 'corda')
    abrir(pg, base, 'transcritas/Victor & Leo - Borboletas (Mirelo).mid')
    pg.select_option('#espN', '4'); time.sleep(.2)
    e = estado(pg)
    confere(e['pistas'] == 4 and all(m < 16 for m in e['assign']), 'quatro flybacks: nenhuma rota além do canal 4')
    antes = e['assign'][1]
    pg.click('#tracks .trk:nth-child(2) .seg button:nth-child(5)')
    confere(estado(pg)['assign'][1] == antes | 8, 'uma faixa em dois canais')
    pg.select_option('#espN', '2'); time.sleep(.2)
    confere(all(m <= 3 for m in estado(pg)['assign']), 'dois flybacks têm configuração própria')
    pg.select_option('#espN', '4'); time.sleep(.2)
    confere(estado(pg)['assign'][1] == antes | 8, 'voltar a quatro recupera a rota manual')
    pg.click('#strips .strip:nth-child(2) .strip-h button:nth-child(2)')
    confere(pg.evaluate('!soa(1) && soa(0)'), 'silenciar um canal')
    pg.click('#strips .strip:nth-child(2) .strip-h button:nth-child(2)')
    n = pg.evaluate('(async () => (await renderWav()).numberOfChannels)()')
    confere(n == 4, f'WAV com um canal por flyback ({n})')

    print('acorde em vários flybacks')
    pg.select_option('#espN', '6')
    abrir(pg, base, 'transcritas/AC-DC - Back In Black.mid')
    r = pg.evaluate("""() => { const g = tracks.findIndex(t => /guitar/.test(t.name));
        return { canais: canaisDe(assign[g]).map(i => i + 1), picks: canaisDe(assign[g]).map(i => ch[i].ctl.pick) }; }""")
    confere(r['canais'] == [3] and r['picks'] == ['lo'],
            f'a guitarra fica no arco dela, na nota grave: arco vazio não recebe pedaço de acorde ({r})')
    abrir(pg, base, 'transcritas/Scorpions - Still Loving You.mid')
    r = pg.evaluate("""() => tracks.map((t, k) => [t.name, canaisDe(assign[k]).map(i => i + 1), canaisDe(assign[k]).map(i => ch[i].ctl.pick)])""")
    rotas = {n: (a, p) for n, a, p in r}
    dist, voz = rotas.get('distorted electric guitar'), rotas.get('voice')
    confere(dist and len(dist[0]) == 1 and dist[0][0] in (5, 6) and dist[1] == ['lo']
            and voz and voz[0][0] == 1 and len(voz[0]) == 2 and set(voz[1]) == {'div'},
            f'a segunda guitarra ganha arco próprio, na nota grave, e a segunda voz reparte com o 1 ({rotas})')
    # repartir à mão: a guitarra de Iron Man em três arcos
    abrir(pg, base, 'transcritas/Black Sabbath - Iron Man.mid')
    r = pg.evaluate("""() => { const g = tracks.findIndex(t => /guitar/.test(t.name)), v = prio.indexOf(3);
        assign[g] = (1 << 2) | (1 << 4) | (1 << 5); [2, 4, 5].forEach(i => { ch[i].ctl.pick = 'div'; }); rebuild();
        const teto = avgPitch(tracks[v]) - 5;
        const acima = [4, 5].flatMap(i => ch[i].segs.filter(s => s.n > teto)).length;
        let igual = 0;
        [[2, 4], [2, 5], [4, 5]].forEach(([i, j]) => ch[i].segs.forEach(a => ch[j].segs.forEach(b => {
          if (a.n === b.n){ const x = Math.max(a.start, b.start), y = Math.min(a.end, b.end); if (y > x) igual += y - x; } })));
        return { notas: [2, 4, 5].map(i => ch[i].segs.length), acima, igual: +igual.toFixed(2) }; }""")
    confere(all(r['notas']) and not r['acima'] and r['igual'] == 0,
            f'repartir à mão: cada arco com notas suas, nada acima do teto nos extras, nenhuma nota repetida ({r})')
    # o baixo toca a mais grave que soa, mesmo com acorde de synth na faixa dele
    abrir(pg, base, 'transcritas/Rick Astley - Never Gonna Give You Up.mid')
    r = pg.evaluate("""() => { const b = tracks.findIndex(t => familia(t) === 'baixo'); let erros = 0, total = 0;
        ch[1].segs.forEach(s => { const m = (s.start + s.end) / 2;
          const soando = tracks[b].notes.filter(x => x.t0 <= m && x.t1 > m).map(x => x.n);
          if (soando.length){ total++; if (s.n !== Math.min(...soando)) erros++; } });
        return { total, erros, juntas: +polifonia(tracks[b]).toFixed(2) }; }""")
    confere(r['total'] > 100 and r['erros'] <= r['total'] * .02,
            f'o arco do baixo toca a nota mais grave que soa na faixa ({r})')
    # a oitava é da música
    abrir(pg, base, "transcritas/Guns N' Roses - Sweet Child O' Mine.mid")
    pg.select_option('#oct0', '1')
    abrir(pg, base, 'transcritas/AC-DC - Back In Black.mid')
    outra = pg.evaluate('ch[0].ctl.oct')
    abrir(pg, base, "transcritas/Guns N' Roses - Sweet Child O' Mine.mid")
    volta = pg.evaluate('ch[0].ctl.oct')
    confere(outra == 0 and volta == 1, f'a oitava mudada numa música fica nela e não passa para outra ({outra}, {volta})')
    abrir(pg, base, 'transcritas/Victor & Leo - Borboletas.mid')
    r = pg.evaluate("""() => { const v = prio.indexOf(3), arcos = canaisDe(assign[v]);
        const media = i => { const s = ch[i].segs; return s.reduce((a, x) => a + x.n, 0) / s.length; };
        return { nome: tracks[v].name, arcos: arcos.map(i => i + 1), alturas: arcos.map(i => Math.round(media(i))) }; }""")
    confere(r['nome'] == 'voice' and len(r['arcos']) == 2 and r['arcos'][0] == 1 and r['alturas'][0] > r['alturas'][1],
            f'a segunda voz da dupla vai para outro arco, e a de cima fica no 1 ({r})')
    a = r['arcos'][1] - 1
    r = pg.evaluate(f"[ch[{a}].som, ch[{a}].ctl.env, ch[0].ctl.env, document.querySelectorAll('#strips .strip .nome')[{a}].textContent]")
    confere(r[0] == 'voz' and r[1] == r[2] and 'som de voz' in r[3],
            f'o arco da segunda voz soa como voz, e o mixer diz isso ({r})')
    abrir(pg, base, 'transcritas/Victor & Leo - Borboletas (Mirelo).mid')
    pg.click('#presets button:nth-child(1)')      # Montagem fixa, por cima do ajuste salvo antes
    r = pg.evaluate("() => tracks.filter((t, k) => assign[k] >> 4 & 1).map(t => [t.name, prio[tracks.indexOf(t)]])")
    dono = max(r, key=lambda x: x[1])[0] if r else None
    confere(dono == 'acoustic_piano', f'no teclado manda a faixa com mais ataques, o piano, não o pad ({r})')

    print('origem')
    pg.click('#libA button[data-vista=transcritas]')
    ia = pg.eval_on_selector_all('#libList button .tag', 'x => x.map(e => e.textContent)')
    confere(ia and all(' · MuScriptor' in t or ' · Mirelo' in t for t in ia),
            f'a vista "transcritas" mostra só as feitas por IA ({sum("MuScriptor" in t for t in ia)} MuScriptor, '
            f'{sum("Mirelo" in t for t in ia)} Mirelo)')
    artistas = pg.eval_on_selector_all('#libF option', 'x => x.map(o => o.textContent)')
    confere(any('AC/DC' in a for a in artistas), f'seletor de artista nas transcritas ({len(artistas) - 1} artistas)')
    pg.click('#libFiltros'); pg.check('#fVoz')
    voz = pg.eval_on_selector_all('#libList button .tag', 'x => x.map(e => e.textContent)')
    confere(voz and all('vocal' in t for t in voz), f'filtro "com voz" no menu ({len(voz)})')
    pg.uncheck('#fVoz'); pg.keyboard.press('Escape')
    confere(pg.is_hidden('#libPop'), 'o menu de filtros fecha com Esc')
    pg.click('#libA button[data-vista=antigas]')
    antigas = pg.eval_on_selector_all('#libList button .tag', 'x => x.map(e => e.textContent)')
    confere(antigas and all(' · nativo' in t for t in antigas), f'as antigas aparecem como MIDI nativo ({len(antigas)})')
    pg.click('#libA button[data-vista=""]')

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
        abrir(pg, base, 'transcritas/Victor & Leo - Borboletas (Mirelo).mid')
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
    pg.evaluate("localStorage.clear(); localStorage.setItem('flyback:esp', JSON.stringify({n: 6}))")
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
    pg.select_option('#espN', '2')
    l = linhas()
    confere('P 1 21' in l and 'P 2 -1' in l, 'com dois flybacks o mapa vai com os outros quatro canais liberados')
    pg.click('#play'); time.sleep(.6); pg.click('#play')
    canais = {int(x.split()[1]) for x in linhas() if x.startswith('N ')}
    confere(canais and canais <= {0, 1}, f'com dois flybacks a serial continua, só nos canais 0 e 1 ({sorted(canais)})')
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
