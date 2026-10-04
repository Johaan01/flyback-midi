"""Confere, música a música, o que a montagem fixa deixa de fora com N flybacks.

    python tools/auditar_montagem.py musicas/transcritas
    python tools/auditar_montagem.py "musicas/transcritas/Mötley Crüe - Kickstart My Heart.mid" --flybacks 4
    python tools/auditar_montagem.py musicas/transcritas --so-problemas

O site mostra uma nota por arco, que é o objetivo, e por isso não deixa ver o que ficou para
trás: um instrumento sem flyback, a segunda voz escondida na faixa de voz, o acorde de seis
notas tocado em dois arcos. Só um player de MIDI completo mostra as notas sobrepostas. Esta
ferramenta abre cada arquivo no próprio index.html, num Chrome de verdade (Playwright), com a
montagem que o site faria sozinho, e mede para cada faixa quanto do tempo de nota dela soa de
fato em algum arco, na mesma altura. É a medida do site, não uma reimplementação dela.

Avisa quando:
- uma faixa com material de verdade (5% da música ou mais) não tem flyback;
- a melodia principal (o arco 1) fica calada em mais de 10% do que tem, contando só trechos de
  mais de 0,3 s — o fim de uma nota que a seguinte corta é resto de transcrição, não perda;
- uma faixa sobreposta (polifonia 1,4 ou mais: acorde, ou dois instrumentos numa faixa) toca
  menos da metade e há arco vazio que poderia ajudar;
- a bateria não tem arco.

Bateria não entra na conta de notas: vira estouros de tom (BATIDA), de outra altura.
"""
import argparse
import functools
import http.server
import json
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

MEDIR = """() => {
  const n = nCanais();
  const rotas = tracks.map((t, k) => canaisDe(assign[k]).filter(c => c < n));
  const porAltura = ch.slice(0, n).map(c => {
    const m = new Map();
    c.segs.forEach(s => (m.get(s.n) || m.set(s.n, []).get(s.n)).push(s));
    return m;
  });
  const lead = tracks.findIndex((t, k) => prio[k] === 3);
  const faixas = tracks.map((t, k) => {
    const fam = familia(t);
    let tempo = 0, soa = 0, falta = 0;
    if (fam !== 'bateria') t.notes.forEach(x => {
      tempo += x.t1 - x.t0;
      const iv = [];
      rotas[k].forEach(c => (porAltura[c].get(x.n) || []).forEach(s => {
        const a = Math.max(s.start, x.t0), b = Math.min(s.end, x.t1);
        if (b > a) iv.push([a, b]);
      }));
      iv.sort((p, q) => p[0] - q[0]);
      let fim = x.t0;
      iv.forEach(([a, b]) => {
        if (a - fim > .3) falta += a - fim;
        if (b > fim){ soa += b - Math.max(a, fim); fim = b; }
      });
      if (x.t1 - fim > .3) falta += x.t1 - fim;
    });
    const u = t.uniao || [];
    const ocupa = u.reduce((a, [i, f]) => a + f - i, 0);
    return { nome: t.name, familia: fam, notas: t.notes.length, polifonia: polifonia(t),
             arcos: rotas[k].map(c => c + 1), soa: tempo ? soa / tempo : null, falta: tempo ? falta / tempo : null,
             ocupa: ocupa / duration, lead: k === lead };
  });
  const arcos = ch.slice(0, n).map((c, i) => ({
    papel: PAPEIS[i], pick: c.ctl.pick,
    faixas: tracks.filter((t, k) => assign[k] >> i & 1).map(t => t.name),
    ativo: c.segs.reduce((a, s) => a + s.end - s.start, 0) / duration }));
  return { duracao: duration, faixas, arcos };
}"""


