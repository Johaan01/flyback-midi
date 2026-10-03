"""Servidor do Flyback MIDI nesta máquina: o site pede, a GPU daqui transcreve, o GitHub publica.

    python tools/servidor.py                  # porta 8790
    python tools/servidor.py --sem-publicar   # transcreve mas não manda ao GitHub

A janela "Baixar músicas" do site conversa com ele: busca por nome, link de música ou de
playlist; fila; progresso; e, ao terminar cada música, commit e push para o acervo. Só
biblioteca padrão aqui — o trabalho pesado é o transcrever.py, num processo à parte por música.

Segurança: o servidor baixa, roda a GPU e publica no GitHub, então só atende quem manda a chave.
Ela é gerada na primeira vez, guardada em ~/.flyback-servidor.json e mostrada ao iniciar; cole no
site. O mesmo arquivo guarda, se houver, a chave da API do Mirelo (campo "mirelo") — ela nunca
vai para o site.

Fora de casa: um túnel do Cloudflare expõe o servidor com https —
    cloudflared tunnel --url http://localhost:8790
— e o endereço que ele mostrar vai no campo "servidor" da janela.
"""
import argparse
import json
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
import lote  # noqa: E402
import mirelo  # noqa: E402

CONFIG = Path.home() / '.flyback-servidor.json'
VERSAO = 1
TRAVA = threading.Lock()          # fila e estado do lote
TRAVA_GIT = threading.Lock()
fila = []                          # trabalhos, na ordem de chegada
cfg = {}
args = None


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def carregar_config():
    c = json.loads(CONFIG.read_text(encoding='utf-8')) if CONFIG.is_file() else {}
    if not c.get('chave'):
        c['chave'] = secrets.token_urlsafe(18)
        CONFIG.write_text(json.dumps(c, indent=1), encoding='utf-8')
    return c


# ---------------------------------------------------------------- estado do lote (o mesmo do lote.py)
def estado_ler():
    arq = SAIDA / '.lote.json'
    return json.loads(arq.read_text(encoding='utf-8')) if arq.is_file() else {}


def estado_gravar(est):
    (SAIDA / '.lote.json').write_text(json.dumps(est, ensure_ascii=False, indent=1), encoding='utf-8')


# ---------------------------------------------------------------- busca
def buscar(texto):
    """Link de playlist, link de música ou nome: devolve os vídeos para escolher."""
    t = texto.strip()
    alvo = t if re.match(r'https?://', t) else f'ytsearch10:{t}'
    rc, out, err = lote.ytdlp('--flat-playlist', '--print',
                              '%(id)s\t%(title)s\t%(channel,uploader|)s\t%(duration|0)s', alvo, timeout=180)
    if rc and not out.strip():
        raise RuntimeError((err.strip().splitlines() or ['o YouTube não respondeu'])[-1][:200])
    est = estado_ler()
    itens = []
    for linha in out.strip('\r\n').splitlines():
        partes = (linha.split('\t') + [''] * 4)[:4]
        if not partes[0]:
            continue
        try:
            dur = int(float(partes[3] or 0))
        except ValueError:
            dur = 0
        itens.append({'id': partes[0], 'titulo': partes[1], 'canal': partes[2], 'duracao': dur,
                      'ja': est.get(partes[0], {}).get('situacao') == 'feito'})
    return itens


# ---------------------------------------------------------------- trabalho
PESO = {'lendo dados': (0, 2), 'baixando': (2, 12), 'descobrindo': (12, 16), 'separando': (16, 30),
        'transcrevendo': (30, 95), 'enviando ao Mirelo': (12, 20), 'Mirelo detectando os instrumentos': (20, 25),
        'Mirelo transcrevendo': (25, 95), 'creditando': (95, 97), 'publicando': (97, 100)}


def etapa(job, nome, pct=0):
    a, b = PESO.get(nome, (job.get('total', 0), job.get('total', 0)))
    with TRAVA:
        job['etapa'], job['total'] = nome, round(a + (b - a) * max(0, min(100, pct)) / 100)


def publicar(arquivo, titulo, motor):
    """Commit só do MIDI e do crédito, e push. Outras mudanças da pasta não entram."""
    with TRAVA_GIT:
        caminhos = [str(Path('musicas') / SAIDA.name / arquivo), str(Path('musicas') / SAIDA.name / 'creditos.json')]
        g = lambda *c: subprocess.run(['git', *c], cwd=RAIZ, capture_output=True, text=True, encoding='utf-8', errors='replace')
        g('add', '--', *caminhos)
        r = g('commit', '-m', f'acervo: {titulo}, transcrita pelo {motor}', '--', *caminhos)
        if r.returncode and 'nothing' not in (r.stdout + r.stderr):
            raise RuntimeError('git commit: ' + (r.stderr or r.stdout).strip()[-200:])
        if g('push', '-q').returncode:
            g('pull', '--rebase', '--autostash', '-q')
            r = g('push', '-q')
            if r.returncode:
                raise RuntimeError('git push: ' + r.stderr.strip()[-200:])


