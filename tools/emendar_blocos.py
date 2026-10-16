#!/usr/bin/env python3
"""Emenda os blocos congelados de uma transcrição com os mesmos blocos de outra transcrição da mesma gravação.

    python tools/emendar_blocos.py base.mid outra.mid -o saida.mid
    python tools/emendar_blocos.py base.mid --so-achar            (só lista os trechos congelados)

O MuScriptor transcreve em blocos fixos de 5 s (0-5, 5-10...). Com orientação 2 o `large` às vezes
para de escrever no meio de um bloco, e as notas abertas ficam soando até o bloco seguinte fechá-las:
em Eye of the Tiger, de 86,56 a 90,56 s, guitarra, baixo e voz seguram a mesma nota e a bateria
some — o dono do projeto ouviu "as notas virarem uma coisa contínua, com todos os instrumentos". Em
out/2026, 24 de 65 transcrições feitas assim tinham trechos de 2 a 9 s congelados.

A orientação 1 não congela, mas escreve menos canto (Back In Black: 85% do canto com 2, 61% com 1).
A emenda fica com a transcrição de orientação 2 e troca só os blocos estragados — o que parou no meio
e os seguintes até o que fechou as notas, que herdaram dele as notas abertas — pelos mesmos blocos da
outra. A nota que atravessa a borda do trecho trocado se junta com a continuação da mesma altura do
outro lado. Bloco em que a outra também congela fica como estava.

Congelado é: 1,5 s ou mais sem ataque em faixa nenhuma, com nota segurada por cima do buraco e a bateria
tocando nos 5 s antes e nos 5 s depois (no meio da música, não na introdução nem no fim). Com 1,5 s,
29 de 66 transcrições de orientação 2 tinham algum, contra 6 de 22 de orientação 1; trocar um bloco
que estava certo custa pouco, porque a outra também é transcrição do mesmo trecho.
"""
import argparse
import math
import re
import sys
from pathlib import Path

import mido

sys.path.insert(0, str(Path(__file__).resolve().parent))
from juntar_faixas import _abs, mapa, seg_para_tick, tick_para_seg  # noqa: E402

BLOCO = 5.0
BAT = re.compile(r'drum|bateri|percus|kit', re.I)


def notas(m):
    """{faixa: [(t0, t1, canal, nota, velocidade)]} em segundos, e a ordem das faixas."""
    pts, tpb = mapa(m), m.ticks_per_beat
    out, ordem = {}, []
    for k, tr in enumerate(m.tracks):
        nome = tr.name or f'faixa {k}'
        abertas, lista = {}, []
        for t, x in _abs(tr):
            if x.type == 'note_on' and x.velocity:
                abertas.setdefault((x.channel, x.note), []).append((tick_para_seg(pts, tpb, t), x.velocity))
            elif x.type in ('note_off', 'note_on') and abertas.get((x.channel, x.note)):
                t0, v = abertas[(x.channel, x.note)].pop(0)
                lista.append((t0, tick_para_seg(pts, tpb, t), x.channel, x.note, v))
        if lista:
            out[nome] = sorted(lista)
            ordem.append(nome)
    return out, ordem


def bateria(nome, lista):
    return bool(BAT.search(nome)) or any(c == 9 for _, _, c, _, _ in lista)


def congelados(faixas, minimo=1.5):
    """[(a, b)]: o último ataque antes do buraco e o primeiro depois."""
    ataques = sorted({round(t0, 3) for l in faixas.values() for t0, *_ in l})
    bat = sorted(t0 for nome, l in faixas.items() if bateria(nome, l) for t0, *_ in l)
    out = []
    for a, b in zip(ataques, ataques[1:]):
        if b - a < minimo:
            continue
        segura = any(t0 <= a + 1e-3 and t1 >= b - .05 for nome, l in faixas.items() if not bateria(nome, l)
                     for t0, t1, *_ in l)
        antes = sum(1 for t in bat if a - 5 <= t <= a)
        depois = sum(1 for t in bat if b <= t <= b + 5)
        if segura and antes >= 4 and depois >= 4:
            out.append((a, b))
    return out


