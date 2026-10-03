"""Mede quanto de cada música do acervo cabe em 2 e em 6 flybacks, e grava no creditos.json.

    python tools/medir_canais.py             # mostra o que mudaria
    python tools/medir_canais.py --aplicar   # grava

Duas notas por música, de 0 a 100:

- `aproveitamento`: em 2 canais, pelo preset "melodia inteira, resto sem atropelo". É a medida
  de sempre, calibrada pelo ouvido do dono do projeto — Na Gruta do Rei da Montanha 83% e
  Korobeiniki 61% soam excelentes, Back in Black 34% soa pobre — e o site corta em 58.
- `aproveitamento6`: em 6 canais, pelo preset "um instrumento por flyback" (`aproveitamento_n`
  em curar_acervo.py, que explica por que os termos são outros). Corte provisório em 62, até
  haver seis flybacks para ouvir: deixa dentro as transcrições do MuScriptor (64 a 75) e os
  arranjos do projeto (77 a 87), e fora a de Back in Black de fã, cheia de acorde (58).

Até aqui só `bandas` e `transcritas` tinham a primeira nota. Os 590 clássicos, o folk russo e
os exemplos não tinham nenhuma, e com o filtro "só as que soam bem" ligado sumiam da lista
inteiros — inclusive os bons. Esta ferramenta mede tudo.

Música que não está no creditos.json da pasta ganha uma entrada só com as notas. Guitar Pro e
MusicXML ficam de fora: são lidos pelo AlphaTab, no navegador, e não pelo leitor daqui.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from curar_acervo import ler_midi, aproveitamento, aproveitamento_n  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
ACERVO = RAIZ / 'musicas'
MIDI = {'.mid', '.midi', '.kar', '.rmi'}
CORTE2, CORTE6 = 58, 62


def pasta_de_creditos(arq):
    """O creditos.json que responde por este arquivo: o da pasta mais próxima, subindo."""
    for p in arq.parents:
        if (p / 'creditos.json').is_file():
            return p
        if p == ACERVO:
            break
    return arq.parent


def notas(arq):
    faixas = ler_midi(arq.read_bytes())
    fins = [t1 for f in faixas for _, t1, _ in f.notas]
    if not fins:
        return None
    dur = max(fins) + .3
    return round(aproveitamento(faixas, dur) * 100), round(aproveitamento_n(faixas, dur, 6) * 100)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--aplicar', action='store_true', help='gravar nos creditos.json')
    ap.add_argument('--refazer', action='store_true', help='medir de novo o que já tem as duas notas')
    args = ap.parse_args()

    arquivos = sorted(p for p in ACERVO.rglob('*') if p.suffix.lower() in MIDI
                      and not any(parte.endswith('(unsorted)') or parte == 'unsorted' for parte in p.parts))
    creditos, mudou = {}, 0
    contagem = {'2 e 6': 0, 'só 6': 0, 'nenhum': 0}
    falhas = []
    for i, arq in enumerate(arquivos, 1):
        base = pasta_de_creditos(arq)
        if base not in creditos:
            c = base / 'creditos.json'
            creditos[base] = json.loads(c.read_text(encoding='utf-8')) if c.is_file() else {}
        dados = creditos[base]
        chave = arq.relative_to(base).as_posix()
        ent = dados.get(chave, {})
        if not args.refazer and 'aproveitamento' in ent and 'aproveitamento6' in ent:
            a2, a6 = ent['aproveitamento'], ent['aproveitamento6']
        else:
            try:
                r = notas(arq)
            except Exception as e:      # arquivo corrompido não pode parar a medição do resto
                falhas.append(f'{arq.relative_to(ACERVO)}: {e}')
                continue
            if r is None:
                continue
            a2, a6 = r
            if ent.get('aproveitamento') != a2 or ent.get('aproveitamento6') != a6:
                ent = dict(ent, aproveitamento=a2, aproveitamento6=a6)
                dados[chave] = ent
                mudou += 1
        contagem['2 e 6' if a2 >= CORTE2 else 'só 6' if a6 >= CORTE6 else 'nenhum'] += 1
        if i % 100 == 0:
            print(f'  {i} de {len(arquivos)}…', flush=True)

    print(f'\n{len(arquivos)} MIDIs: {contagem["2 e 6"]} soam bem já em 2 flybacks, '
          f'{contagem["só 6"]} só com 6, {contagem["nenhum"]} em nenhum dos dois')
    for f in falhas:
        print('  não li', f)
    if not args.aplicar:
        print(f'{mudou} entradas mudariam. Rode com --aplicar para gravar.')
        return
    for base, dados in creditos.items():
        (base / 'creditos.json').write_text(json.dumps(dados, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{mudou} entradas gravadas em {len(creditos)} creditos.json.')


if __name__ == '__main__':
    main()
