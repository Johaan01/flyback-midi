#!/usr/bin/env python3
"""Baixa transcrições MIDI de rock e metal para a pasta de entrada do acervo.

    python tools/baixar_bandas.py                          # só lista o que acharia
    python tools/baixar_bandas.py --baixar                 # baixa de verdade
    python tools/baixar_bandas.py --fonte zeppelin --baixar
    python tools/baixar_bandas.py --fonte midiworld --busca "ac dc" metallica --baixar

Quatro fontes, todas de acesso livre e sem cadastro:

  midiworld    https://www.midiworld.com/search/?q=...   busca paginada; cada resultado é
               "Título (Artista) - download". Não há página por artista — as que parecem
               existir devolvem a home —, então a varredura é por termo de busca.
  zeppelin     https://zeppelinmidi.com/                 páginas por disco, cada uma com
               links para midi/*.mid. Tudo é Led Zeppelin.
  maiden       https://maidenmidi.com/                   mesma forma, em im-midis/*.mid.
               Tudo é Iron Maiden.
  folkrusso    https://www.freesheetmusic.net/russian.html   uma página só, com o acervo de
               folk russo e soviético: Kalinka, Katyusha, Korobeiniki, Ochi Chornye, Troika.
               Fica fora de `--fonte todas` porque tem destino próprio:

                   --fonte folkrusso --destino "musicas/folk russo (unsorted)" --baixar

Os arquivos caem em `musicas/rock e metal (unsorted)/` com o nome "Artista - Título.mid", que
é o formato que `tools/organizar_bandas.py` sabe ler, e o endereço de origem de cada um fica
registrado em `_origem.json`, na mesma pasta — é dele que sai a atribuição ao site que publicou
a transcrição. O caminho completo é:

    baixar_bandas.py --baixar   →   organizar_bandas.py --aplicar   →   gerar_acervo.py

Educação: estas são transcrições feitas por fãs de obras ainda protegidas. O repositório as
mantém com atribuição ao artista e ao transcritor, para estudo e demonstração sem fins
lucrativos — veja USO-EDUCACIONAL.md na raiz. Quem baixa responde pelo uso que faz.

A varredura é devagar de propósito: uma chamada por segundo por padrão, com identificação no
User-Agent. Não aumente a toque de caixa; são sites pequenos, mantidos por uma pessoa só.

Só usa a biblioteca padrão do Python.
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from organizar_bandas import titulo_bonito, normalizar_banda   # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / 'musicas' / 'rock e metal (unsorted)'
UA = 'flyback-midi/1.0 (https://github.com/Johaan01/flyback-midi) python-urllib'

# Termos usados quando não se passa --busca. O midiworld só acha por palavra solta e casa de
# forma bem literal, então vale listar a banda do jeito que ela aparece nos títulos de lá.
BUSCAS = [
    'rock', 'metal', 'acdc', 'ac dc', 'metallica', 'iron maiden', 'black sabbath',
    'led zeppelin', 'deep purple', 'ozzy', 'judas priest', 'megadeth', 'slayer',
    'pantera', 'scorpions', 'queen', 'guns n roses', 'nirvana', 'pink floyd',
    'van halen', 'aerosmith', 'kiss', 'motorhead', 'rainbow', 'dio', 'anthrax',
]

MW_ITEM = re.compile(r'^(?P<titulo>[^<>()]{2,120}?)\s*\((?P<artista>[^<>()]{1,60})\)\s*-\s*'
                     r'<a\s+href="(?P<url>[^"]*?/download/\d+)"', re.M)
LINK = re.compile(r'href="([^"#?]+)"', re.I)
RX_FAIXA = re.compile(r'^\d{1,3}[A-Za-z]?[-_]+\d{0,3}[-_]*')   # "04A-1__Black_Dog"


def url_segura(u):
    """Escapa o caminho da URL. Vários arquivos do acervo de folk têm espaço no nome
    ("pust vsegda budet solntse.mid") e o servidor devolve 404 se o espaço for cru."""
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit(
        (p.scheme, p.netloc, urllib.parse.quote(p.path, safe='/%'), p.query, p.fragment))


def abrir(url, binario=False, tentativas=3):
    url = url_segura(url)
    espera = 2.0
    for n in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                dados = r.read()
            return dados if binario else dados.decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code in (404, 403, 410) or n == tentativas - 1:
                raise                       # link morto não melhora com insistência
        except (urllib.error.URLError, TimeoutError) as e:
            if n == tentativas - 1:
                raise
            print(f'    (tentando de novo: {e})', file=sys.stderr)
            time.sleep(espera)
            espera *= 2
    return None


def nome_limpo(s):
    # a barra some em vez de virar hífen: "AC/DC - Thunderstruck" com hífen viraria banda "AC"
    # e título "DC - Thunderstruck" quando organizar_bandas.py fosse ler o nome de volta.
    s = s.replace('/', '').replace('\\', '')
    s = re.sub(r'[:*?"<>|]', '-', s).strip(' .')
    return re.sub(r'\s{2,}', ' ', s)


def de_arquivo(caminho):
    """'midi/04A-1__Black_Dog.mid' -> 'Black Dog'."""
    base = urllib.parse.unquote(caminho.rsplit('/', 1)[-1])
    base = re.sub(r'\.(mid|midi)$', '', base, flags=re.I)
    cortado = RX_FAIXA.sub('', base)
    if len(cortado.strip(' _-')) < 2:       # o nome era só o número da faixa: fica o original
        cortado = base
    cortado = cortado.replace('_', ' ').replace('%20', ' ')
    return titulo_bonito(re.sub(r'\s{2,}', ' ', cortado).strip()) or 'sem título'


# ---------------------------------------------------------------- fontes
def do_midiworld(buscas, paginas, pausa):
    achados = []
    for termo in buscas:
        q = urllib.parse.quote(termo)
        for pg in range(1, paginas + 1):
            url = f'https://www.midiworld.com/search/{pg}/?q={q}'
            try:
                pagina = abrir(url)
            except Exception as e:
                print(f'  ! {url}: {e}', file=sys.stderr)
                break
            itens = list(MW_ITEM.finditer(pagina))
            for m in itens:
                achados.append({
                    'artista': normalizar_banda(html.unescape(m['artista']).strip()),
                    'titulo': titulo_bonito(html.unescape(m['titulo']).strip()),
                    'url': html.unescape(m['url']),
                })
            print(f'  midiworld "{termo}" página {pg}: {len(itens)}')
            time.sleep(pausa)
            if len(itens) < 15:                 # página curta: acabou o resultado
                break
    return achados


# O acervo russo traz o mesmo tema transliterado de vários jeitos — "two guitars", "dve gitari"
# e "dwje gitary" são a mesma música, assim como "moscow evenings", "pod moskovniye vechera" e
# "padmoskownye vjetsjera". Sem juntar isso o acervo fica com a mesma canção três vezes, e com
# nomes que ninguém procura. A chave é o nome do arquivo, sem extensão.
FOLK_RUSSO = {
    'kalinka': 'Kalinka',
    'katyusha': 'Katyusha',
    'korobochka': 'Korobeiniki',
    'troika': 'Troika',
    'kamarynska': 'Kamarinskaya',
    'barinya': 'Barynya',
    'lezginka': 'Lezginka',
    'metelitsa': 'Metelitsa',
    'khorovod': 'Khorovod',
    'kasatsjok': 'Kazachok',
    'chastushky': 'Chastushki',
    'walenki': 'Valenki',
    'snowstorm': 'Metelitsa (Nevasca)',
    'ochi chorniya': 'Ochi Chornye', 'black eyes': 'Ochi Chornye', 'schwarze augen': 'Ochi Chornye',
    'two guitars': 'Dve Gitary', 'dve gitari': 'Dve Gitary', 'dwje gitary': 'Dve Gitary',
    'moscow evenings': 'Podmoskovnye Vechera', 'pod moskovniye vechera': 'Podmoskovnye Vechera',
    'padmoskownye vjetsjera': 'Podmoskovnye Vechera', 'midnight in moscow': 'Podmoskovnye Vechera',
    'pust vsegda budet solntse': 'Pust Vsegda Budet Solntse',
    'let there always be sunshine': 'Pust Vsegda Budet Solntse',
    'uralskaya ryabinushka': 'Uralskaya Ryabinushka', 'ural rowan tree': 'Uralskaya Ryabinushka',
    'uralin pihlaja': 'Uralskaya Ryabinushka',
    'otsveli hrizantemy': 'Otsveli Hrizantemy',
    'chrysanthemums were blooming': 'Otsveli Hrizantemy',
    'odinokaya garmon': 'Odinokaya Garmon', 'lonely accordion': 'Odinokaya Garmon',
    'in the manchurian hills': 'Na Sopkah Manchzhurii',
    'mantsurian kukkuloilla': 'Na Sopkah Manchzhurii',
    'bublichki': 'Bublichki', 'pretzels': 'Bublichki',
    'bielo litza kruglolitza': 'Belolitsa Kruglolitsa',
    'bielolitza kruglolitza': 'Belolitsa Kruglolitsa',
    'dorogoy dalnoyu': 'Dorogoi Dlinnoyu',
    'yamshchik ne goni loshadey': 'Yamshchik, ne Goni Loshadey',
    'vo sadu ly v ohorode': 'Vo Sadu Li, v Ogorode',
    'otce nash': 'Otche Nash', 'pater noster': 'Otche Nash',
    'in the city garden': 'V Gorodskom Sadu',
    'ozhidanie expectation waltz': 'Ozhidanie', 'ozhidanie': 'Ozhidanie',
    'toska po rodina mot barrikaderna': 'Toska po Rodine',
    'mot barrikaderna toska po rodina': 'Toska po Rodine',
    'toska po rodina': 'Toska po Rodine', 'mot barrikaderna': 'Toska po Rodine',
    'round dance': 'Khorovod',
    'russian sher': 'Russian Sher',
}


def de_pagina_unica(url, prefixo, artista, pausa, nomes=None):
    """Uma página só, com os .mid listados nela — é a forma do acervo de folk do FreeSheetMusic."""
    try:
        corpo = abrir(url)
    except Exception as e:
        print(f'  ! {url}: {e}', file=sys.stderr)
        return []
    achados, vistos = [], set()
    for h in LINK.findall(corpo):
        if not h.lower().endswith(('.mid', '.midi')) or (prefixo and prefixo not in h.lower()):
            continue
        alvo = urllib.parse.urljoin(url, h)
        base = urllib.parse.unquote(h.rsplit('/', 1)[-1]).rsplit('.', 1)[0].lower().strip()
        titulo = (nomes or {}).get(base) or de_arquivo(h)
        chave_item = titulo.casefold()
        if alvo in vistos or chave_item in vistos:
            continue
        vistos.add(alvo)
        vistos.add(chave_item)      # transliteração diferente do mesmo tema não entra duas vezes
        achados.append({'artista': artista, 'titulo': titulo, 'url': alvo})
    print(f'  {url.rsplit("/", 1)[-1]}: {len(achados)}')
    time.sleep(pausa)
    return achados


def de_site_por_disco(base, pasta_midi, artista, pausa):
    """zeppelinmidi e maidenmidi: a home lista as páginas de disco, cada uma lista os .mid."""
    try:
        home = abrir(base)
    except Exception as e:
        print(f'  ! {base}: {e}', file=sys.stderr)
        return []
    paginas = []
    for h in LINK.findall(home):
        if h.lower().endswith(('.html', '.htm')) and '//' not in h:
            if h not in paginas:
                paginas.append(h)
    achados, vistos = [], set()
    for p in paginas:
        url = urllib.parse.urljoin(base, p)
        try:
            corpo = abrir(url)
        except Exception as e:
            print(f'  ! {url}: {e}', file=sys.stderr)
            continue
        n = 0
        for h in LINK.findall(corpo):
            if not h.lower().endswith(('.mid', '.midi')):
                continue
            if pasta_midi and pasta_midi not in h.lower():
                continue
            alvo = urllib.parse.urljoin(url, h)
            if alvo in vistos:
                continue
            vistos.add(alvo)
            achados.append({'artista': artista, 'titulo': de_arquivo(h), 'url': alvo})
            n += 1
        if n:
            print(f'  {p}: {n}')
        time.sleep(pausa)
    return achados


FONTES = {
    'midiworld': lambda a: do_midiworld(a.busca or BUSCAS, a.paginas, a.pausa),
    'zeppelin': lambda a: de_site_por_disco('https://zeppelinmidi.com/', 'midi/', 'Led Zeppelin', a.pausa),
    'maiden': lambda a: de_site_por_disco('https://maidenmidi.com/', 'im-midis/', 'Iron Maiden', a.pausa),
    'folkrusso': lambda a: de_pagina_unica('https://www.freesheetmusic.net/russian.html',
                                           '/music/worldfolk/russian/', 'Tradicional russo',
                                           a.pausa, FOLK_RUSSO),
}
# 'todas' é o que se quer para encher a pasta de bandas; o folk russo tem destino próprio e por
# isso fica de fora, rodado à parte com --fonte folkrusso --destino "musicas/folk russo (…)".
PADRAO = ['midiworld', 'zeppelin', 'maiden']
# De onde veio cada arquivo. `organizar_bandas.py` lê este manifesto e copia o endereço para o
# creditos.json, para que a atribuição aponte para quem publicou a transcrição — sem isso o
# crédito morreria junto com a pasta de entrada, que é apagada quando tudo dela é arrumado.
MANIFESTO = '_origem.json'


def gravar_manifesto(itens):
    arq = DESTINO / MANIFESTO
    antes = {}
    if arq.is_file():
        try:
            antes = json.loads(arq.read_text(encoding='utf-8'))
        except ValueError:
            pass
    for a in itens:
        # guarda o nome como a fonte escreveu: "10cc" e "ABC" não sobrevivem a um .title()
        antes[a['arquivo']] = {'url': a['url'], 'site': urllib.parse.urlparse(a['url']).netloc,
                               'artista': a['artista'], 'titulo': a['titulo']}
    arq.write_text(json.dumps(dict(sorted(antes.items())), ensure_ascii=False, indent=1) + '\n',
                   encoding='utf-8')
    return len(antes)


# ---------------------------------------------------------------- principal
def executar(args):
    global DESTINO
    if args.destino:
        d = Path(args.destino)
        DESTINO = d if d.is_absolute() else (RAIZ / d)
    fontes = PADRAO if args.fonte == 'todas' else [args.fonte]
    DESTINO.mkdir(parents=True, exist_ok=True)
    ja_tem = {p.name.lower() for p in DESTINO.glob('*')}

    achados = []
    for f in fontes:
        print(f'\n--- {f} ---')
        achados += FONTES[f](args)

    # mesma música em mais de uma fonte, ou o mesmo link repetido
    unicos, vistos = [], set()
    for a in achados:
        a['arquivo'] = nome_limpo(f'{a["artista"]} - {a["titulo"]}') + '.mid'
        k = a['arquivo'].lower()
        if k in vistos or a['url'] in {u['url'] for u in unicos}:
            continue
        vistos.add(k)
        unicos.append(a)
    novos = [a for a in unicos if a['arquivo'].lower() not in ja_tem]
    if args.limite:
        novos = novos[:args.limite]

    quantos = gravar_manifesto(unicos)
    print(f'\n{len(achados)} links, {len(unicos)} distintos, '
          f'{len(unicos) - len(novos)} já estão na pasta, {len(novos)} a baixar')
    print(f'origem de {quantos} arquivos registrada em {MANIFESTO}')
    for a in novos[:30]:
        print(f'   {a["arquivo"]}')
    if len(novos) > 30:
        print(f'   … e mais {len(novos) - 30}')

    if not args.baixar:
        print('\nnada foi baixado. Rode com --baixar para valer.')
        return

    ok = ruins = 0
    for k, a in enumerate(novos, 1):
        destino = DESTINO / a['arquivo']
        try:
            dados = abrir(a['url'], binario=True)
        except Exception as e:
            print(f'  ! {a["arquivo"]}: {e}', file=sys.stderr)
            ruins += 1
            continue
        # tem de ser MIDI de verdade: o site pode devolver uma página de erro com status 200
        if not dados or b'MThd' not in dados[:2048] or len(dados) < 64:
            print(f'  ! {a["arquivo"]}: não é um MIDI ({len(dados or b"")} bytes)', file=sys.stderr)
            ruins += 1
            continue
        destino.write_bytes(dados)
        ok += 1
        if k % 10 == 0 or k == len(novos):
            print(f'  {k}/{len(novos)}…')
        time.sleep(args.pausa)

    try:
        onde = DESTINO.relative_to(RAIZ)
    except ValueError:
        onde = DESTINO
    print(f'\n{ok} baixados, {ruins} recusados, em {onde}')
    if ok:
        print('Agora rode: python tools/organizar_bandas.py --aplicar')


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--fonte', choices=list(FONTES) + ['todas'], default='todas')
    p.add_argument('--destino', help='pasta de entrada (padrão: musicas/rock e metal (unsorted))')
    p.add_argument('--busca', nargs='*', help='termos para o midiworld (padrão: lista embutida)')
    p.add_argument('--paginas', type=int, default=3, help='páginas de busca por termo (padrão 3)')
    p.add_argument('--limite', type=int, default=0, help='no máximo tantos arquivos nesta rodada')
    p.add_argument('--pausa', type=float, default=1.0, help='segundos entre chamadas (padrão 1,0)')
    p.add_argument('--baixar', action='store_true', help='baixa de verdade')
    executar(p.parse_args())


if __name__ == '__main__':
    main()
