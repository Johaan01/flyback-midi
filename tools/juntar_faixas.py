#!/usr/bin/env python3
"""Acrescenta a um MIDI faixas de outro MIDI da mesma gravação, alinhadas pelo tempo em segundos.

    python tools/juntar_faixas.py base.mid outro.mid "electric bass" "drums" -o saida.mid

Para quando uma segunda transcrição acerta um instrumento que a primeira perdeu e erra outro.
Em out/2026 o detector de instrumentos (PANNs) não reconheceu bateria eletrônica nem baixo de
sintetizador em três músicas, embora os stems do Demucs pesassem 0,27 a 0,56 na mistura; refeitas
com baixo e bateria na lista, ganharam esses arcos mas perderam voz (96% -> 51% do canto em The Man
Who Sold the World). Juntar só as faixas novas à primeira versão ficou com o melhor das duas.

As grades de tempo das duas transcrições diferem (o MuScriptor detecta a batida a cada vez), por
isso a conversão passa por segundos, e não por ticks. Antes de juntar, confira se a faixa nova não
repete o que a base já tem com outro nome: em Live And Let Die, 71% da guitarra da segunda
transcrição era o "piano" da primeira.
"""
import argparse
import bisect

import mido


def mapa(m):
    """[(tick, segundo, tempo)] das mudanças de andamento."""
    ev = sorted((t, x.tempo) for tr in m.tracks for t, x in _abs(tr) if x.type == 'set_tempo')
    pts, seg, tick0, tempo = [(0, 0.0, 500000)], 0.0, 0, 500000
    for t, novo in ev:
        seg += mido.tick2second(t - tick0, m.ticks_per_beat, tempo)
        tick0, tempo = t, novo
        pts.append((t, seg, tempo))
    return pts


def _abs(tr):
    t = 0
    for x in tr:
        t += x.time
        yield t, x


def tick_para_seg(pts, tpb, tick):
    i = bisect.bisect_right([p[0] for p in pts], tick) - 1
    t0, s0, tempo = pts[i]
    return s0 + mido.tick2second(tick - t0, tpb, tempo)


def seg_para_tick(pts, tpb, seg):
    i = bisect.bisect_right([p[1] for p in pts], seg) - 1
    t0, s0, tempo = pts[i]
    return round(t0 + mido.second2tick(seg - s0, tpb, tempo))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('base')
    ap.add_argument('outro')
    ap.add_argument('faixas', nargs='+')
    ap.add_argument('-o', required=True)
    a = ap.parse_args()
    base, outro = mido.MidiFile(a.base), mido.MidiFile(a.outro)
    pb, po = mapa(base), mapa(outro)
    usados = {x.channel for tr in base.tracks for x in tr if hasattr(x, 'channel')}
    livres = [c for c in range(16) if c != 9 and c not in usados]
    for nome in a.faixas:
        tr = next(t for t in outro.tracks if t.name == nome)
        canais = {x.channel for x in tr if hasattr(x, 'channel')}
        troca = {c: (9 if c == 9 else livres.pop(0)) for c in canais}
        evs = []
        for t, x in _abs(tr):
            if x.type == 'end_of_track':
                continue
            nt = seg_para_tick(pb, base.ticks_per_beat, tick_para_seg(po, outro.ticks_per_beat, t))
            evs.append((nt, x.copy(channel=troca[x.channel]) if hasattr(x, 'channel') else x))
        nova, ant = mido.MidiTrack(), 0
        for nt, x in evs:
            nova.append(x.copy(time=nt - ant))
            ant = nt
        nova.append(mido.MetaMessage('end_of_track', time=0))
        base.tracks.append(nova)
        print(f'+ {nome}: {sum(1 for _, x in evs if x.type == "note_on" and x.velocity)} notas, canal {troca}')
    base.save(a.o)


if __name__ == '__main__':
    main()
