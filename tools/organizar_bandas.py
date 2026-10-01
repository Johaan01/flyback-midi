#!/usr/bin/env python3
"""Arruma musicas/bandas: identifica, tira repetido e ordena pelo que é mais conhecido.

    python tools/organizar_bandas.py                    # só mostra o que faria
    python tools/organizar_bandas.py --aplicar          # move e escreve creditos.json
    python tools/organizar_bandas.py --origem "pasta"   # de onde vêm os arquivos soltos
    python tools/organizar_bandas.py --token XXXX       # token do ListenBrainz, opcional

O que entra aqui é transcrição de fã: arquivo solto chamado "banda-titulo-ano.mid", sem ordem
nenhuma, com a mesma música repetida em versões diferentes. Para testar o flyback com música
que se reconhece, o que importa é saber quais são as conhecidas — e é isso que esta ferramenta
mede, com dois bancos abertos:

  Wikipedia   visitas ao artigo da música nos últimos doze meses. É a fonte principal porque
              não pede chave nenhuma e cobre todas as bandas por igual.
              https://wikimedia.org/api/rest_v1/ e https://en.wikipedia.org/w/api.php

  ListenBrainz  total de escutas por gravação, do banco aberto da MetaBrainz (dados em CC0).
              Mede audição de verdade, e por isso pesa mais quando está disponível. Desde
              2025 o endpoint de popularidade pede token: pegue um de graça em
              https://listenbrainz.org/settings/ e passe em --token (ou em LISTENBRAINZ_TOKEN).
              Sem token, a ordenação sai só pela Wikipedia, o que já funciona bem.

As duas medidas estão em escalas diferentes — milhões de escutas contra dezenas de milhares de
visitas —, então não dá para somar uma com a outra. Cada uma é convertida no seu percentil
dentro da própria fonte, e aí sim as duas se combinam.

As respostas ficam guardadas em tools/popularidade.json, então rodar de novo não precisa de
internet e dá o mesmo resultado.

Repetidas: quando o mesmo título aparece mais de uma vez, fica o arquivo com a melhor
transcrição — mais faixas separadas (que é o que permite mandar instrumento para cada lado),
depois melhor aproveitamento em dois canais monofônicos, depois mais notas.

Só usa a biblioteca padrão do Python.
"""
import argparse
import difflib
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from curar_acervo import (ler_midi, aproveitamento, remover_vazias,   # noqa: E402
                           achar_lead, veredito_lead)       # mesmo leitor e mesma deteccao do site

RAIZ = Path(__file__).resolve().parent.parent
ORIGEM = RAIZ / 'musicas' / 'rock e metal (unsorted)'
DESTINO = RAIZ / 'musicas' / 'bandas'
CACHE = Path(__file__).resolve().parent / 'popularidade.json'

UA = 'flyback-midi/1.0 (https://github.com/Johaan01/flyback-midi) python-urllib'
MB = 'https://musicbrainz.org/ws/2'
LB = 'https://api.listenbrainz.org/1'
WP = 'https://en.wikipedia.org/w/api.php'
WPV = 'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user'
PAUSA_MB = 1.1      # o MusicBrainz pede no máximo uma chamada por segundo
PAUSA_WP = 0.15

PESO = {'listenbrainz': .62, 'wikipedia': .38}   # escuta de verdade vale mais que visita a artigo

# Como o nome da banda aparece no arquivo -> como ela se chama de verdade.
APELIDOS = {
    'acdc': 'AC/DC', 'ac dc': 'AC/DC', 'iron maiden': 'Iron Maiden',
    'judas priest': 'Judas Priest', 'black sabbath': 'Black Sabbath',
    'ozzy osbourne': 'Ozzy Osbourne', 'ozzy osboure': 'Ozzy Osbourne',
    'ozzy osborne': 'Ozzy Osbourne', 'scorpions': 'Scorpions',
    'powerwolf': 'Powerwolf', 'metallica': 'Metallica', 'megadeth': 'Megadeth',
    'slayer': 'Slayer', 'sepultura': 'Sepultura', 'pantera': 'Pantera',
    'disturbed': 'Disturbed', 'led zeppelin': 'Led Zeppelin', 'deep purple': 'Deep Purple',
    'guns n roses': "Guns N' Roses", 'gunsnroses': "Guns N' Roses",
    'queen': 'Queen', 'kiss': 'Kiss', 'motorhead': 'Motörhead', 'rainbow': 'Rainbow',
    'dio': 'Dio', 'anthrax': 'Anthrax', 'testament': 'Testament', 'helloween': 'Helloween',
    'blind guardian': 'Blind Guardian', 'nightwish': 'Nightwish', 'rammstein': 'Rammstein',
    'system of a down': 'System of a Down', 'nirvana': 'Nirvana', 'the beatles': 'The Beatles',
    'pink floyd': 'Pink Floyd', 'the rolling stones': 'The Rolling Stones',
    'van halen': 'Van Halen', 'aerosmith': 'Aerosmith', 'bon jovi': 'Bon Jovi',
    # nomes que nenhuma regra de capitalização acerta sozinha
    '10cc': '10cc', 'abba': 'ABBA', 'zz top': 'ZZ Top', 'rem': 'R.E.M.', 'u2': 'U2',
    'inxs': 'INXS', 'aha': 'a-ha', 'a ha': 'a-ha', 'a-ha': 'a-ha', 'ha': 'a-ha',
    'ub40': 'UB40', 'elo': 'ELO',
    'dc talk': 'dc Talk', 'xtc': 'XTC', 'ozzy': 'Ozzy Osbourne',
}

