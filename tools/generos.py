"""Preenche o gênero (campo 'estilo') das músicas de banda e das transcritas, pelo MusicBrainz.

    python tools/generos.py             # mostra o que acharia
    python tools/generos.py --aplicar   # grava nos creditos.json

Os clássicos já têm estilo (período: barroco, clássico, romântico) vindo do Mutopia. Bandas e
transcritas não tinham nenhum, e o filtro de gênero do site ficaria vazio. Uma consulta por
artista (o MusicBrainz pede no máximo uma por segundo), com a primeira música dele junto para
desambiguar — nome sozinho é ambíguo: "Coda" achava um produtor de eletrônica, não o cantor de
BLOODY STREAM. Os gêneros são agrupados em poucos nomes (GENEROS em lote.py).

Artista que o MusicBrainz não classifica fica sem gênero, a menos que esteja em MANUAL.
Música que já tem 'estilo' não é tocada.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lote import artista_mb  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
PASTAS = ['bandas', 'transcritas']
# o que o MusicBrainz não classifica e se sabe com segurança
MANUAL = {'coda': 'Anime', 'baitaca': 'Gaúcha', 'purcell henry': 'Baroque',
          'nintendo': 'Trilha sonora', 'jun ishikawa, dan miyakawa': 'Trilha sonora',
          'disney themes': 'Trilha sonora', 'movie themes': 'Trilha sonora', 'tv themes': 'Trilha sonora',
          # grafados de outro jeito no MusicBrainz ("Daryl Hall & John Oates")
          'hall and oates': 'Pop', 'bill haley and the comets': 'Rock', 'presidents of the usa': 'Rock',
          '1910 fruitgum company': 'Pop', 'all 4 one': 'Soul', 'manhattans': 'Soul', 'desree': 'Soul',
          'marusha': 'Eletrônica', 'dave rodgers': 'Eletrônica'}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--aplicar', action='store_true', help='gravar nos creditos.json')
    args = ap.parse_args()

    creditos = {p: json.loads((RAIZ / 'musicas' / p / 'creditos.json').read_text(encoding='utf-8')) for p in PASTAS}
    por_artista = {}
    for p, dados in creditos.items():
        for arq, e in dados.items():
            nome = e.get('artista') or e.get('autor')
            if nome and not e.get('estilo'):
                musica = Path(arq).stem.split(' - ', 1)[-1]
                por_artista.setdefault(nome, []).append((p, arq, musica))

    print(f'{len(por_artista)} artistas sem gênero; consultando o MusicBrainz…', flush=True)
    achados, contagem = {}, Counter()
    for i, (nome, musicas) in enumerate(sorted(por_artista.items()), 1):
        _, estilo = artista_mb(nome, musicas[0][2])
        estilo = estilo or MANUAL.get(nome.lower())
        achados[nome] = estilo
        contagem[estilo or '(sem gênero)'] += len(musicas)
        print(f'  [{i}/{len(por_artista)}] {nome}: {estilo or "—"}', flush=True)

    print('\nmúsicas por gênero:', ', '.join(f'{k} {v}' for k, v in contagem.most_common()))
    if not args.aplicar:
        print('Rode com --aplicar para gravar.')
        return
    for nome, musicas in por_artista.items():
        if achados.get(nome):
            for p, arq, _ in musicas:
                creditos[p][arq]['estilo'] = achados[nome]
    for p, dados in creditos.items():
        (RAIZ / 'musicas' / p / 'creditos.json').write_text(json.dumps(dados, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print('gravado.')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
