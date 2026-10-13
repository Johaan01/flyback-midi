#!/usr/bin/env python3
"""Traz para musicas/classicos as obras orquestrais famosas do PDMX, com 6 partes ou mais.

    python tools/baixar_pdmx.py              (baixa o que faltar e grava no acervo)
    python tools/baixar_pdmx.py --medir      (só mede a seleção, sem gravar)

Por que existe: os clássicos do Mutopia eram quase todos de piano ou de um instrumento solo —
218 de 590 com duas partes, 127 com uma —, e o site toca seis flybacks. O dono do projeto pediu
"músicas conhecidas com uma carga de instrumentos melhor distribuída": Ode à Alegria, as
sinfonias, Mozart, Bach, Wagner. O Mutopia não tem mais isso a dar (as 21 peças dele que ficaram
são o que havia de orquestral e conhecido).

O PDMX (Long et al., 2024; zenodo.org/records/15571083) junta 254 mil partituras do MuseScore
que os autores marcaram como domínio público ou CC0, com o MIDI de cada uma e o metadado do site:
partes, favoritos, nota dos usuários, autor da partitura. A licença da edição é livre; a obra é
de compositor morto há mais de 70 anos (Prokofiev, o mais recente, em 1953). O dataset em si é
CC BY, então o crédito do PDMX vai junto com o do autor de cada partitura.

A escolha é manual, em SELECAO: para cada obra conhecida, a partitura de mais favoritos e boa
nota que seja para orquestra (não banda marcial, coro de clarinetes ou percussão). Arquivos que o
Mutopia já dava com orquestra inteira (5ª de Beethoven, Novo Mundo, Aleluia, Flauta Mágica) não
entram de novo.

O catálogo (225 MB), os MIDIs (214 MB) e os metadados (159 MB) ficam em ~/pdmx.
"""
import argparse
import io
import json
import sys
import tarfile
import unicodedata
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / 'tools'))
from curar_acervo import ler_midi, aproveitamento, aproveitamento_n  # noqa: E402

DESTINO = RAIZ / 'musicas' / 'classicos'
CACHE = Path.home() / 'pdmx'
ZENODO = 'https://zenodo.org/records/15571083/files/'
ARQUIVOS = ('PDMX.csv', 'mid.tar.gz', 'metadata.tar.gz')
CREDITO_PDMX = 'PDMX (Long et al., 2024), CC BY 4.0'

AA, IT, FR, RU, NO, UK = ('Alemanha e Áustria', 'Itália', 'França', 'Rússia e Leste Europeu',
                          'Nórdicos e Países Baixos', 'Ilhas Britânicas')