# Em quantos níveis o acervo se divide, do mais conhecido para o menos: (nome, piso, fração).
# Os dois primeiros crescem com o acervo mas nunca encolhem abaixo do piso — o topo tem de
# continuar sendo um punhado de músicas que qualquer um reconhece, e não uma lista de rolar.
NIVEIS = [('mais ouvidas', 45, .07), ('conhecidas', 85, .15), ('para fãs', None, None)]

# O acervo de folk russo é quase todo tradicional e em domínio público, mas algumas peças têm
# autor conhecido — e duas delas ainda estão protegidas. Chamar tudo de "tradicional" seria
# cômodo e errado: título -> (autoria, já em domínio público?).
AUTORIA_CONHECIDA = {
    'Katyusha': ('Matvey Blanter, letra de Mikhail Isakovsky (1938)', False),
    'Podmoskovnye Vechera': ('Vasily Solovyov-Sedoi, letra de Mikhail Matusovsky (1955)', False),
    'Pust Vsegda Budet Solntse': ('Arkady Ostrovsky, letra de Lev Oshanin (1962)', False),
    'Uralskaya Ryabinushka': ('Yevgeny Rodygin, letra de Mikhail Pilipenko (1953)', False),
    'Odinokaya Garmon': ('Boris Mokrousov, letra de Mikhail Isakovsky (1946)', False),
    'Dorogoi Dlinnoyu': ('Boris Fomin, letra de Konstantin Podrevsky (1924)', False),
    'Ochi Chornye': ('melodia de Florian Hermann, letra de Yevhen Hrebinka (1879)', True),
    'Otsveli Hrizantemy': ('Nikolai Kharito, letra de Vasily Shumsky (1910)', True),
    'Kalinka': ('Ivan Larionov (1860)', True),
    'Korobeiniki': ('melodia tradicional sobre poema de Nikolai Nekrasov (1861)', True),
    'Na Sopkah Manchzhurii': ('Ilya Shatrov (1906)', True),
}

ARTIGO = re.compile(r'\b(the|a|an|o|os|as)\b')
PARENTESES = re.compile(r'\(.*?\)|\[.*?\]')
SUFIXO = re.compile(r'\b(live|remaster(ed)?|demo|acoustic|edit|version|mix|single|mono|stereo)\b')

# Os arquivos vêm como "iron_maiden-run_to_the_hills-1982.mid": o ano do disco no fim e, às
# vezes, uma marca de quem transcreveu ("instru", "only", "full"). Nada disso é o nome da
# música, e deixar passar faz "paranoid instru only-1970" não casar com "Paranoid".
RX_ANO = re.compile(r'\s*[-–(\[]?\s*(?:19|20)\d{2}\s*[)\]]?\s*$')
RX_MARCA = re.compile(
    r'\s*[-–(\[]?\s*\b(instrumental|instru|instr|only|full|complete|final|midi'
    r'|karaoke|kar|v\d+|ver\d*)\b\s*[)\]]?\s*$', re.I)
MIUDAS = {'a', 'an', 'the', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'from',
          'by', 'with', 'as', 'is', 'it', 'into', 'over', 'vs', 'n'}
# o "(Black Sabbath song)" que a Wikipedia põe no fim do nome do artigo para desempatar
RX_DESAMBIGUA = re.compile(r'\s*\(([^()]*)\)\s*$')


def sem_acento(s):
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).casefold()