def processar(job):
    vid, url = job['vid'], f"https://www.youtube.com/watch?v={job['vid']}"
    etapa(job, 'lendo dados')
    artista, musica, duracao = lote.metadados(url)
    with TRAVA:
        est = estado_ler()
        titulo = lote.nome_livre(SAIDA, artista, musica, vid, est)
        job['titulo'] = titulo
        est[vid] = dict(est.get(vid, {}), titulo=titulo, url=url, situacao='rodando')
        estado_gravar(est)

    audio = lote.baixar(url, vid, aviso=lambda p: etapa(job, 'baixando', p))
    if not duracao:
        try:
            import soundfile as sf
            duracao = int(sf.info(str(audio)).duration)
        except Exception:
            pass

    if job['motor'] == 'mirelo':
        midi, instrumentos = mirelo.transcrever(audio, aviso=lambda e, p: etapa(job, e, p))
        arq = SAIDA / f'{titulo}.mid'
        arq.write_bytes(midi)
        rel = {'arquivo': str(arq), 'modelo': 'Mirelo', 'instrumentos': instrumentos,
               'origem': 'MuScriptor pelo Mirelo (API), transcrição automática do áudio, sem transcritor humano; '
                         'instrumentos detectados pelo Mirelo: ' + (', '.join(instrumentos) or 'sem lista')}
    else:
        rel, ultimo = None, None
        for t in (1, 2):           # a segunda em processo novo e com a separação em blocos menores
            try:
                rel = lote.transcrever(audio, titulo, SAIDA, 'large', duracao, 10.0 if t == 1 else 5.0,
                                       aviso=lambda e, p: etapa(job, e, p))
                break
            except lote.Falha as ex:
                ultimo = ex
                log(f'   {titulo}: tentativa {t} falhou: {ex}')
        if not rel:
            with TRAVA:
                est = estado_ler()
                est[vid].update(situacao='mirelo', erro=str(ultimo), instrumentos=ultimo.instrumentos)
                estado_gravar(est)
                lote.para_o_mirelo(SAIDA, est)
            raise RuntimeError(f'a GPU não conseguiu: {ultimo}. Ficou na lista para o Mirelo.')

    etapa(job, 'creditando')
    arq = Path(rel['arquivo'])
    entrada = lote.creditar(SAIDA, arq, artista, musica, url, rel['modelo'], rel)
    with TRAVA:
        est = estado_ler()
        est[vid].update(situacao='feito', modelo=rel['modelo'], arquivo=arq.name,
                        instrumentos=rel.get('instrumentos'), aproveitamento=entrada['aproveitamento'],
                        aproveitamento6=entrada['aproveitamento6'])
        est[vid].pop('erro', None)
        estado_gravar(est)
        lote.para_o_mirelo(SAIDA, est)
        job['arquivo'] = arq.name
    if not args.sem_publicar:
        etapa(job, 'publicando')
        publicar(arq.name, titulo, 'Mirelo' if job['motor'] == 'mirelo' else 'MuScriptor large')
    audio.unlink(missing_ok=True)


def trabalhador():
    while True:
        with TRAVA:
            job = next((j for j in fila if j['situacao'] == 'aguardando'), None)
            if job:
                job['situacao'], job['inicio'] = 'rodando', time.time()
        if not job:
            time.sleep(1)
            continue
        log(f"começando: {job.get('titulo') or job['vid']} ({job['motor']})")
        try:
            processar(job)
            with TRAVA:
                job.update(situacao='pronto', etapa='pronto', total=100, fim=time.time())
            log(f"pronto: {job['titulo']}")
        except Exception as e:
            traceback.print_exc()
            with TRAVA:
                job.update(situacao='falhou', erro=str(e)[:300], fim=time.time())


