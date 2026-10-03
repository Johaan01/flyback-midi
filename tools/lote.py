"""Transcreve uma playlist inteira do YouTube, sozinho, e deixa cada música creditada no acervo.

    python tools/lote.py "https://www.youtube.com/playlist?list=..."
    python tools/lote.py --lista links.txt              # um endereço por linha
    python tools/lote.py --situacao                     # o que já foi, o que falhou, o que falta

Feito para ficar rodando sem ninguém olhando. Por música:

1. baixa o áudio (yt-dlp) para um cache temporário, que só some depois do MIDI pronto;
2. roda o transcrever.py num processo à parte, com `--instrumentos auto` e o `large`. Processo à
   parte de propósito: depois de um erro de CUDA o estado do processo não é confiável, e uma
   música ruim não pode contaminar as seguintes;
3. se o `large` falhar, tenta de novo de outro jeito: processo novo e a separação em blocos
   de 5 s em vez de 10, que é onde a placa aperta. Não cai para o `medium` — o dono do projeto
   prefere o resultado bom a um resultado qualquer. Se falhar de novo, a música vai para
   `para-o-mirelo.md` na pasta de saída, com o endereço e os instrumentos detectados, para
   rodar à mão no Mirelo marcando aqueles instrumentos; e o lote segue;
4. mede o aproveitamento em 2 e em 6 flybacks e grava o crédito no creditos.json da pasta:
   artista e título do YouTube, o endereço, o modelo e os instrumentos detectados.

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


def baixar(url, vid):
    CACHE.mkdir(exist_ok=True)
    pronto = sorted(CACHE.glob(f'{vid}.wav'))
    if pronto:
        return pronto[0]
    rc, _, err = ytdlp('-q', '--no-playlist', '-x', '--audio-format', 'wav', '-o',
                       str(CACHE / f'{vid}.%(ext)s'), url, timeout=1800)
    achado = sorted(CACHE.glob(f'{vid}.wav'))
    if rc or not achado:
        raise RuntimeError((err.strip().splitlines() or ['sem detalhe'])[-1][:300])
    return achado[0]


class Falha(RuntimeError):
    """Transcrição que não terminou, com os instrumentos que chegaram a ser detectados."""
    def __init__(self, motivo, instrumentos=None):
        super().__init__(motivo)
        self.instrumentos = instrumentos or []


def transcrever(audio, titulo, saida, modelo, duracao, trecho=10.0):
    """Roda o transcrever.py à parte. Devolve o relatório, ou levanta Falha com o motivo."""
    rel = CACHE / f'{audio.stem}.{modelo}.json'
    rel.unlink(missing_ok=True)
    # o large leva ~3,5 vezes a duração da música numa RTX 2060, com a separação junto; folga
    # larga, só para não deixar uma música travada segurar o lote inteiro
    limite = max(1800, 8 * (duracao or 300))
    cmd = [sys.executable, str(AQUI / 'transcrever.py'), str(audio), '--titulo', titulo,
           '--saida', str(saida), '--modelo', modelo, '--instrumentos', 'auto', '--relatorio', str(rel),
           '--trecho', str(trecho)]
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=limite, env=env)
    except subprocess.TimeoutExpired as e:
        texto = (e.stdout or '') if isinstance(e.stdout, str) else ''
        raise Falha(f'passou de {limite // 60} min', _instrumentos(texto))
    if r.returncode or not rel.is_file():
        fim = [l for l in (r.stderr + r.stdout).splitlines() if l.strip() and '[muscriptor]' not in l]
        raise Falha((fim[-1] if fim else f'saiu com {r.returncode}')[:300], _instrumentos(r.stdout))
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


def creditar(saida, arq, artista, musica, url, modelo, rel):
    faixas = ler_midi(arq.read_bytes())
    fins = [t1 for f in faixas for _, t1, _ in f.notas]
    dur = (max(fins) if fins else 0) + .3
    medida, nota = achar_lead(faixas, dur)      # a mesma detecção de canto do site e do acervo
    vocal = veredito_lead(nota) + (f' · faixa "{medida["nome"]}"' if medida and nota >= 3.8 else '')
    insts = ', '.join(rel.get('instrumentos') or []) or 'sem lista'
    entrada = {
        'autor': artista, 'artista': artista,
        'licenca': 'obra protegida — uso educacional sem fins lucrativos',
        'credito': f'interpretação de {artista}; "{musica}"',
        'transcricao': f'MuScriptor {modelo} (Kyutai/Mirelo) rodado localmente, transcrição automática do '
                       f'áudio, sem transcritor humano; instrumentos detectados pelo PANNs: {insts}',
        'fonte': url,
        'vocal': vocal,
        'aproveitamento': round(aproveitamento(faixas, dur) * 100),
        'aproveitamento6': round(aproveitamento_n(faixas, dur, 6) * 100),
    }
    c = saida / 'creditos.json'
    dados = json.loads(c.read_text(encoding='utf-8')) if c.is_file() else {}
    dados[arq.name] = entrada
    c.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return entrada


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

        audio = None
        for _ in range(args.tentativas):
            try:
                audio = baixar(url, vid)
                break
            except Exception as ex:
                atual['erro'] = f'download: {ex}'
                log(f'   download falhou: {ex}')
                time.sleep(20)
        if not audio:
            atual['situacao'] = 'sem audio'
            guardar()
            continue
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
                rel = transcrever(audio, titulo, saida, args.modelo, duracao, trecho)
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
        entrada = creditar(saida, arq, artista, musica, url, rel['modelo'], rel)
        atual.update(situacao='feito', modelo=rel['modelo'], arquivo=arq.name,
                     instrumentos=rel.get('instrumentos'), segundos=rel.get('segundos'),
                     aproveitamento=entrada['aproveitamento'], aproveitamento6=entrada['aproveitamento6'])
        atual.pop('erro', None)
        guardar()
        para_o_mirelo(saida, estado)       # sai da lista se tinha ido para ela antes
        audio.unlink(missing_ok=True)
        novos += 1
        log(f'   cabe em 2: {entrada["aproveitamento"]}% · em 6: {entrada["aproveitamento6"]}% · voz: {entrada["vocal"]}')

    from collections import Counter
    log('fim do lote: ' + ', '.join(f'{k} {v}' for k, v in Counter(v['situacao'] for v in estado.values()).items()))
    log('para aparecer no site: python tools/gerar_acervo.py (e publicar)')


if __name__ == '__main__':
    if os.name == 'nt':
        sys.stdout.reconfigure(encoding='utf-8')
    main()