def chave(s):
    """Reduz um título ao que importa para comparar: sem acento, sem pontuação, sem '(live)'."""
    s = sem_acento(s).replace('&', ' and ').replace("'", '').replace('’', '')
    s = PARENTESES.sub(' ', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    s = SUFIXO.sub(' ', s)
    s = ARTIGO.sub(' ', s)
    return ' '.join(s.split())


def limpar_titulo(s):
    s = re.sub(r'\s{2,}', ' ', s.replace('_', ' ')).strip()
    s = RX_ANO.sub('', s)
    for _ in range(4):                       # "paranoid instru only-1970": tira uma marca por vez
        novo = RX_MARCA.sub('', s).strip(' -–')
        if novo == s or not novo:
            break
        s = novo
    return s.strip(' -–') or 'sem título'


def titulo_bonito(s):
    saida = []
    for k, p in enumerate(s.split()):
        if p.isupper() and len(p) > 1:       # N.I.B., TNT — já estão como devem ficar
            saida.append(p)
            continue
        b = p.lower()
        saida.append(b if k and b in MIUDAS else b[:1].upper() + b[1:])
    return ' '.join(saida)


NOME_MAX = 80


def seguro(s):
    """Nome que pode virar pasta ou arquivo. A barra de 'AC/DC' vira hífen — a pasta fica
    'AC-DC', e o nome de verdade continua no campo 'artista' do creditos.json.

    O corte em NOME_MAX não é capricho: o acervo Lakh tem títulos como o do 'Cygnus X-1, Book
    II' do Rush, com os seis movimentos listados, que passa de 250 caracteres e estoura o
    limite de caminho do Windows — o arquivo é criado mas nem o Git consegue removê-lo depois.
    """
    s = re.sub(r'[\\/:*?"<>|]', '-', s).strip(' .')
    s = re.sub(r'\s{2,}', ' ', s)
    if len(s) > NOME_MAX:
        s = s[:NOME_MAX].rsplit(' ', 1)[0].strip(' ,-.') or s[:NOME_MAX]
    return s or 'sem nome'


def normalizar_banda(nome):
    limpo = re.sub(r'\s{2,}', ' ', nome.replace('_', ' ')).strip()
    # Primeiro a forma crua, sem passar por chave(): ela tira artigo, e "A-Ha" vira "ha",
    # que não casa com nada. Nome de banda não tem artigo para tirar.
    direto = ' '.join(sem_acento(limpo).split())
    if direto in APELIDOS:
        return APELIDOS[direto]
    k = chave(nome)
    if k in APELIDOS:
        return APELIDOS[k]
    # nome que já veio com maiúscula foi escrito assim na fonte, e title() só estragaria:
    # "10cc" vira "10Cc", "ABC" vira "Abc", "AC/DC" vira "Ac/Dc"
    return limpo if any(c.isupper() for c in limpo) else limpo.title()


def partir(nome):
    """'iron_maiden-run_to_the_hills-1982.mid' -> ('Iron Maiden', 'Run to the Hills')."""
    base = re.sub(r'\.(mid|midi)$', '', nome, flags=re.I).replace('_', ' ')
    base = re.sub(r'\s{2,}', ' ', base).strip()
    for sep in (' - ', ' – ', '-', '–'):
        if sep in base:
            banda, titulo = base.split(sep, 1)
            banda, titulo = banda.strip(), limpar_titulo(titulo)
            if banda and titulo:
                return normalizar_banda(banda), titulo_bonito(titulo)
    return None, titulo_bonito(limpar_titulo(base))


# ---------------------------------------------------------------- rede
def buscar(url, cabecalhos=None, corpo=None, tentativas=3):
    """Uma chamada, com repetição quando o serviço pede calma (429) ou tropeça (5xx)."""
    espera = 1.0
    for n in range(tentativas):
        h = {'User-Agent': UA, 'Accept': 'application/json'}
        h.update(cabecalhos or {})
        dados = json.dumps(corpo).encode() if corpo is not None else None
        if dados:
            h['Content-Type'] = 'application/json'
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, data=dados, headers=h), timeout=30) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                try:
                    return json.loads(e.read().decode('utf-8'))
                except (ValueError, OSError):
                    return {'erro_http': e.code}
            if n == tentativas - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if n == tentativas - 1:
                raise
        time.sleep(espera)
        espera *= 2
    return None


def carregar_cache():
    base = {'listenbrainz': {}, 'wikipedia': {}, 'categorias': {}}
    if CACHE.is_file():
        try:
            d = json.loads(CACHE.read_text(encoding='utf-8'))
            if 'bandas' in d:                      # formato antigo, só com ListenBrainz
                base['listenbrainz'] = d['bandas']
            for k in base:
                base[k].update(d.get(k) or {})
        except ValueError:
            pass
    return base


# ---------------------------------------------------------------- ListenBrainz
def lb_da_banda(banda, cache, token):
    """{chave do título: escutas}, somando todas as versões de cada música."""
    guardado = cache['listenbrainz'].get(banda)
    if guardado is not None:
        return guardado['musicas']
    if not token:
        return None
    try:
        q = urllib.parse.quote(f'artist:"{banda}"')
        achado = buscar(f'{MB}/artist/?query={q}&fmt=json&limit=1')
        time.sleep(PAUSA_MB)
        mbid = (achado.get('artists') or [{}])[0].get('id') if achado else None
        if not mbid:
            return None
        d = buscar(f'{LB}/popularity/top-recordings-for-artist/{mbid}',
                   {'Authorization': f'Token {token}'})
        if not isinstance(d, list):
            erro = (d or {}).get('error', '')
            print(f'  ! ListenBrainz recusou {banda}: {str(erro)[:90]}', file=sys.stderr)
            return None
        musicas = {}
        for r in d:
            k = chave(r.get('recording_name') or '')
            if k:
                musicas[k] = musicas.get(k, 0) + int(r.get('total_listen_count') or 0)
        cache['listenbrainz'][banda] = {'mbid': mbid, 'musicas': musicas}
        return musicas
    except (urllib.error.URLError, ValueError, TypeError, KeyError) as e:
        print(f'  ! ListenBrainz falhou em {banda}: {e}', file=sys.stderr)
        return None