def problemas(m):
    """Lista de avisos, em português, do que a montagem deixa de fora."""
    out = []
    vazios = [i + 1 for i, a in enumerate(m['arcos']) if not a['faixas']]
    for f in m['faixas']:
        if not f['notas']:
            continue
        if not f['arcos'] and (f['familia'] == 'bateria' or f['ocupa'] >= .05):
            out.append(f'"{f["nome"]}" ({f["familia"]}) não tem flyback — {f["ocupa"] * 100:.0f}% da música')
            continue
        if f['soa'] is None or not f['arcos']:
            continue
        if f['lead'] and f['falta'] > .1:
            out.append(f'a melodia principal "{f["nome"]}" fica calada em {f["falta"] * 100:.0f}% do que tem, '
                       f'em trechos de mais de 0,3 s')
        elif f['polifonia'] >= 1.4 and f['soa'] < .5 and vazios:
            out.append(f'"{f["nome"]}" tem {f["polifonia"]:.1f} notas soando juntas e toca {f["soa"] * 100:.0f}%; '
                       f'arco vazio: {", ".join(map(str, vazios))}')
    return out


def tabela(nome, m):
    linhas = [f'\n{nome}  ({m["duracao"] // 60:.0f}:{m["duracao"] % 60:02.0f})']
    for i, a in enumerate(m['arcos']):
        linhas.append(f'  {i + 1} {a["papel"]:9s} {(" + ".join(a["faixas"]) or "—")[:44]:44s} '
                      f'{a["pick"]:4s} ativo {a["ativo"] * 100:3.0f}%')
    linhas.append('  faixa                          família    notas  juntas  arcos     toca')
    for f in m['faixas']:
        toca = '—' if f['soa'] is None else f'{f["soa"] * 100:3.0f}%'
        arcos = ','.join(map(str, f['arcos'])) or 'nenhum'
        linhas.append(f'  {f["nome"][:30]:30s} {f["familia"]:9s} {f["notas"]:6d}  {f["polifonia"]:5.2f}  '
                      f'{arcos:8s} {toca:>5s}{"  ← melodia" if f["lead"] else ""}')
    return '\n'.join(linhas)


class _Calado(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def auditar(arquivos, flybacks=6):
    """{arquivo: medida} — abre cada um no site, com a montagem que ele faria sozinho."""
    from playwright.sync_api import sync_playwright
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(_Calado, directory=str(RAIZ)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out = {}
    try:
        with sync_playwright() as p:
            nav = p.chromium.launch(channel='chrome', headless=True)
            pg = nav.new_page()
            erros = []
            pg.on('pageerror', lambda e: erros.append(str(e)))
            base = f'http://127.0.0.1:{srv.server_address[1]}/index.html'
            pg.goto(base)
            pg.evaluate('localStorage.clear()')        # a montagem padrão, não a deste navegador
            pg.goto(base)
            pg.wait_for_function("typeof openBuffer === 'function'")
            pg.select_option('#espN', str(flybacks))
            time.sleep(.3)
            for arq in arquivos:
                pg.evaluate("async b => openBuffer(new Uint8Array(b).buffer, {})", list(Path(arq).read_bytes()))
                time.sleep(.2)
                out[arq] = pg.evaluate(MEDIR)
            nav.close()
            if erros:
                raise RuntimeError('erro na página: ' + erros[0])
    finally:
        srv.shutdown()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('caminhos', nargs='+', help='arquivos .mid ou pastas')
    ap.add_argument('--flybacks', type=int, default=6, choices=range(3, 7))
    ap.add_argument('--so-problemas', action='store_true', help='mostrar só as músicas com aviso')
    ap.add_argument('--json', help='gravar as medidas num .json')
    args = ap.parse_args()
    arqs = []
    for c in map(Path, args.caminhos):
        arqs += sorted(c.rglob('*.mid')) if c.is_dir() else [c]
    medidas = auditar(arqs, args.flybacks)
    com = 0
    for arq, m in medidas.items():
        avisos = problemas(m)
        com += bool(avisos)
        if avisos or not args.so_problemas:
            print(tabela(Path(arq).name, m))
            print('\n'.join('  ! ' + a for a in avisos) or '  ok')
    print(f'\n{len(medidas)} músicas com {args.flybacks} flybacks: {len(medidas) - com} ok, {com} com aviso')
    if args.json:
        Path(args.json).write_text(json.dumps({str(k): v for k, v in medidas.items()}, ensure_ascii=False, indent=1),
                                   encoding='utf-8')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
