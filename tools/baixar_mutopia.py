#!/usr/bin/env python3
"""Baixa os MIDIs do Mutopia Project para musicas/classicos.

    python tools/baixar_mutopia.py            (tudo que ainda não foi baixado)
    python tools/baixar_mutopia.py --limite 50

O Mutopia (mutopiaproject.org) publica partituras em domínio público ou
Creative Commons, com MIDI gerado pelo LilyPond. Todas as licenças permitem
redistribuir; as CC pedem crédito, que fica em musicas/classicos/creditos.json
e aparece no site quando a música é aberta.

Como funciona:
  1. a lista de peças vem do repositório MutopiaProject/MutopiaProject no GitHub
     (uma consulta à API);
  2. os nomes dos compositores vêm da página browse.html do Mutopia;
  3. para cada peça, lê o .rdf (título, opus, instrumentos, licença, arquivo MIDI)
     e baixa o .mid ou o -mids.zip dos movimentos.

Pode rodar de novo: peças já registradas em creditos.json são puladas, então só
chega o que for novo. Só usa a biblioteca padrão do Python.
"""
import argparse
import html
import io
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / 'musicas' / 'classicos'
CREDITOS = DESTINO / 'creditos.json'
SITE = 'https://www.mutopiaproject.org/'
ARVORE = 'https://api.github.com/repos/MutopiaProject/MutopiaProject/git/trees/master?recursive=1'
AGENTE = 'flyback-midi-acervo/1.0 (+https://github.com/Johaan01/flyback-midi)'
MP = '{http://www.mutopiaproject.org/piece-data/0.1/}'
PAUSA = 0.25          # segundos entre pedidos de cada conexão
CONEXOES = 4

trava = Lock()


def baixar(url, tentativas=4):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': AGENTE})
            with urllib.request.urlopen(req, timeout=40) as r:
                dados = r.read()
            time.sleep(PAUSA)
            return dados
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == tentativas - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if i == tentativas - 1:
                raise
        time.sleep(2 ** i)
    return None


def pecas_do_repositorio():
    arvore = json.loads(baixar(ARVORE))
    if arvore.get('truncated'):
        print('aviso: a árvore do GitHub veio truncada; algumas peças podem faltar')
    pecas = set()
    for item in arvore['tree']:
        p = item['path']
        if item['type'] != 'blob' or not p.startswith('ftp/') or not p.endswith('.ly'):
            continue
        partes = p.split('/')
        pasta, nome = partes[-2], partes[-1][:-3]
        if pasta == nome:
            pecas.add('/'.join(partes[:-1]))
        elif pasta.endswith('-lys') and len(partes) >= 4:
            pecas.add('/'.join(partes[:-2]))
    return sorted(pecas)


def compositores():
    pagina = baixar(SITE + 'browse.html').decode('utf-8', 'replace')
    nomes = {}
    for ident, nome in re.findall(r"make-table\.cgi\?Composer=([A-Za-z0-9-]+)'>([^<]+)</a>", pagina):
        nomes[ident] = html.unescape(nome)
    return nomes


def sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c)).casefold()


def pasta_do_compositor(ident, nome):
    """'J. S. Bach (1685–1750)' com id BachJS vira 'Bach (J. S.)': ordena pelo sobrenome."""
    nome = re.sub(r'\s*\([^)]*\)\s*$', '', nome or ident).strip()
    partes = nome.split()
    chave = sem_acento(ident)
    for i, parte in enumerate(partes):
        formas = {sem_acento(parte).rstrip('.'), parte.lower().replace('ü', 'ue').replace('ö', 'oe').replace('ä', 'ae')}
        if len(parte) > 2 and any(chave.startswith(f) for f in formas):
            sobrenome, prenome = ' '.join(partes[i:]), ' '.join(partes[:i])
            return f'{sobrenome} ({prenome})' if prenome else sobrenome
    return nome


def nome_de_arquivo(s):
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip(' .')
    return (s[:110].rstrip(' .') or 'sem título')


def licenca_curta(lic):
    l = lic.lower()
    if 'noncommercial' in l or 'no deriv' in l or 'noderiv' in l:
        return None                      # não dá para publicar num repositório aberto
    if 'public domain' in l or 'domain' in l:
        return 'Domínio público'
    m = re.search(r'(\d\.\d)', l)
    v = (' ' + m.group(1)) if m else ''
    if 'sharealike' in l or 'share-alike' in l or 'share alike' in l:
        return 'CC BY-SA' + v
    if 'attribution' in l:
        return 'CC BY' + v
    return None