def casar(titulo, musicas):
    """Acha a música no catálogo da banda, aceitando diferença pequena de grafia."""
    k = chave(titulo)
    if not k or not musicas:
        return 0
    if k in musicas:
        return musicas[k]
    perto = difflib.get_close_matches(k, list(musicas), n=1, cutoff=.86)
    if perto:
        return musicas[perto[0]]
    for mk in musicas:                      # título encurtado ou esticado no nome do arquivo
        if len(mk) > 8 and (mk in k or k in mk):
            return musicas[mk]
    return 0


# ---------------------------------------------------------------- Wikipedia
def janela_de_meses(meses=12):
    hoje = date.today().replace(day=1)
    fim = hoje - timedelta(days=1)
    ini = hoje
    for _ in range(meses):
        ini = (ini - timedelta(days=1)).replace(day=1)
    return ini.strftime('%Y%m%d00'), fim.strftime('%Y%m%d00')


def chave_bruta(s):
    """Como chave(), mas sem jogar fora o que está entre parênteses, que às vezes é parte do
    nome: "Revolution (Mother Earth)" não é a mesma coisa que "Revolution"."""
    s = sem_acento(s).replace('&', ' and ').replace("'", '').replace('’', '')
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return ' '.join(ARTIGO.sub(' ', s).split())


def artigo_serve(artigo, titulo, banda):
    """A busca da Wikipedia quase sempre devolve alguma coisa, e aceitar o primeiro resultado
    dava número errado: "Revolution (Mother Earth)" pegava o artigo Revolution, com 1,4 milhão
    de visitas, e quatro músicas do Scorpions pegavam todas a mesma página. Então só serve o
    artigo cujo nome é mesmo o da música, tirando o desambiguador entre parênteses."""
    m = RX_DESAMBIGUA.search(artigo)
    desambiguado = False
    if m:
        d = sem_acento(m.group(1))
        # "album" saiu daqui de propósito: "...And Justice for All (album)" não é a música,
        # e aceitá-lo fazia a contagem do disco virar a contagem da faixa
        if any(p in d for p in ('song', 'single')) or sem_acento(banda) in d:
            artigo, desambiguado = artigo[:m.start()], True
    # música que se chama como a banda ("Black Sabbath", "Iron Maiden"): sem desambiguador no
    # nome, o artigo achado é o da banda, e as visitas dela não dizem nada sobre a música
    if not desambiguado and chave_bruta(artigo) == chave_bruta(banda):
        return False
    return chave_bruta(artigo) == chave_bruta(titulo)


RX_CAT_MUSICA = re.compile(r'\b(songs?|singles?|hymns?|anthems?|instrumentals?)\b', re.I)


def artigo_e_musica(artigo, cache):
    """Confirma pelas categorias que o artigo é de uma canção.

    Só comparar o nome não basta, porque um monte de música se chama como outra coisa famosa:
    "Genghis Khan" do Iron Maiden casava com o artigo do imperador mongol e trazia 3,2 milhões
    de visitas, "Ides of March" com o evento histórico, e o tema de "Buffy the Vampire Slayer"
    com a série. Categoria do tipo "Category:1991 singles" ou "Category:Metallica songs"
    resolve, e é uma chamada barata.
    """
    if artigo in cache['categorias']:
        return cache['categorias'][artigo]
    try:
        nome = urllib.parse.quote(artigo.replace(' ', '_'), safe='')
        d = buscar(f'{WP}?action=query&prop=categories&cllimit=500&titles={nome}&format=json')
        time.sleep(PAUSA_WP)
        paginas = ((d or {}).get('query') or {}).get('pages') or {}
        cats = [c.get('title', '') for p in paginas.values() for c in (p.get('categories') or [])]
        ok = any(RX_CAT_MUSICA.search(c) for c in cats)
    except (urllib.error.URLError, ValueError, TypeError, KeyError, AttributeError):
        return None
    cache['categorias'][artigo] = ok
    return ok


