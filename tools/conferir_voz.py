"""Quanto do canto da gravação tem nota na faixa de voz do MIDI.

    python tools/conferir_voz.py musica.wav "musicas/transcritas/AC-DC - Thunderstruck.mid"
    python tools/conferir_voz.py musica.wav a.mid b.mid --json saida.json

O auditor da montagem (auditar_montagem.py) vê o que o site deixa de tocar do MIDI; isto vê o
que o MIDI deixou de transcrever da gravação. Thunderstruck foi o caso: o dono do projeto ouviu
"quase metade" das vozes faltando, e era isso mesmo — a faixa de voz cobria 45% do canto. Os
gritos "Thunder!" e o "ah-ah" do coro, sem altura clara, não tinham virado nota. Refeita com a
lista certa (voz, guitarra distorcida, baixo, bateria) e orientação 2, cobre 65%.

O canto vem do stem de voz do Demucs (o mesmo `separar` do transcrever.py): quadro de 50 ms
acima de -30 dB do pico, e só conta trecho que se sustenta meio segundo. Reverberação de grito
e respiração entram como canto, então 100% não é a meta: a versão boa de Thunderstruck dá 65%.
Abaixo de 60% vale ouvir.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from curar_acervo import ler_midi  # noqa: E402

QUADRO = .05
LIMITE = 60          # % do canto com nota abaixo do qual a música merece ser ouvida


def canto(arquivo, dispositivo='cuda'):
    """Máscara de quadros de QUADRO s em que há canto na gravação."""
    import transcrever as T
    stems, sr = T.separar(arquivo, dispositivo)
    voz = stems['vocals']
    n = int(sr * QUADRO)
    q = len(voz) // n
    rms = np.sqrt((voz[:q * n].reshape(q, n) ** 2).mean(1) + 1e-12)
    ativo = 20 * np.log10(rms / np.percentile(rms, 95)) > -30
    k = int(.5 / QUADRO)
    return np.convolve(ativo.astype(int), np.ones(k), 'same') >= k * .6


def cobertura(mascara, midi):
    """(% do canto com nota na faixa de voz, segundos sem nota, trechos de 2 s ou mais sem nota)."""
    q = len(mascara)
    tem = np.zeros(q, bool)
    for t in ler_midi(Path(midi).read_bytes()):
        if t.nome.strip().lower() in ('voice', 'vocal', 'voz'):
            for a, b, *_ in t.notas:
                tem[int(a / QUADRO):int(np.ceil(b / QUADRO))] = True
    falta = mascara & ~tem
    trechos, ini = [], None
    for i, f in enumerate(np.append(falta, False)):
        if f and ini is None:
            ini = i
        if not f and ini is not None:
            if (i - ini) * QUADRO >= 2:
                trechos.append((round(ini * QUADRO, 1), round(i * QUADRO, 1)))
            ini = None
    pct = round(100 * (mascara & tem).sum() / max(1, mascara.sum()))
    return pct, round(falta.sum() * QUADRO), trechos


def mmss(s):
    return f'{int(s // 60)}:{int(s % 60):02d}'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('audio', help='a gravação (wav, mp3…)')
    ap.add_argument('midis', nargs='+', help='MIDI com faixa "voice"')
    ap.add_argument('--cpu', action='store_true', help='separar sem a GPU')
    ap.add_argument('--json', help='gravar o resultado num .json')
    args = ap.parse_args()
    m = canto(args.audio, 'cpu' if args.cpu else 'cuda')
    print(f'canto na gravação: {m.sum() * QUADRO:.0f} s de {len(m) * QUADRO:.0f} s')
    out = {}
    for midi in args.midis:
        pct, falta, trechos = cobertura(m, midi)
        out[midi] = {'cobre': pct, 'falta_s': falta, 'trechos': trechos}
        print(f'{Path(midi).name}: a faixa de voz cobre {pct}% do canto; {falta} s sem nota'
              + (f'  ← abaixo de {LIMITE}%, vale ouvir' if pct < LIMITE else ''))
        if trechos:
            print('  sem nota: ' + ', '.join(f'{mmss(a)}–{mmss(b)}' for a, b in trechos))
    if args.json:
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
