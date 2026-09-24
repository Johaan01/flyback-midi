#!/usr/bin/env python3
"""Gera musicas/index.json, a lista que o site usa para mostrar o acervo.

O GitHub Pages não lista pastas, então o site precisa desse índice. O workflow
de publicação roda este script a cada envio; localmente, tools/servir.py
também roda. Só usa a biblioteca padrão do Python.

Regras:
  - entram arquivos .mid .midi .kar .rmi .gp .gp3 .gp4 .gp5 .gpx .musicxml .mxl
  - subpastas viram grupos no acervo (musicas/exemplos/... aparece em "exemplos")
  - um .json com o mesmo nome da música é a configuração pronta dela
    (roteamento e canais), baixada pelo botão "Baixar configuração" do site
  - arquivos e pastas começados por ponto são ignorados
"""
import json
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / 'musicas'
TIPOS = {
    '.mid': 'MIDI', '.midi': 'MIDI', '.kar': 'MIDI', '.rmi': 'MIDI',
    '.gp': 'GP', '.gp3': 'GP', '.gp4': 'GP', '.gp5': 'GP', '.gpx': 'GP',
    '.musicxml': 'XML', '.mxl': 'XML',
}


def sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if not unicodedata.combining(c)).casefold()


def gerar():
    itens = []
    if PASTA.is_dir():
        for arq in PASTA.rglob('*'):
            rel = arq.relative_to(PASTA)
            if not arq.is_file() or arq.suffix.lower() not in TIPOS:
                continue
            if any(p.startswith('.') for p in rel.parts):
                continue
            cfg = arq.with_suffix('.json')
            pasta = rel.parent.as_posix()
            itens.append({
                'arquivo': rel.as_posix(),
                'titulo': unicodedata.normalize('NFC', arq.stem.replace('_', ' ').strip()) or arq.name,
                'tipo': TIPOS[arq.suffix.lower()],
                'pasta': '' if pasta == '.' else pasta,
                'config': cfg.relative_to(PASTA).as_posix() if cfg.is_file() else None,
                'bytes': arq.stat().st_size,
            })
    itens.sort(key=lambda i: (i['pasta'] != '', sem_acento(i['pasta']), sem_acento(i['titulo'])))
    PASTA.mkdir(exist_ok=True)
    dados = {'gerado': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'musicas': itens}
    (PASTA / 'index.json').write_text(json.dumps(dados, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return itens


if __name__ == '__main__':
    itens = gerar()
    print(f'{len(itens)} músicas em musicas/index.json')
    for i in itens:
        print(f"  {i['tipo']:4} {i['arquivo']}" + ('  (com configuração)' if i['config'] else ''))
    sys.exit(0)