def wp_da_musica(banda, titulo, cache, janela):
    """Visitas ao artigo da música nos últimos doze meses. 0 quando a música não tem artigo —
    o que já é, por si, sinal de que ela é menos conhecida."""
    ck = f'{banda}|{chave(titulo)}'
    if ck in cache['wikipedia']:
        return cache['wikipedia'][ck]['visitas']
    artigo, visitas = None, 0
    try:
        q = urllib.parse.quote(f'"{titulo}" {banda}')
        d = buscar(f'{WP}?action=query&list=search&srsearch={q}&srlimit=8&format=json')
        time.sleep(PAUSA_WP)
        for a in ((d or {}).get('query') or {}).get('search') or []:
            if artigo_serve(a['title'], titulo, banda) and artigo_e_musica(a['title'], cache):
                artigo = a['title']
                break
        if artigo:
            nome = urllib.parse.quote(artigo.replace(' ', '_'), safe='')
            pv = buscar(f'{WPV}/{nome}/monthly/{janela[0]}/{janela[1]}')
            time.sleep(PAUSA_WP)
            visitas = sum(i.get('views') or 0 for i in (pv or {}).get('items') or [])
    except (urllib.error.URLError, ValueError, TypeError, KeyError) as e:
        print(f'  ! Wikipedia falhou em {banda} — {titulo}: {e}', file=sys.stderr)
        return None
    cache['wikipedia'][ck] = {'artigo': artigo, 'visitas': visitas}
    return visitas


# ---------------------------------------------------------------- qualidade da transcrição
def medir(caminho):
    try:
        faixas = ler_midi(caminho.read_bytes())
    except Exception:
        return None
    if not faixas:
        return None
    notas = sum(len(f.notas) for f in faixas)
    dur = max(n[1] for f in faixas for n in f.notas)
    if dur < 12 or notas < 60:   # 12 s ainda pega interlúdio curto de disco, que é faixa de verdade
        return None
    nomeadas = sum(1 for f in faixas if f.nome and not f.gm)
    cantor, lead = achar_lead(faixas, dur)
    return {'faixas': len(faixas), 'nomeadas': nomeadas, 'notas': notas, 'dur': dur,
            'score': aproveitamento(faixas, dur + .3),
            'lead': lead, 'cantor': (cantor or {}).get('nome', '')}


def qualidade(m):
    """Qual transcrição da mesma música fica.

    A linha de canto pesa quase metade: sem ela a música sai pobre no flyback — toca só
    acompanhamento, e quem ouve sente que falta alguma coisa. O acervo Lakh costuma ter três
    ou quatro versões da mesma música, e normalmente só uma traz o vocal, então é justamente
    aqui que se escolhe certo. Depois vale ter faixas separadas, que é o que permite mandar
    instrumento para cada lado.
    """
    return (m['lead'] * .55
            + min(m['faixas'], 12) * .22 + min(m['nomeadas'], 12) * .06
            + m['score'] + min(m['notas'], 6000) / 12000)


def percentis(valores):
    """valor bruto -> posição relativa de 0 a 1, para comparar fontes de escalas diferentes."""
    positivos = sorted(v for v in valores if v > 0)
    if not positivos:
        return lambda v: 0.0
    n = len(positivos)

    def p(v):
        if v <= 0:
            return 0.0
        lo, hi = 0, n
        while lo < hi:                      # quantos valores são menores que este
            meio = (lo + hi) // 2
            if positivos[meio] < v:
                lo = meio + 1
            else:
                hi = meio
        return (lo + 1) / n
    return p