# (título no PDMX, começo do título basta; região; pasta do compositor; nome no acervo; estilo)
SELECAO = [
    ('Ode to Joy (for orchestra)', AA, 'Beethoven (L. V.)', 'Symphony No. 9 - Ode to Joy (theme)', 'Classical'),
    ('Beethoven - Symphony No. 9 - Movement IV', AA, 'Beethoven (L. V.)', 'Symphony No. 9 (Op. 125) - IV. Finale', 'Classical'),
    ('Symphony No.7 in A major op.92 - II Allegretto', AA, 'Beethoven (L. V.)', 'Symphony No. 7 (Op. 92) - II. Allegretto', 'Classical'),
    ('Opus 68a Symphony VI Sinfonia Pastorale - The First Movement', AA, 'Beethoven (L. V.)', 'Symphony No. 6, Pastoral (Op. 68) - I. Allegro ma non troppo', 'Classical'),
    ('beethoven ouverture egmont 84', AA, 'Beethoven (L. V.)', 'Egmont Overture (Op. 84)', 'Classical'),
    ('Mozart - Symphony No.40 in G minor K.550 Movement 1', AA, 'Mozart (W. A.)', 'Symphony No. 40 (KV 550) - I. Molto allegro', 'Classical'),
    ('Eine kleine Nachtmusik - W.-A. Mozart', AA, 'Mozart (W. A.)', 'Eine kleine Nachtmusik (KV 525) - I. Allegro', 'Classical'),
    ('Requiem in D Minor K. 626 III. Sequentia: Lacrimosa', AA, 'Mozart (W. A.)', 'Requiem (KV 626) - Lacrimosa', 'Classical'),
    ('The Marriage of Figaro Overture', AA, 'Mozart (W. A.)', 'The Marriage of Figaro - Overture (KV 492)', 'Classical'),
    ('Alla turca (Rondo K.331 - Mozart)', AA, 'Mozart (W. A.)', 'Rondo alla Turca (KV 331), para orquestra', 'Classical'),
    ('Mozart: Piano Concerto No. 21 in C Major K. 467 - II. Anda', AA, 'Mozart (W. A.)', 'Piano Concerto No. 21 (KV 467) - II. Andante', 'Classical'),
    ('Bach - Brandenburg Concerto No. 3', AA, 'Bach (J. S.)', 'Brandenburg Concerto No. 3 (BWV 1048) - I. Allegro', 'Baroque'),
    ("Jesu Joy of Man's Desiring - Jesus Bleibet Meine Freude", AA, 'Bach (J. S.)', "Jesu, Joy of Man's Desiring (BWV 147)", 'Baroque'),
    ('Air on the G String', AA, 'Bach (J. S.)', 'Air on the G String (BWV 1068)', 'Baroque'),
    ('Wagner Richard: Das Brautlied aus Lohengrin', AA, 'Wagner (R.)', 'Lohengrin - Bridal Chorus', 'Romantic'),
    ('Tannhäuser - Ouverture (extrait)', AA, 'Wagner (R.)', 'Tannhäuser - Overture (excerpt)', 'Romantic'),
    ('VIVALDI La Primavera', IT, 'Vivaldi (A.)', 'The Four Seasons - Spring (RV 269) - I. Allegro', 'Baroque'),
    ("L'Inverno (Winter) by Antonio Vivaldi", IT, 'Vivaldi (A.)', 'The Four Seasons - Winter (RV 297)', 'Baroque'),
    ('Tchaikovsky - Dance of the sugar plum fairy', RU, 'Tchaikovsky (P. I.)', 'The Nutcracker - Dance of the Sugar Plum Fairy', 'Romantic'),
    ('Nutcracker Suite Dance of the Reed Pipes', RU, 'Tchaikovsky (P. I.)', 'The Nutcracker - Dance of the Reed Pipes', 'Romantic'),
    ('Swan Lake Op. 20 (Act II X/XIV. Scéne)', RU, 'Tchaikovsky (P. I.)', 'Swan Lake (Op. 20) - Act II, Scene', 'Romantic'),
    ('Swan Lake Op. 20 - Act II No. 13 - Dance of the Swans IV', RU, 'Tchaikovsky (P. I.)', 'Swan Lake (Op. 20) - Dance of the Little Swans', 'Romantic'),
    ('Tchaikovsky - Swan Lake Finale', RU, 'Tchaikovsky (P. I.)', 'Swan Lake (Op. 20) - Finale', 'Romantic'),
    ('In the Hall of the Mountain King', NO, 'Grieg (E.)', 'Peer Gynt - In the Hall of the Mountain King', 'Romantic'),
    ('Overture from William Tell', IT, 'Rossini (G.)', 'William Tell - Overture', 'Romantic'),
    ('The Barber of Seville Overture', IT, 'Rossini (G.)', 'The Barber of Seville - Overture', 'Romantic'),
    ('An der schönen blauen Donau/Blue Danube', AA, 'Strauss II (J.)', 'The Blue Danube (Op. 314)', 'Romantic'),
    ('Radetzky March', AA, 'Strauss I (J.)', 'Radetzky March (Op. 228)', 'Romantic'),
    ('Also Sprach Zarathustra', AA, 'Strauss (R.)', 'Also sprach Zarathustra - Sunrise', 'Romantic'),
    ('Mars', UK, 'Holst (G.)', 'The Planets - Mars', 'Modern'),
    ('Holst The Planets IV. Jupiter the Bringer of Jollity', UK, 'Holst (G.)', 'The Planets - Jupiter', 'Modern'),
    ('Habanera', FR, 'Bizet (G.)', 'Carmen - Habanera', 'Romantic'),
    ('Carmen- Votre toast', FR, 'Bizet (G.)', 'Carmen - Toreador Song', 'Romantic'),
    ('Carmen', FR, 'Bizet (G.)', 'Carmen - Prelude', 'Romantic'),
    ('Saint-Saëns - Danse Macabre Op. 40', FR, 'Saint-Saëns (C.)', 'Danse macabre (Op. 40)', 'Romantic'),
    ("Ravel's Bolero", FR, 'Ravel (M.)', 'Boléro', 'Modern'),
    ('La grande porte de Kiev', RU, 'Mussorgsky (M.)', 'Pictures at an Exhibition - The Great Gate of Kiev', 'Romantic'),
    ('Canon or Cannon in D Johann Pachelbel', AA, 'Pachelbel (J.)', 'Canon in D', 'Baroque'),
    ('La donna è mobile (from Rigoletto)', IT, 'Verdi (G.)', 'Rigoletto - La donna è mobile', 'Romantic'),
    ("Gloria all'Egitto ad Iside (Triumphal March from Aïda)", IT, 'Verdi (G.)', 'Aida - Triumphal March', 'Romantic'),
    ('Nessun dorma (from Turandot)', IT, 'Puccini (G.)', 'Turandot - Nessun dorma', 'Romantic'),
    ('La Gioconda - Danza delle ore', IT, 'Ponchielli (A.)', 'La Gioconda - Dance of the Hours', 'Romantic'),
    ('Viens Mallika...Sous le dôme épais (Flower Duet from Lakmé', FR, 'Delibes (L.)', 'Lakmé - Flower Duet', 'Romantic'),
    ('Dance of the Knights (suite 2 version)', RU, 'Prokofiev (S.)', 'Romeo and Juliet - Dance of the Knights', 'Modern'),
]