# ---------------------------------------------------------------- HTTP
class Pedido(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin') or '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Chave')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        # a página publicada (https) falando com localhost precisa disto no Chrome
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Access-Control-Max-Age', '600')
        self.send_header('Vary', 'Origin')

    def _json(self, dados, codigo=200):
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(codigo)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _autorizado(self):
        if secrets.compare_digest(self.headers.get('X-Chave', ''), cfg['chave']):
            return True
        self._json({'erro': 'chave errada ou ausente'}, 401)
        return False

    def _corpo(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}') if n else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        rota = urllib.parse.urlparse(self.path)
        if rota.path == '/ping':                       # sem chave: só diz que existe
            return self._json({'flyback': True, 'versao': VERSAO})
        if not self._autorizado():
            return
        if rota.path == '/estado':
            return self._json({'versao': VERSAO, 'mirelo': bool(mirelo.chave()), 'publicar': not args.sem_publicar,
                               'gpu': GPU, 'pasta': SAIDA.name})
        if rota.path == '/fila':
            with TRAVA:
                return self._json({'fila': [{k: v for k, v in j.items()} for j in fila[-60:]]})
        if rota.path == '/arquivo':
            nome = urllib.parse.parse_qs(rota.query).get('nome', [''])[0]
            arq = (SAIDA / nome).resolve()
            if '/' in nome or '\\' in nome or arq.parent != SAIDA.resolve() or arq.suffix != '.mid' or not arq.is_file():
                return self._json({'erro': 'arquivo não encontrado'}, 404)
            corpo = arq.read_bytes()
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'audio/midi')
            self.send_header('Content-Length', str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
            return
        self._json({'erro': 'rota desconhecida'}, 404)

    def do_POST(self):
        if not self._autorizado():
            return
        rota = urllib.parse.urlparse(self.path).path
        try:
            corpo = self._corpo()
        except ValueError:
            return self._json({'erro': 'corpo não é JSON'}, 400)
        if rota == '/buscar':
            try:
                return self._json({'itens': buscar(str(corpo.get('texto', '')))})
            except Exception as e:
                return self._json({'erro': str(e)}, 502)
        if rota == '/fila':
            motor = 'mirelo' if corpo.get('motor') == 'mirelo' else 'local'
            if motor == 'mirelo' and not mirelo.chave():
                return self._json({'erro': 'este servidor não tem a chave da API do Mirelo'}, 400)
            novos = []
            with TRAVA:
                ativos = {j['vid'] for j in fila if j['situacao'] in ('aguardando', 'rodando')}
                for it in corpo.get('itens') or []:
                    vid = str(it.get('id', ''))
                    if not re.fullmatch(r'[\w-]{6,20}', vid) or vid in ativos:
                        continue
                    job = {'id': uuid.uuid4().hex[:8], 'vid': vid, 'titulo': str(it.get('titulo', ''))[:150],
                           'motor': motor, 'situacao': 'aguardando', 'etapa': 'na fila', 'total': 0}
                    fila.append(job)
                    novos.append(job['id'])
            return self._json({'novos': novos})
        self._json({'erro': 'rota desconhecida'}, 404)

    def do_DELETE(self):
        if not self._autorizado():
            return
        m = re.fullmatch(r'/fila/(\w+)', urllib.parse.urlparse(self.path).path)
        with TRAVA:
            antes = len(fila)
            if m:
                fila[:] = [j for j in fila if not (j['id'] == m.group(1) and j['situacao'] in ('aguardando', 'pronto', 'falhou'))]
        self._json({'removido': len(fila) < antes})


def main():
    global cfg, args, SAIDA, GPU
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--porta', type=int, default=8790)
    ap.add_argument('--saida', default='musicas/transcritas')
    ap.add_argument('--sem-publicar', action='store_true', help='não fazer commit e push de cada música')
    args = ap.parse_args()
    SAIDA = (RAIZ / args.saida) if not Path(args.saida).is_absolute() else Path(args.saida)
    SAIDA.mkdir(parents=True, exist_ok=True)
    cfg = carregar_config()
    try:
        import torch
        GPU = torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'sem GPU (vai pela CPU, devagar)'
    except Exception:
        GPU = 'desconhecida'
    import transcrever as T
    T.achar_no_winget('yt-dlp', 'ffmpeg', 'deno')
    threading.Thread(target=trabalhador, daemon=True).start()
    srv = ThreadingHTTPServer(('127.0.0.1', args.porta), Pedido)
    log(f'servidor do Flyback MIDI em http://localhost:{args.porta}  ·  {GPU}')
    log(f'chave (cole na janela "Baixar músicas" do site): {cfg["chave"]}')
    log('Mirelo: ' + ('chave da API configurada' if mirelo.chave() else 'sem chave da API (só a GPU daqui)'))
    log('publicação no GitHub: ' + ('desligada' if args.sem_publicar else 'ligada, uma música por commit'))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        log('encerrado')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