# ---------------------------------------------------------------- principal
def organizar(args):
    global DESTINO
    if args.destino:
        d = Path(args.destino)
        DESTINO = d if d.is_absolute() else (RAIZ / d)
    origem = Path(args.origem) if args.origem else ORIGEM
    # a pasta de entrada some quando tudo dela já foi arrumado; sem ela a ferramenta ainda
    # serve, para reclassificar o que está em musicas/bandas
    if not origem.is_dir() and not DESTINO.is_dir():
        sys.exit(f'não achei nem a pasta de entrada ({origem}) nem {DESTINO}')
    if not origem.is_dir():
        origem = DESTINO
    token = args.token or os.environ.get('LISTENBRAINZ_TOKEN') or ''
    # A classificação é sempre sobre o acervo inteiro: os arquivos novos da pasta de entrada
    # mais os que já estão arrumados. Ordenar só os novos entre si jogaria uma faixa qualquer
    # para o topo só por ser a única da rodada, e é o acervo todo que define o que é "mais
    # ouvida". Com isso a ferramenta pode rodar a cada leva nova, e tudo se reacomoda.
    arquivos = sorted(p for p in origem.rglob('*') if p.suffix.lower() in ('.mid', '.midi'))
    mesma = DESTINO.is_dir() and origem.resolve() == DESTINO.resolve()
    ja_postas = [] if mesma or not DESTINO.is_dir() else sorted(
        p for p in DESTINO.rglob('*') if p.suffix.lower() in ('.mid', '.midi'))
    print(f'{len(arquivos)} arquivos em {origem.name}'
          + (f', {len(ja_postas)} já em {DESTINO.name}' if ja_postas else '') + '\n')
    arquivos += ja_postas

    # de onde veio cada arquivo, escrito por baixar_bandas.py: é o que faz a atribuição apontar
    # para quem publicou a transcrição, e não só para a banda que compôs
    # A busca é insensível a maiúsculas de propósito: o nome do arquivo foi gravado numa
    # rodada do baixador e o manifesto pode ter sido escrito em outra, com a regra de
    # capitalização já corrigida — "10Cc - X.mid" no disco e "10CC - X.mid" no manifesto são
    # o mesmo arquivo, e casar exato perderia a procedência de todos eles.
    origens = {}
    manifesto = origem / '_origem.json'
    if manifesto.is_file():
        try:
            origens = {k.casefold(): v for k, v in
                       json.loads(manifesto.read_text(encoding='utf-8')).items()}
        except ValueError:
            pass

    def ja_arrumado(p):
        """Artista de um arquivo que já está em <destino>/<artista>/<título>.mid.

        Sem isto o artista sairia de `partir(p.name)`, que lê o nome do arquivo — e o nome de
        um arquivo já arrumado é só o título, sem o artista. Todos caíam em "(sem banda)" e
        músicas homônimas de bandas diferentes se fundiam na hora de tirar repetidas.
        """
        try:
            rel = p.relative_to(DESTINO)
        except ValueError:
            return None
        return rel.parts[0] if len(rel.parts) == 2 else ''

    itens, ilegiveis = [], 0
    for p in arquivos:
        org = origens.get(p.name.casefold()) or {}
        dono = ja_arrumado(p)
        # o manifesto tem o nome como a fonte escreveu, que é melhor do que o do arquivo:
        # o nome do arquivo já passou por uma normalização que perde maiúscula e pontuação
        if dono is not None:
            banda = normalizar_banda(dono) if dono else '(sem banda)'
            titulo = titulo_bonito(limpar_titulo(p.stem))
        elif org.get('artista') and org.get('titulo'):
            banda, titulo = normalizar_banda(org['artista']), titulo_bonito(limpar_titulo(org['titulo']))
        else:
            banda, titulo = partir(p.name)
        if args.artista:                     # acervo de autoria coletiva: o artista é fixo
            banda = args.artista
        m = medir(p)
        if m is None:
            ilegiveis += 1
            continue
        itens.append({'arq': p, 'banda': banda or '(sem banda)', 'titulo': titulo,
                      'chave': chave(titulo), 'origem': org, **m})
    if ilegiveis:
        print(f'{ilegiveis} ilegíveis ou curtos demais, deixados de fora\n')

    # repetidas: mesma banda e mesma música, fica a melhor transcrição
    grupos = {}
    for i in itens:
        grupos.setdefault((i['banda'], i['chave']), []).append(i)
    ficam, repetidas = [], []
    for g in grupos.values():
        g.sort(key=qualidade, reverse=True)
        ficam.append(g[0])
        repetidas += g[1:]

    bandas = sorted({i['banda'] for i in ficam})
    # música sem artista não pode ser muita: todas caem no mesmo balde e, ao tirar repetidas,
    # duas músicas homônimas de bandas diferentes viram uma só
    anonimas = sum(1 for i in ficam if i['banda'] == '(sem banda)')
    if anonimas > max(5, len(ficam) * .02):
        print(f'\n!! {anonimas} de {len(ficam)} músicas sem artista identificado — confira o nome '
              f'dos arquivos de entrada ("Artista - Título.mid")', file=sys.stderr)
    print(f'{len(bandas)} bandas: {", ".join(bandas)}')
    print(f'{len(ficam)} músicas distintas, {len(repetidas)} repetidas descartadas\n')

    cache = carregar_cache()
    janela = janela_de_meses()
    if args.plano:
        # Acervo de folk tradicional: ordenar Kalinka contra Troika por visita de artigo não
        # diz nada útil, e gastaria centenas de chamadas para produzir um número sem sentido.
        for i in ficam:
            i['escutas'] = i['visitas'] = 0
        print('acervo plano: sem medição de popularidade')
    if not args.plano:
        if not args.offline:
            print(f'medindo popularidade (Wikipedia{", ListenBrainz" if token else ""})…')
        for b in bandas:
            lb = None if args.offline else lb_da_banda(b, cache, token)
            if lb is None:
                lb = (cache['listenbrainz'].get(b) or {}).get('musicas')
            for i in ficam:
                if i['banda'] != b:
                    continue
                i['escutas'] = casar(i['titulo'], lb) if lb else 0
                if args.offline:
                    i['visitas'] = (cache['wikipedia'].get(f'{b}|{i["chave"]}') or {}).get('visitas', 0)
                else:
                    i['visitas'] = wp_da_musica(b, i['titulo'], cache, janela) or 0
    if not args.plano and not args.offline:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    # as duas fontes vivem em escalas diferentes: compara pelo percentil dentro de cada uma
    p_lb = percentis([i['escutas'] for i in ficam])
    p_wp = percentis([i['visitas'] for i in ficam])
    for i in ficam:
        pesos, soma = 0.0, 0.0
        if i['escutas'] > 0:
            soma += PESO['listenbrainz'] * p_lb(i['escutas'])
            pesos += PESO['listenbrainz']
        if i['visitas'] > 0:
            soma += PESO['wikipedia'] * p_wp(i['visitas'])
            pesos += PESO['wikipedia']
        i['nota'] = soma / pesos if pesos else 0.0

    ficam.sort(key=lambda i: (-i['nota'], -i['visitas'], i['banda'], i['titulo']))
    for pos, i in enumerate(ficam, 1):
        i['posicao'] = pos
    corte, nivel_de = 0, {}
    for nome, piso, fracao in NIVEIS:
        quanto = None if piso is None else max(piso, round(len(ficam) * fracao))
        fim = len(ficam) if quanto is None else min(len(ficam), corte + quanto)
        for i in ficam[corte:fim]:
            nivel_de[id(i)] = nome
        corte = fim

    com_lb = sum(1 for i in ficam if i['escutas'] > 0)
    com_wp = sum(1 for i in ficam if i['visitas'] > 0)
    sem_nada = [i for i in ficam if not i['nota']]
    print(f'\nmedidas: {com_wp} pela Wikipedia, {com_lb} pelo ListenBrainz, '
          f'{len(sem_nada)} sem nenhuma das duas')
    if not token and not args.plano:
        print('(sem token do ListenBrainz: a ordem saiu só pela Wikipedia — veja --token)')
    print()
    for nome, _, _ in NIVEIS:
        print(f'  {sum(1 for i in ficam if nivel_de[id(i)] == nome):4}  {nome}')
    print('\ntop 30:')
    for i in ficam[:30]:
        print(f'  {i["posicao"]:3}  {i["nota"]:.3f}  wiki {i["visitas"]:>8,}  '
              f'lb {i["escutas"]:>10,}  {i["banda"]} — {i["titulo"]}'.replace(',', '.'))
    if sem_nada:
        print(f'\nsem medição ({len(sem_nada)}), vão para o fim:')
        for i in sem_nada[:12]:
            print(f'       {i["banda"]} — {i["titulo"]}')

    if args.verbose and repetidas:
        print('\nrepetidas (fica a de cima):')
        for g in grupos.values():
            if len(g) > 1:
                for k, i in enumerate(g):
                    print(f'  {"fica" if not k else "sai "}  {qualidade(i):.2f}  '
                          f'{i["faixas"]:2d} faixas {i["notas"]:5d} notas  {i["arq"].name}')

    if not args.aplicar:
        print('\nnada foi alterado. Rode com --aplicar para valer.')
        return

    DESTINO.mkdir(parents=True, exist_ok=True)
    # parte do creditos.json que já existe: a ferramenta roda de novo a cada leva nova de
    # arquivos, e sobrescrever apagaria a atribuição de tudo que entrou nas levas anteriores
    arq_cred = DESTINO / 'creditos.json'
    creditos = {}
    if arq_cred.is_file():
        try:
            creditos = json.loads(arq_cred.read_text(encoding='utf-8'))
        except ValueError:
            pass
    antigos = {k: v for k, v in creditos.items()}
    creditos = {}
    tomados, guardados = set(), set()
    for i in ficam:
        nivel = nivel_de[id(i)]
        # A pasta é o artista, não o nível de popularidade: artista é coisa estável, e o nível
        # muda quando o número de escutas muda — o que trocaria a música de pasta e quebraria o
        # link dela. A popularidade continua gravada, em 'posicao', e vira filtro no site.
        rel = (seguro(i['titulo']) + '.mid') if args.plano else \
              f'{seguro(i["banda"])}/{seguro(i["titulo"])}.mid'
        # dois títulos distintos podem virar o mesmo nome de arquivo depois de limpos
        # ("Verse Chorus Verse (outtake, 1991)" e "Verse Chorus Verse (outtake,"): sem
        # desempatar, o segundo sobrescreveria o primeiro e a música sumiria
        if rel.casefold() in tomados:
            raiz, ext = rel[:-4], rel[-4:]
            k = 2
            while f'{raiz} ({k}){ext}'.casefold() in tomados:
                k += 1
            rel = f'{raiz} ({k}){ext}'
        tomados.add(rel.casefold())
        destino = DESTINO / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        if i['arq'].resolve() != destino.resolve():
            destino.unlink(missing_ok=True)
            shutil.move(str(i['arq']), str(destino))
        guardados.add(destino.resolve())
        # o que já estava escrito sobre esta música é preservado — inclusive o nome do
        # transcritor, se alguém tiver preenchido à mão — e só a posição é recalculada
        try:
            antes = antigos.get(i['arq'].relative_to(DESTINO).as_posix(), {})
        except ValueError:
            antes = {}
        fontes = []
        if i['visitas']:
            fontes.append(f'{i["visitas"]} visitas/ano na Wikipedia')
        if i['escutas']:
            fontes.append(f'{i["escutas"]} escutas no ListenBrainz')
        site = (i.get('origem') or {}).get('site') or ''
        transcrito = ('transcrição MIDI de autor não identificado'
                      + (f', publicada em {site}' if site else ''))
        autoria, dominio = AUTORIA_CONHECIDA.get(i['titulo'], (None, None))
        if autoria:
            composto, licenca = autoria, ('Domínio público' if dominio else
                                          'obra protegida · uso educacional sem fins lucrativos')
        elif args.plano:
            composto, licenca = 'tradicional, autoria não atribuída', 'Domínio público'
        else:
            composto, licenca = f'composição de {i["banda"]}', \
                                'obra protegida · uso educacional sem fins lucrativos'
        entrada = {
            'autor': i['banda'],
            'artista': i['banda'],
            'licenca': licenca,
            'credito': f'{composto}; {transcrito}',
            'transcricao': f'autor não identificado · {site}' if site else 'autor não identificado',
        }
        if (i.get('origem') or {}).get('url'):
            entrada['fonte'] = i['origem']['url']
        entrada.update({k: v for k, v in antes.items() if v})
        # o que o site usa para o filtro 'só com vocal', e o que responde a pergunta que
        # ninguém consegue responder ouvindo 718 arquivos um a um
        entrada['vocal'] = veredito_lead(i['lead'])
        if i['cantor'] and i['lead'] >= 3.8:
            entrada['vocal'] += f' · faixa "{i["cantor"]}"'
        if not args.plano:     # sem medição, não há posição nem nível para registrar
            entrada['posicao'] = i['posicao']
            entrada['nivel'] = nivel
            entrada['popularidade'] = ' · '.join(fontes) or 'sem medição'
        creditos[rel] = entrada
    # Apagar as repetidas é por caminho, e o caminho de uma repetida pode ser exatamente onde a
    # vencedora acabou de ser gravada: quando a versão nova ganha de uma que já estava no
    # acervo, ela é movida POR CIMA do arquivo antigo. Apagar aí destruiria a vencedora — foi
    # assim que 272 músicas sumiram numa rodada, entre elas Back In Black e Highway to Hell.
    for i in repetidas:
        if i['arq'].resolve() in guardados:
            continue
        i['arq'].unlink(missing_ok=True)
    # entrada de música que não está mais na pasta não serve para nada
    existentes = {p.relative_to(DESTINO).as_posix() for p in DESTINO.rglob('*.mid')}
    creditos = {k: v for k, v in creditos.items() if k in existentes}
    # Arquivo sem crédito é falha séria: a atribuição é o que sustenta esta pasta inteira, e
    # já aconteceu de passar despercebido — o sistema de arquivos do Windows não diferencia
    # maiúsculas, então renomear "a-ha" para "A-Ha" não mexe no disco e deixa o crédito órfão,
    # que o filtro acima descartava calado. Reclame alto em vez de publicar sem atribuição.
    # a conta tem de fechar: tudo que foi escolhido tem de estar no disco no fim
    if len(existentes) != len(ficam):
        print(f'\n!! escolhi {len(ficam)} músicas mas o acervo tem {len(existentes)} arquivos — '
              f'{len(ficam) - len(existentes)} se perderam na gravação', file=sys.stderr)
    orfaos = sorted(existentes - set(creditos))
    if orfaos:
        print(f'\n!! {len(orfaos)} arquivo(s) sem crédito — ATRIBUIÇÃO INCOMPLETA:', file=sys.stderr)
        for k in orfaos[:20]:
            print(f'   {k}', file=sys.stderr)
        print('   Rode de novo; se persistir, confira APELIDOS e o nome do arquivo.', file=sys.stderr)
    arq_cred.write_text(
        json.dumps(dict(sorted(creditos.items())), ensure_ascii=False, indent=1) + '\n',
        encoding='utf-8')
    # o destino também: reorganizar deixa para trás a pasta do esquema anterior, vazia
    remover_vazias(origem)
    remover_vazias(DESTINO)
    if origem.is_dir() and not any(origem.iterdir()):
        try:
            origem.rmdir()
        except OSError:
            pass
    try:
        onde = DESTINO.relative_to(RAIZ).as_posix()
    except ValueError:
        onde = str(DESTINO)
    print(f'\npronto: {len(ficam)} músicas em {onde}/' + ('' if args.plano else '<artista>/'))
    print(f'Confira a atribuição em {onde}/creditos.json e em USO-EDUCACIONAL.md,')
    print('e rode tools/gerar_acervo.py para refazer o índice.')


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--aplicar', action='store_true', help='move e apaga de verdade')
    p.add_argument('--origem', help='pasta com os arquivos soltos')
    p.add_argument('--destino', help='pasta do acervo (padrão: musicas/bandas)')
    p.add_argument('--plano', action='store_true', help='sem subpasta por artista (folk tradicional)')
    p.add_argument('--artista', help='artista fixo, para acervo sem autor identificado')
    p.add_argument('--token', help='token do ListenBrainz (ou a variável LISTENBRAINZ_TOKEN)')
    p.add_argument('--offline', action='store_true', help='usa só o que já está em popularidade.json')
    p.add_argument('-v', '--verbose', action='store_true', help='mostra as repetidas uma a uma')
    organizar(p.parse_args())


if __name__ == '__main__':
    main()