def nfc(s):
    return unicodedata.normalize('NFC', s)


def baixar():
    CACHE.mkdir(exist_ok=True)
    for nome in ARQUIVOS:
        alvo = CACHE / nome
        if not alvo.is_file() or alvo.stat().st_size == 0:
            print(f'baixando {nome} do Zenodo…', flush=True)
            tmp = alvo.with_suffix('.parcial')
            urllib.request.urlretrieve(ZENODO + nome + '?download=1', tmp)
            tmp.replace(alvo)


def do_tar(arq, caminhos):
    """{caminho: bytes} para os caminhos pedidos ('./mid/...'), numa passada só pelo .tar.gz."""
    quer = {c.lstrip('./'): c for c in caminhos}
    achou = {}
    with tarfile.open(arq) as t:
        for m in t:
            c = quer.get(m.name.lstrip('./'))
            if c:
                achou[c] = t.extractfile(m).read()
                if len(achou) == len(quer):
                    break
    return achou


def partes(faixas):
    return sum(1 for f in faixas if f.notas)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--medir', action='store_true', help='só mede a seleção, sem gravar no acervo')
    args = ap.parse_args()
    baixar()
    import pandas as pd
    d = pd.read_csv(CACHE / 'PDMX.csv', low_memory=False)
    d = d[d['mid'].notna() & (d.n_tracks >= 6)]
    linhas = []
    for titulo, *resto in SELECAO:
        m = d[d.title.fillna('').str.startswith(titulo)].sort_values('n_favorites', ascending=False)
        if titulo == 'Mars':
            m = m[m.composer_name.fillna('').str.contains('Holst', case=False)]
        if titulo == 'Habanera' or titulo == 'Carmen':
            m = m[m.composer_name.fillna('').str.contains('Bizet', case=False) & (m.title == titulo)]
        if not len(m):
            sys.exit(f'não achei no PDMX: {titulo}')
        linhas.append((m.iloc[0], *resto))
    mids = do_tar(CACHE / 'mid.tar.gz', [r['mid'] for r, *_ in linhas])
    metas = do_tar(CACHE / 'metadata.tar.gz', [r['metadata'] for r, *_ in linhas])

    arq_cred = DESTINO / 'creditos.json'
    cred = json.loads(arq_cred.read_text(encoding='utf-8')) if arq_cred.is_file() else {}
    for r, regiao, pasta, nome, estilo in linhas:
        dados = mids[r['mid']]
        faixas = ler_midi(dados)
        fins = [t1 for f in faixas for _, t1, _ in f.notas]
        dur = (max(fins) if fins else 0) + .3
        meta = json.loads(metas[r['metadata']]).get('data', {}).get('score', {})
        nomes = meta.get('parts_names') or []
        print(f'{partes(faixas):3} partes  {dur/60:5.1f} min  ap6 {aproveitamento_n(faixas, dur, 6)*100:3.0f}%  '
              f'{nome}  ←  {r.title[:50]}')
        if args.medir:
            continue
        rel = nfc(f'{regiao}/{pasta}/{nome}.mid')
        alvo = DESTINO / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_bytes(dados)
        usuario = (meta.get('user') or {}).get('name') or 'autor no MuseScore'
        cred[rel] = {
            'autor': ' '.join(reversed(pasta.rstrip(')').split(' ('))),      # 'Beethoven (L. V.)' -> 'L. V. Beethoven'
            'instrumentos': 'Orquestra: ' + ', '.join(dict.fromkeys(nomes)) if nomes else 'Orquestra',
            'estilo': estilo,
            'licenca': 'CC0' if r.license == 'cc-zero' else 'Domínio público',
            'credito': f'partitura de {usuario} no MuseScore; {CREDITO_PDMX}',
            'arranjo': '',
            'fonte': meta.get('url') or '',
            'regiao': regiao,
            'aproveitamento': round(aproveitamento(faixas, dur) * 100),
            'aproveitamento6': round(aproveitamento_n(faixas, dur, 6) * 100),
        }
    if not args.medir:
        arq_cred.write_text(json.dumps(cred, ensure_ascii=False, indent=1), encoding='utf-8')
        print(f'{len(linhas)} obras gravadas em {DESTINO}')


if __name__ == '__main__':
    main()
