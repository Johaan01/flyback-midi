"""Transcreve uma playlist inteira do YouTube, sozinho, e deixa cada música creditada no acervo.

    python tools/lote.py "https://www.youtube.com/playlist?list=..."
    python tools/lote.py --lista links.txt              # um endereço por linha
    python tools/lote.py --situacao                     # o que já foi, o que falhou, o que falta
    python tools/lote.py URL --listar                   # só os vídeos, para escrever as listas
    python tools/lote.py URL --instrumentos-por listas.json

Feito para ficar rodando sem ninguém olhando. Por música:

1. baixa o áudio (yt-dlp) para um cache temporário, que só some depois do MIDI pronto;
2. roda o transcrever.py num processo à parte, com o `large` e a lista de instrumentos da música
   (`--instrumentos-por`, um .json {id do vídeo: "voice,electric_bass,..."}) ou, sem ela, a
   detecção automática. A lista certa é o que mais pesa no resultado: é ela que o MuScriptor
   recebe como condicionamento, e a automática erra o "resto" (em BLOODY STREAM viu órgão no
   lugar da guitarra). Kickstart My Heart com voz, guitarra distorcida, baixo e bateria saiu
   perto do Mirelo. Processo à parte de propósito: depois de um erro de CUDA o estado do processo não é confiável, e uma
   música ruim não pode contaminar as seguintes;
3. se o `large` falhar, tenta de novo de outro jeito: processo novo e a separação em blocos
   de 5 s em vez de 10, que é onde a placa aperta. Não cai para o `medium` — o dono do projeto
   prefere o resultado bom a um resultado qualquer. Se falhar de novo, a música vai para
   `para-o-mirelo.md` na pasta de saída, com o endereço e os instrumentos detectados, para
   rodar à mão no Mirelo marcando aqueles instrumentos; e o lote segue;
4. mede o aproveitamento em 2 e em 6 flybacks e grava o crédito no creditos.json da pasta:
   artista e título do YouTube, o endereço, o modelo e os instrumentos;
5. confere a montagem de 6 flybacks no próprio site (auditar_montagem.py): instrumento sem
   arco, melodia calada em trecho longo, acorde preso num arco com arco vazio ao lado. Os
   avisos vão para o log e para o `.lote.json` — é o que olhar antes de publicar, em vez de
   abrir cada MIDI num editor para ver as notas sobrepostas que o site não mostra.

O estado fica em `.lote.json` na pasta de saída e é gravado depois de cada música: interromper
e rodar de novo continua de onde parou, e o que já foi não é refeito. O que falhou também não,
a menos que se peça `--refazer-falhas`.

Baixar do YouTube contraria os termos de uso do serviço; quem roda responde pelo uso. O acervo
é para estudo e demonstração, sem fins lucrativos — ver USO-EDUCACIONAL.md.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(AQUI))
from curar_acervo import ler_midi, aproveitamento, aproveitamento_n, achar_lead, veredito_lead  # noqa: E402

CACHE = Path(tempfile.gettempdir()) / 'flyback-lote'
# título do YouTube traz enfeite que não é nome de música
RUIDO = re.compile(r'\s*[\(\[][^)\]]*\b(official|oficial|video|vídeo|clipe|clip|lyric|letra|audio|áudio|'
                   r'hd|hq|4k|remaster\w*|visualizer|mv)\b[^)\]]*[\)\]]', re.I)


def log(*a):
    print(datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def ytdlp(*args, timeout=600):
    r = subprocess.run(['yt-dlp', '--no-warnings', *args], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def videos_de(endereco):
    """[(id, título)] de uma playlist, ou do vídeo avulso."""
    rc, out, err = ytdlp('--flat-playlist', '--print', '%(id)s\t%(title)s', endereco)
    if rc:
        raise RuntimeError(err.strip().splitlines()[-1] if err.strip() else f'yt-dlp saiu com {rc}')
    return [tuple(linha.split('\t', 1)) for linha in out.splitlines() if '\t' in linha]


def metadados(url):
    """Artista e título limpos, e a duração. O YouTube Music preenche artist/track; vídeo comum
    só tem o título do envio e o canal, e aí vale o padrão "Artista - Título" do título."""
    rc, out, _ = ytdlp('--no-playlist', '--skip-download', '--print',
                       '%(artist|)s\t%(track|)s\t%(title|)s\t%(uploader|)s\t%(duration|0)s', url)
    artista = musica = ''
    duracao = 0
    if rc == 0 and out.strip():
        # strip só de quebra de linha: campo vazio no começo é tabulação, e um strip() comum a
        # comia, escorregando tudo uma posição (o artista virava o título)
        linha = [l for l in out.strip('\r\n').splitlines() if l.strip()][-1]
        artista, musica, titulo, canal, dur = (linha.split('\t') + [''] * 5)[:5]
        duracao = int(float(dur or 0))
        titulo = RUIDO.sub('', titulo).strip()
        if not musica:
            if ' - ' in titulo:
                a, musica = titulo.split(' - ', 1)
                artista = artista or a
            else:
                musica = titulo
        if not artista:
            artista = re.sub(r'\s*-\s*Topic$|VEVO$|\s+Official$', '', canal or '', flags=re.I).strip()
        artista = artista.split(',')[0].strip()
    musica = RUIDO.sub('', musica).strip()
    # título que repete o artista no fim ("Livin' On A Prayer - Bon Jovi") perde a repetição
    if artista and musica.lower().endswith(' - ' + artista.lower()):
        musica = musica[:-len(artista) - 3].strip()
    return artista or 'artista não identificado', musica or 'sem título', duracao


def baixar(url, vid, aviso=None):
    """Áudio em wav no cache. `aviso(pct)`, se vier, recebe o andamento do download."""
    CACHE.mkdir(exist_ok=True)
    pronto = sorted(CACHE.glob(f'{vid}.wav'))
    if pronto:
        return pronto[0]
    cmd = ['yt-dlp', '--no-warnings', '--newline', '--no-playlist', '-x', '--audio-format', 'wav',
           '-o', str(CACHE / f'{vid}.%(ext)s'), url]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8', errors='replace')
    ultima = ''
    for linha in proc.stdout:
        ultima = linha.strip() or ultima
        m = re.search(r'\[download\]\s+([\d.]+)%', linha)
        if m and aviso:
            aviso(float(m.group(1)))
    proc.wait(timeout=1800)
    achado = sorted(CACHE.glob(f'{vid}.wav'))
    if proc.returncode or not achado:
        raise RuntimeError(ultima[:300] or f'yt-dlp saiu com {proc.returncode}')
    return achado[0]


class Falha(RuntimeError):
    """Transcrição que não terminou, com os instrumentos que chegaram a ser detectados."""
    def __init__(self, motivo, instrumentos=None):
        super().__init__(motivo)
        self.instrumentos = instrumentos or []


def transcrever(audio, titulo, saida, modelo, duracao, trecho=10.0, aviso=None, instrumentos='auto',
                orientacao=1.0):
    """Roda o transcrever.py à parte. Devolve o relatório, ou levanta Falha com o motivo.

    `aviso(etapa, pct)`, se vier, recebe o andamento: a separação ("separando… 40%") e a
    transcrição ("transcrevendo… 70%") que o transcrever.py escreve linha a linha."""
    rel = CACHE / f'{audio.stem}.{modelo}.json'
    rel.unlink(missing_ok=True)
    # o large leva ~3,5 vezes a duração da música numa RTX 2060, com a separação junto; folga
    # larga, só para não deixar uma música travada segurar o lote inteiro
    limite = max(1800, 8 * (duracao or 300))
    cmd = [sys.executable, str(AQUI / 'transcrever.py'), str(audio), '--titulo', titulo,
           '--saida', str(saida), '--modelo', modelo, '--instrumentos', instrumentos, '--relatorio', str(rel),
           '--orientacao', str(orientacao),
           '--trecho', str(trecho)]
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8', errors='replace', env=env)
    linhas, inicio = [], time.time()
    for linha in proc.stdout:
        linhas.append(linha)
        if time.time() - inicio > limite:
            proc.kill()
            raise Falha(f'passou de {limite // 60} min', _instrumentos(''.join(linhas)))
        m = re.search(r'(descobrindo|separando|transcrevendo)\D*(\d+)?%?', linha)
        if m and aviso:
            aviso(m.group(1), int(m.group(2)) if m.group(2) else 0)
    proc.wait()
    texto = ''.join(linhas)
    if proc.returncode or not rel.is_file():
        fim = [l for l in texto.splitlines() if l.strip() and '[muscriptor]' not in l]
        raise Falha((fim[-1] if fim else f'saiu com {proc.returncode}')[:300], _instrumentos(texto))
    return json.loads(rel.read_text(encoding='utf-8'))


def _instrumentos(texto):
    """A lista que o transcrever.py anunciou antes de falhar, se chegou a anunciar."""
    for linha in reversed((texto or '').splitlines()):
        if linha.strip().startswith('instrumentos:'):
            return [x.strip() for x in linha.split(':', 1)[1].split(',') if x.strip()]
    return []


def para_o_mirelo(saida, estado):
    """Reescreve a lista das músicas que o large não conseguiu, para rodar à mão no Mirelo."""
    pendentes = [v for v in estado.values() if v.get('situacao') == 'mirelo']
    arq = saida / 'para-o-mirelo.md'
    if not pendentes:
        arq.unlink(missing_ok=True)
        return
    linhas = ['# Para rodar no Mirelo', '',
              'O MuScriptor `large` não conseguiu transcrever estas músicas aqui, nem na segunda',
              'tentativa. No Mirelo, marque os instrumentos da coluna do meio: são os que o',
              'detector ouviu, e com eles a voz sai na faixa dela. Depois envie o MIDI para esta',
              'pasta com o mesmo nome.', '',
              '| Música | Instrumentos para marcar | Por que falhou |', '|---|---|---|']
    for v in pendentes:
        insts = ', '.join(v.get('instrumentos') or []) or '(não chegou a detectar)'
        linhas.append(f'| [{v["titulo"]}]({v["url"]}) | {insts} | {v.get("erro", "")[:120]} |')
    arq.write_text('\n'.join(linhas) + '\n', encoding='utf-8')


UA = 'flyback-midi/1.0 (https://github.com/Johaan01/flyback-midi)'
# gêneros do MusicBrainz agrupados em poucos nomes: o filtro do site tem de ser curto
GENEROS = [('metal', 'Metal'), ('punk', 'Punk'), ('rock', 'Rock'), ('sertanejo', 'Sertanejo'),
           ('gaúcha', 'Gaúcha'), ('gaucha', 'Gaúcha'), ('nativis', 'Gaúcha'), ('samba', 'Samba'),
           ('mpb', 'MPB'), ('forró', 'Forró'), ('anime', 'Anime'), ('j-pop', 'J-pop'), ('j-rock', 'Rock'),
           ('pop', 'Pop'), ('country', 'Country'), ('folk', 'Folk'), ('blues', 'Blues'), ('jazz', 'Jazz'),
           ('electronic', 'Eletrônica'), ('synth', 'Eletrônica'), ('disco', 'Disco'), ('funk', 'Funk'),
           ('soul', 'Soul'), ('r&b', 'Soul'), ('hip hop', 'Hip-hop'), ('rap', 'Hip-hop'),
           ('reggae', 'Reggae'), ('classical', 'Clássica'), ('soundtrack', 'Trilha sonora')]


def _mb(caminho):
    req = urllib.request.Request('https://musicbrainz.org/ws/2/' + caminho, headers={'User-Agent': UA})
    for tentativa in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                dados = json.load(r)
            break
        except urllib.error.HTTPError as e:
            # 503 é o limite de taxa, mesmo respeitando uma por segundo: AC/DC, Black Sabbath,
            # KISS e Scorpions ficaram sem gênero na primeira rodada por isso
            if e.code != 503 or tentativa == 3:
                raise
            time.sleep(2 + 3 * tentativa)
    time.sleep(1.1)                    # o MusicBrainz pede no máximo uma consulta por segundo
    return dados


def artista_mb(nome, musica=None):
    """(nome como o MusicBrainz escreve, gênero agrupado) — ou (None, None) se não achar com
    segurança. O nome canônico corrige o que vem do YouTube ("BAITACA" vira "Baitaca"); o gênero
    é o mais votado do artista, agrupado em GENEROS.

    Com a música junto, o artista sai da gravação que casa com os dois: nome sozinho é ambíguo —
    "Coda" achava um produtor de eletrônica, não o cantor de BLOODY STREAM."""
    dobra = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
    try:
        a = None
        if musica:
            r = _mb('recording/?fmt=json&limit=3&query='
                    + urllib.parse.quote(f'recording:"{musica}" AND artist:"{nome}"'))
            for rec in r.get('recordings') or []:
                cand = (rec.get('artist-credit') or [{}])[0].get('artist')
                # a gravação tem de ser do mesmo artista: "Do Fundo da Grota" também existe por
                # outra dupla, e casava com ela
                if cand and int(rec.get('score', 0)) >= 90 and dobra(cand.get('name', '')) == dobra(nome):
                    a = cand
                    break
        if not a:
            r = _mb('artist/?fmt=json&limit=1&query=' + urllib.parse.quote(f'artist:"{nome}"'))
            a = (r.get('artists') or [None])[0]
            # e o nome tem de ser o mesmo: "Movie Themes" ou "Nintendo" não são artista do
            # MusicBrainz, e a busca devolveria alguém parecido com nota alta
            if not a or int(a.get('score', 0)) < 90 or dobra(a.get('name', '')) != dobra(nome):
                return None, None
        info = _mb(f'artist/{a["id"]}?inc=genres+tags&fmt=json')
        # gêneros curados primeiro; as tags dos usuários cobrem artista menos conhecido
        g = (sorted(info.get('genres') or [], key=lambda x: -x.get('count', 0))
             + sorted(info.get('tags') or [], key=lambda x: -x.get('count', 0)))
        estilo = None
        for gen in g:
            estilo = next((rot for chave, rot in GENEROS if chave in gen['name'].lower()), None)
            if estilo:
                break
        return a.get('name') or None, estilo
    except Exception:
        return None, None


def creditar(saida, arq, artista, musica, url, modelo, rel):
    faixas = ler_midi(arq.read_bytes())
    fins = [t1 for f in faixas for _, t1, _ in f.notas]
    dur = (max(fins) if fins else 0) + .3
    medida, nota = achar_lead(faixas, dur)      # a mesma detecção de canto do site e do acervo
    vocal = veredito_lead(nota) + (f' · faixa "{medida["nome"]}"' if medida and nota >= 3.8 else '')
    insts = ', '.join(rel.get('instrumentos') or []) or 'sem lista'
    canonico, estilo = artista_mb(artista, musica)
    artista = canonico or artista
    origem = rel.get('origem') or (f'MuScriptor {modelo} (Kyutai/Mirelo) rodado localmente, transcrição automática do '
                                   f'áudio, sem transcritor humano; instrumentos detectados pelo PANNs: {insts}')
    entrada = {
        'autor': artista, 'artista': artista,
        'licenca': 'obra protegida — uso educacional sem fins lucrativos',
        'credito': f'interpretação de {artista}; "{musica}"',
        'transcricao': origem,
        'fonte': url,
        'vocal': vocal,
        'aproveitamento': round(aproveitamento(faixas, dur) * 100),
        'aproveitamento6': round(aproveitamento_n(faixas, dur, 6) * 100),
        **({'estilo': estilo} if estilo else {}),
    }
    c = saida / 'creditos.json'
    dados = json.loads(c.read_text(encoding='utf-8')) if c.is_file() else {}
    dados[arq.name] = entrada
    c.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return entrada


def auditar(arq):
    """O que a montagem de 6 flybacks deixa de fora nesta música, pelo próprio site. Sem o
    Playwright, a conferência fica para depois (tools/auditar_montagem.py) e o lote segue."""
    try:
        import auditar_montagem as A
        return A.problemas(A.auditar([arq])[arq])
    except Exception as ex:
        return [f'auditoria não rodou: {str(ex)[:120]}']


def conferir_voz(audio, arq):
    """(% do canto da gravação com nota na faixa de voz, aviso ou None), num processo à parte
    como a transcrição: separa o canto de novo (cerca de 1 min) e compara (conferir_voz.py)."""
    import conferir_voz as C
    with tempfile.TemporaryDirectory() as d:
        j = Path(d) / 'voz.json'
        r = subprocess.run([sys.executable, str(AQUI / 'conferir_voz.py'), str(audio), str(arq), '--json', str(j)],
                           capture_output=True, text=True, encoding='utf-8', errors='replace',
                           env=dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1'))
        if not j.is_file():
            return None, f'conferência de voz não rodou: {(r.stdout + r.stderr).strip()[-160:]}'
        v = next(iter(json.loads(j.read_text(encoding='utf-8')).values()))
    if v['cobre'] >= C.LIMITE:
        return v['cobre'], None
    onde = ', '.join(f'{int(a // 60)}:{int(a % 60):02d}' for a, _ in v['trechos'][:6])
    return v['cobre'], (f'a faixa de voz cobre só {v["cobre"]}% do canto da gravação'
                        + (f'; sem nota a partir de {onde}' if onde else ''))


def nome_livre(saida, artista, musica, vid, estado):
    """'Artista - Música', e com o id do vídeo se outro vídeo já usou o mesmo nome."""
    # barra vira hífen (AC/DC -> AC-DC, como na pasta de bandas; "War Pigs / Luke's Wall"), o
    # resto que o Windows não aceita some, e espaço repetido vira um só
    limpo = lambda s: re.sub(r'\s+', ' ', ''.join(c for c in s.replace('/', '-') if c not in '\\:*?"<>|')).strip()
    base = limpo(f'{artista} - {musica}')[:120]
    dono = next((k for k, v in estado.items() if v.get('titulo') == base and k != vid), None)
    return base if not dono else f'{base} ({vid})'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('endereco', nargs='?', help='playlist ou vídeo do YouTube')
    ap.add_argument('--lista', help='arquivo de texto com um endereço por linha')
    ap.add_argument('--saida', default='musicas/transcritas', help='pasta do acervo (padrão: musicas/transcritas)')
    ap.add_argument('--modelo', default='large', choices=('large', 'medium', 'small'),
                    help='modelo do MuScriptor (padrão large)')
    ap.add_argument('--tentativas', type=int, default=2,
                    help='tentativas antes de mandar a música para a lista do Mirelo (padrão 2; da '
                         'segunda em diante a separação usa blocos de 5 s)')
    ap.add_argument('--limite', type=int, default=0, help='parar depois de N músicas novas')
    ap.add_argument('--refazer-falhas', action='store_true',
                    help='tentar de novo o que foi para a lista do Mirelo ou ficou sem áudio')
    ap.add_argument('--situacao', action='store_true', help='só mostrar o estado do lote')
    ap.add_argument('--listar', action='store_true',
                    help='só listar os vídeos (id e título), para escrever a lista de instrumentos')
    ap.add_argument('--instrumentos-por', metavar='ARQ',
                    help='.json {id do vídeo: "voice,electric_bass,..."}: a lista de cada música, no lugar '
                         'da detecção automática. Quem não estiver nele usa a automática')
    ap.add_argument('--orientacao-com-lista', type=float, default=2.0, metavar='N',
                    help='orientação (cfg_coef) quando a música tem lista própria; com a automática é 1. '
                         'Thunderstruck com a lista certa: voz cobrindo 38%% do canto com 1, 65%% com 2')
    ap.add_argument('--sem-auditoria', action='store_true',
                    help='não conferir a montagem de 6 flybacks de cada música (auditar_montagem.py)')
    args = ap.parse_args()

    saida = Path(args.saida)
    saida = saida if saida.is_absolute() else RAIZ / saida
    saida.mkdir(parents=True, exist_ok=True)
    arq_estado = saida / '.lote.json'
    estado = json.loads(arq_estado.read_text(encoding='utf-8')) if arq_estado.is_file() else {}
    guardar = lambda: arq_estado.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding='utf-8')

    if args.situacao or not (args.endereco or args.lista):
        if not estado:
            ap.error('passe uma playlist, --lista, ou rode depois de um lote para ver a situação')
        from collections import Counter
        print(Counter(v['situacao'] for v in estado.values()))
        for vid, v in estado.items():
            if v['situacao'] != 'feito':
                print(f'  {v["situacao"]:9s} {v.get("titulo", vid)}  {v.get("erro", "")}')
        return

    import transcrever as T
    T.achar_no_winget('yt-dlp', 'ffmpeg', 'deno')      # o winget não atualiza o PATH da sessão
    enderecos = [args.endereco] if args.endereco else \
        [l.strip() for l in Path(args.lista).read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')]
    fila = []
    for e in enderecos:
        try:
            fila += videos_de(e)
        except Exception as ex:
            log(f'não consegui ler {e}: {ex}')
    log(f'{len(fila)} vídeos na fila; {sum(1 for v, _ in fila if estado.get(v, {}).get("situacao") == "feito")} já feitos')
    if args.listar:
        for vid, titulo_yt in fila:
            print(f'{vid}\t{titulo_yt}\t{estado.get(vid, {}).get("situacao", "")}')
        return
    listas = json.loads(Path(args.instrumentos_por).read_text(encoding='utf-8')) if args.instrumentos_por else {}

    novos = 0
    for n, (vid, titulo_yt) in enumerate(fila, 1):
        atual = estado.get(vid, {})
        if atual.get('situacao') == 'feito' or (atual.get('situacao') in ('mirelo', 'sem audio') and not args.refazer_falhas):
            continue
        if args.limite and novos >= args.limite:
            log(f'limite de {args.limite} músicas atingido')
            break
        url = f'https://www.youtube.com/watch?v={vid}'
        artista, musica, duracao = metadados(url)
        titulo = nome_livre(saida, artista, musica, vid, estado)
        estado[vid] = atual = {'titulo': titulo, 'url': url, 'situacao': 'rodando', 'tentativas': {}}
        guardar()
        log(f'[{n}/{len(fila)}] {titulo} ({duracao // 60}:{duracao % 60:02d})')

        # A internet caiu por três minutos numa madrugada e dez músicas seguidas viraram "sem
        # áudio", com duas tentativas a 20 s. Agora são cinco, esperando cada vez mais (até 8 min
        # no total): uma queda curta passa, e um vídeo que não existe mais ainda desiste.
        audio = None
        for t in range(5):
            try:
                audio = baixar(url, vid)
                break
            except Exception as ex:
                atual['erro'] = f'download: {ex}'
                log(f'   download falhou: {ex}')
                time.sleep(30 * 2 ** t)
        if not audio:
            atual['situacao'] = 'sem audio'
            guardar()
            continue
        if artista == 'artista não identificado' and musica == 'sem título':
            # os dados falharam (sem internet) e o download passou depois: busca de novo, senão
            # a música entra no acervo como "artista não identificado - sem título"
            artista, musica, duracao = metadados(url)
            atual['titulo'] = titulo = nome_livre(saida, artista, musica, vid, estado)
            guardar()
            log(f'   é {titulo}')
        if not duracao:            # o YouTube nem sempre informa; o áudio baixado sempre sabe
            try:
                import soundfile as sf
                duracao = int(sf.info(str(audio)).duration)
            except Exception:
                pass

        rel = None
        for t in range(1, args.tentativas + 1):
            atual['tentativas'] = t
            guardar()
            inicio = time.time()
            # da segunda em diante, processo novo e separação em blocos menores
            trecho = 10.0 if t == 1 else 5.0
            try:
                rel = transcrever(audio, titulo, saida, args.modelo, duracao, trecho,
                                  instrumentos=listas.get(vid) or 'auto',
                                  orientacao=args.orientacao_com_lista if listas.get(vid) else 1.0)
                log(f'   {args.modelo}: pronto em {(time.time() - inicio) / 60:.1f} min · '
                    f'{", ".join(rel.get("instrumentos") or []) or "sem lista"}')
                break
            except Falha as ex:
                atual['erro'] = str(ex)
                if ex.instrumentos:
                    atual['instrumentos'] = ex.instrumentos
                log(f'   tentativa {t}: {ex}')

        if not rel:
            atual['situacao'] = 'mirelo'
            guardar()
            para_o_mirelo(saida, estado)
            log('   foi para a lista do Mirelo')
            continue
        arq = Path(rel['arquivo'])
        if listas.get(vid):
            rel['origem'] = (f'MuScriptor {rel["modelo"]} (Kyutai/Mirelo) rodado localmente, transcrição automática '
                             f'do áudio, sem transcritor humano; instrumentos escolhidos à mão: '
                             f'{", ".join(rel.get("instrumentos") or []).replace("_", " ")}'
                             + (f'; orientação {args.orientacao_com_lista:g}' if args.orientacao_com_lista != 1 else ''))
        entrada = creditar(saida, arq, artista, musica, url, rel['modelo'], rel)
        atual.update(situacao='feito', modelo=rel['modelo'], arquivo=arq.name,
                     instrumentos=rel.get('instrumentos'), segundos=rel.get('segundos'),
                     aproveitamento=entrada['aproveitamento'], aproveitamento6=entrada['aproveitamento6'])
        atual.pop('erro', None)
        guardar()
        para_o_mirelo(saida, estado)       # sai da lista se tinha ido para ela antes
        novos += 1
        log(f'   cabe em 2: {entrada["aproveitamento"]}% · em 6: {entrada["aproveitamento6"]}% · voz: {entrada["vocal"]}')
        if not args.sem_auditoria:
            avisos = auditar(arq)
            cobre, aviso = conferir_voz(audio, arq)
            if cobre is not None:
                atual['voz_coberta'] = cobre
                log(f'   a faixa de voz cobre {cobre}% do canto da gravação')
            if aviso:
                avisos.append(aviso)
            atual['avisos'] = avisos
            guardar()
            for a in avisos:
                log(f'   ! {a}')
        audio.unlink(missing_ok=True)

    from collections import Counter
    log('fim do lote: ' + ', '.join(f'{k} {v}' for k, v in Counter(v['situacao'] for v in estado.values()).items()))
    log('para aparecer no site: python tools/gerar_acervo.py (e publicar)')


if __name__ == '__main__':
    if os.name == 'nt':
        sys.stdout.reconfigure(encoding='utf-8')
    main()