def ler_rdf(dados):
    raiz = ET.fromstring(dados)
    d = raiz.find('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
    get = lambda k: ((d.find(MP + k).text or '').strip() if d is not None and d.find(MP + k) is not None else '')
    return {k: get(k) for k in ('title', 'composer', 'opus', 'for', 'style', 'licence', 'midFile', 'maintainer', 'arranger', 'id')}


def processar(peca, nomes, creditos, usados):
    stem = peca.split('/')[-1]
    rdf = baixar(f'{SITE}{peca}/{stem}.rdf')
    if not rdf:
        return 'sem rdf', []
    info = ler_rdf(rdf)
    lic = licenca_curta(info['licence'])
    if not lic:
        return 'licença ' + (info['licence'] or 'vazia'), []
    if not info['midFile']:
        return 'sem midi', []
    dados = baixar(f'{SITE}{peca}/{info["midFile"]}')
    if not dados:
        return 'midi não encontrado', []

    ident = info['composer'] or peca.split('/')[1]
    pasta = nome_de_arquivo(pasta_do_compositor(ident, nomes.get(ident, ident)))
    titulo = info['title'] or stem
    if info['opus'] and sem_acento(info['opus']) not in sem_acento(titulo):
        titulo = f'{titulo} ({info["opus"]})'
    base = nome_de_arquivo(titulo)

    if info['midFile'].lower().endswith('.zip'):
        try:
            z = zipfile.ZipFile(io.BytesIO(dados))
            mids = sorted(n for n in z.namelist() if n.lower().endswith(('.mid', '.midi')))
            partes = [(f'{base} - {i + 1:02d}', z.read(n)) for i, n in enumerate(mids)]
        except zipfile.BadZipFile:
            return 'zip inválido', []
        if len(partes) == 1:
            partes = [(base, partes[0][1])]
    else:
        partes = [(base, dados)]

    feitos = []
    compositor = re.sub(r'\s*\([^)]*\)\s*$', '', nomes.get(ident, ident)).strip()
    for nome, conteudo in partes:
        if conteudo[:4] != b'MThd':
            continue
        with trava:
            rel = f'{pasta}/{nome}.mid'
            n = 2
            while rel in usados:
                rel = f'{pasta}/{nome} ({n}).mid'
                n += 1
            usados.add(rel)
        arq = DESTINO / rel
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(conteudo)
        feitos.append(rel)
        with trava:
            creditos[rel] = {
                'autor': compositor,
                'instrumentos': info['for'],
                'estilo': info['style'],
                'licenca': lic,
                'credito': ('tipografia de ' + info['maintainer']) if info['maintainer'] else '',
                'arranjo': info['arranger'],
                'fonte': f'{SITE}{peca}/',
                'mutopia': peca,
            }
    return 'ok', feitos


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--limite', type=int, default=0, help='baixa no máximo N peças novas')
    args = ap.parse_args()

    creditos = json.loads(CREDITOS.read_text(encoding='utf-8')) if CREDITOS.is_file() else {}
    feitas = {c['mutopia'] for c in creditos.values()}
    usados = set(creditos)

    print('lendo a lista de peças no GitHub…')
    pecas = [p for p in pecas_do_repositorio() if p not in feitas]
    if args.limite:
        pecas = pecas[:args.limite]
    print(f'{len(pecas)} peças novas para baixar ({len(feitas)} já estavam no acervo)')
    if not pecas:
        return
    nomes = compositores()

    motivos, arquivos, t0 = {}, 0, time.time()

    def salvar():
        DESTINO.mkdir(parents=True, exist_ok=True)
        with trava:
            texto = json.dumps(dict(sorted(creditos.items())), ensure_ascii=False, indent=1)
        CREDITOS.write_text(texto + '\n', encoding='utf-8')

    with ThreadPoolExecutor(CONEXOES) as ex:
        futuros = {ex.submit(processar, p, nomes, creditos, usados): p for p in pecas}
        for i, f in enumerate(as_completed(futuros), 1):
            try:
                motivo, feitos = f.result()
            except Exception as e:  # noqa: BLE001 — uma peça ruim não para o resto
                motivo, feitos = 'erro: ' + type(e).__name__, []
            motivos[motivo] = motivos.get(motivo, 0) + 1
            arquivos += len(feitos)
            if i % 50 == 0 or i == len(pecas):
                salvar()
                print(f'  {i}/{len(pecas)} peças · {arquivos} arquivos · {time.time() - t0:.0f} s', flush=True)
    salvar()
    print('resultado:', ', '.join(f'{k}: {v}' for k, v in sorted(motivos.items(), key=lambda x: -x[1])))


if __name__ == '__main__':
    sys.exit(main())