def janelas(cong):
    """os blocos de 5 s do que parou no meio ao que fechou as notas, juntando os que se encostam"""
    js = sorted((BLOCO * math.floor(a / BLOCO), BLOCO * (math.floor(b / BLOCO) + 1)) for a, b in cong)
    out = []
    for a, b in js:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def emendar(base, outra, js):
    """notas da base fora das janelas e da outra dentro delas; a nota cortada na borda se junta com a
    continuação da mesma altura do outro lado"""
    res = {}
    canal_base = {nome: l[0][2] for nome, l in base.items()}
    for nome in list(base) + [n for n in outra if n not in base]:
        pedacos = []
        for t0, t1, c, n, v in base.get(nome, []):
            partes = [(t0, t1)]
            for a, z in js:
                novas = []
                for x0, x1 in partes:
                    if x1 <= a or x0 >= z:
                        novas.append((x0, x1))
                    else:
                        if x0 < a:
                            novas.append((x0, a))
                        if x1 > z:
                            novas.append((z, x1))
                partes = novas
            pedacos += [(x0, x1, c, n, v) for x0, x1 in partes if x1 - x0 > .005]
        c_base = canal_base.get(nome)
        for t0, t1, c, n, v in outra.get(nome, []):
            for a, z in js:
                x0, x1 = max(t0, a), min(t1, z)
                if x1 - x0 > .005:
                    pedacos.append((x0, x1, c if c_base is None else c_base, n, v))
        bordas = [x for j in js for x in j]
        pedacos.sort(key=lambda x: (x[3], x[0]))
        juntos = []
        for x in pedacos:
            y = juntos[-1] if juntos else None
            if y and y[3] == x[3] and abs(y[1] - x[0]) < 1e-6 and any(abs(x[0] - b) < 1e-6 for b in bordas):
                juntos[-1] = (y[0], x[1], y[2], y[3], y[4])
            else:
                juntos.append(x)
        res[nome] = sorted(juntos)
    return res


def escrever(base_mid, outra_mid, res, saida):
    """a base com as notas trocadas: o resto de cada faixa (nome, programa, andamento) fica como estava"""
    pts, tpb = mapa(base_mid), base_mid.ticks_per_beat
    novo = mido.MidiFile(type=base_mid.type, ticks_per_beat=tpb)
    feitas = set()

    def faixa(tr, nome, origem):
        po, otpb = mapa(origem), origem.ticks_per_beat
        evs = []
        for t, x in _abs(tr):
            if x.type in ('note_on', 'note_off', 'end_of_track'):
                continue
            tt = t if origem is base_mid else seg_para_tick(pts, tpb, tick_para_seg(po, otpb, t))
            evs.append((tt, 1, x))
        for t0, t1, c, n, v in res.get(nome, []):
            evs.append((seg_para_tick(pts, tpb, t0), 2, mido.Message('note_on', channel=c, note=n, velocity=v)))
            evs.append((seg_para_tick(pts, tpb, t1), 0, mido.Message('note_off', channel=c, note=n, velocity=0)))
        evs.sort(key=lambda e: (e[0], e[1]))
        out, ant = mido.MidiTrack(), 0
        for t, _, x in evs:
            out.append(x.copy(time=t - ant))
            ant = t
        out.append(mido.MetaMessage('end_of_track', time=0))
        return out

    for k, tr in enumerate(base_mid.tracks):
        nome = tr.name or f'faixa {k}'
        novo.tracks.append(faixa(tr, nome, base_mid))
        feitas.add(nome)
    for k, tr in enumerate(outra_mid.tracks):
        nome = tr.name or f'faixa {k}'
        if nome not in feitas and res.get(nome):
            novo.tracks.append(faixa(tr, nome, outra_mid))
    novo.save(saida)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('base', help='a transcrição que fica (orientação 2)')
    ap.add_argument('outra', nargs='?', help='a da mesma gravação que empresta os blocos (orientação 1)')
    ap.add_argument('-o', help='MIDI de saída')
    ap.add_argument('--so-achar', action='store_true', help='só listar os trechos congelados da base')
    a = ap.parse_args()
    base_mid = mido.MidiFile(a.base)
    base, _ = notas(base_mid)
    cong = congelados(base)
    print('congelados: ' + (', '.join(f'{x:.2f}-{y:.2f} s' for x, y in cong) or 'nenhum'))
    if a.so_achar or not cong:
        return
    if not a.outra or not a.o:
        sys.exit('para emendar: base.mid outra.mid -o saida.mid')
    outra_mid = mido.MidiFile(a.outra)
    outra, _ = notas(outra_mid)
    cong_outra = congelados(outra)
    js = [j for j in janelas(cong) if not any(x < j[1] and y > j[0] for x, y in cong_outra)]
    pulados = [j for j in janelas(cong) if j not in js]
    print('blocos trocados: ' + (', '.join(f'{x:.0f}-{y:.0f} s' for x, y in js) or 'nenhum')
          + (' | a outra também congela em ' + ', '.join(f'{x:.0f}-{y:.0f} s' for x, y in pulados) if pulados else ''))
    if not js:
        return
    escrever(base_mid, outra_mid, emendar(base, outra, js), a.o)
    depois, _ = notas(mido.MidiFile(a.o))
    resto = congelados(depois)
    print('depois da emenda: ' + (', '.join(f'{x:.2f}-{y:.2f} s' for x, y in resto) or 'nenhum trecho congelado'))


if __name__ == '__main__':
    main()
