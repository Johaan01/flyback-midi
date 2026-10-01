#!/usr/bin/env python3
"""Compõe os arranjos de musicas/exemplos.

    python tools/compor_rock.py

Arranjos de temas em domínio público (Grieg, Bach, Beethoven, Pachelbel,
Greensleeves, Korobeiniki), escritos numa notação curta de texto e gravados
como MIDI formato 1 com faixas nomeadas. Servem de exemplo de arranjo de banda
para dois flybacks: a melodia e o solo nunca soam ao mesmo tempo. Cada música sai com
um .json de configuração: guitarra base no canal esquerdo, melodia e solo no
direito, que não se sobrepõem no tempo e por isso cabem num flyback só.

Notação dos padrões (tempos em semínimas):
  E2/8     nota e duração: 1 2 4 8 16 32, com . ou .. para pontuar e t para tercina
  E2       sem duração, repete a anterior
  E2*      power chord (tônica, quinta, oitava)       m  abafada (palm mute)
  [E3,G3]  acorde                                     >  acentuada
  r/8      pausa                                      |  barra: confere a soma do compasso
Só usa a biblioteca padrão do Python.
"""
import json
import math
import random
import re
import struct
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / 'musicas' / 'exemplos'
DIV = 480
NOMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
PC = {n: i for i, n in enumerate(NOMES)}
PROG = {'dist': 30, 'over': 29, 'limpa': 27, 'aco': 25, 'baixo': 33, 'palheta': 34, 'synbaixo': 38,
        'serra': 81, 'quadrada': 80, 'voz': 85, 'orgao': 19, 'piano': 0, 'cravo': 6, 'cordas': 48,
        'violino': 40, 'flauta': 73, 'pad': 89}
DUR = {'1': 4, '2': 2, '4': 1, '8': .5, '16': .25, '32': .125}
TOKEN = re.compile(r'^(r|\[[^\]]+\]|[A-G]#?-?\d)(\*)?(m)?(>)?(?:/(\d+)(\.{0,2})(t)?)?$')
BATERIA = {'K': 36, 'S': 38, 's': 37, 'H': 42, 'O': 46, 'P': 44, 'C': 49, 'c': 57, 'R': 51, 'B': 53,
           'X': 52, 'T': 48, 'M': 45, 'F': 43}


# ---------------------------------------------------------------- notação
def nota(s):
    m = re.fullmatch(r'([A-G]#?)(-?\d)', s)
    if not m:
        raise ValueError('nota inválida: ' + s)
    return 12 * (int(m[2]) + 1) + PC[m[1]]


def nome(n):
    return NOMES[n % 12] + str(n // 12 - 1)


def ler(padrao, barra):
    """Padrão → ([(início, duração, notas, abafada, acento)], comprimento). Confere cada compasso marcado."""
    evs, t, dur, ini = [], 0.0, 1.0, 0.0
    toks = padrao.split()
    for k, tok in enumerate(toks):
        if tok == '|':
            if abs((t - ini) - barra) > 1e-6:
                raise ValueError(f'compasso com {t - ini:g} tempos, esperado {barra:g}: '
                                 + ' '.join(toks[max(0, k - 12):k]))
            ini = t
            continue
        m = TOKEN.match(tok)
        if not m:
            raise ValueError('símbolo inválido: ' + tok)
        cab, power, mudo, acento, d, pontos, tercina = m.groups()
        if d:
            dur = DUR[d] * {'': 1, '.': 1.5, '..': 1.75}[pontos] * (2 / 3 if tercina else 1)
        if cab != 'r':
            ns = [nota(x.strip()) for x in cab[1:-1].split(',')] if cab.startswith('[') else [nota(cab)]
            if power:
                ns = [ns[0], ns[0] + 7, ns[0] + 12]
            evs.append((t, dur, ns, bool(mudo), bool(acento)))
        t += dur
    if '|' in toks and abs((t - ini) - barra) > 1e-6:
        raise ValueError(f'último compasso com {t - ini:g} tempos, esperado {barra:g}: ' + ' '.join(toks[-12:]))
    return evs, t


def dur_txt(d):
    for txt, v in (('1', 4), ('2.', 3), ('2', 2), ('4..', 1.75), ('4.', 1.5), ('4', 1), ('8.', .75),
                   ('4t', 2 / 3), ('8', .5), ('8t', 1 / 3), ('16', .25), ('32', .125)):
        if abs(d - v) < 1e-6:
            return txt
    raise ValueError(f'duração sem símbolo: {d}')


def partes_dur(d):
    """Decompõe uma duração em valores com símbolo (para pausas e notas longas)."""
    out = []
    for v in (4, 3, 2, 1.75, 1.5, 1, .75, .5, .25, .125):
        while d >= v - 1e-6:
            out.append(v)
            d -= v
    return out


QUAL = {'': (0, 4, 7), 'm': (0, 3, 7), 'dim': (0, 3, 6), 'dim7': (0, 3, 6, 9), '7': (0, 4, 7, 10),
        'm7': (0, 3, 7, 10), '5': (0, 7), 'sus4': (0, 5, 7)}
ESCALA = {'maior': (0, 2, 4, 5, 7, 9, 11), 'menor': (0, 2, 3, 5, 7, 8, 10), 'harm': (0, 2, 3, 5, 7, 8, 11),
          'pentam': (0, 3, 5, 7, 10), 'pentaM': (0, 2, 4, 7, 9), 'blues': (0, 3, 5, 6, 7, 10)}


def acorde(txt):
    m = re.fullmatch(r'([A-G]#?)(m7|m|dim7|dim|7|5|sus4)?', txt)
    if not m:
        raise ValueError('acorde inválido: ' + txt)
    r = PC[m[1]]
    return r, [(r + i) % 12 for i in QUAL[m[2] or '']], QUAL[m[2] or '']


def escala(tonica, tipo):
    return sorted((PC[tonica] + i) % 12 for i in ESCALA[tipo])


def raiz_em(pc, lo):
    return lo + (pc - lo) % 12


def acorde_em(acs, t, barra):
    """Qual acorde soa no tempo t do compasso ('C D' divide o compasso ao meio)."""
    return acs[min(int(t / (barra / len(acs)) + 1e-9), len(acs) - 1)]


# ---------------------------------------------------------------- geradores de padrão
RITMO = re.compile(r'^(r)?(\d+)(\.{0,2})(t)?([mo5>]*)$')


def ritmo_ler(ritmo):
    out = []
    for tok in ritmo.split():
        m = RITMO.match(tok)
        if not m:
            raise ValueError('ritmo inválido: ' + tok)
        pausa, d, pts, terc, mods = m.groups()
        out.append((bool(pausa), d + pts + (terc or ''), DUR[d] * {'': 1, '.': 1.5, '..': 1.75}[pts] * (2 / 3 if terc else 1), mods))
    return out


def riff(acordes, ritmo, barra, lo=40, power=True):
    """Power chords (ou tônicas) seguindo a harmonia, no ritmo dado, um compasso por item de 'acordes'."""
    rit, bars = ritmo_ler(ritmo), []
    for ac in acordes:
        acs, t, toks = ac.split(), 0.0, []
        for pausa, dtxt, d, mods in rit:
            if pausa:
                toks.append('r/' + dtxt)
            else:
                r = raiz_em(acorde(acorde_em(acs, t, barra))[0], lo)
                if 'o' in mods:
                    r += 12
                if '5' in mods:
                    r += 7
                toks.append(nome(r) + ('*' if power and '5' not in mods else '') + ('m' if 'm' in mods else '')
                            + ('>' if '>' in mods else '') + '/' + dtxt)
            t += d
        bars.append(' '.join(toks))
    return ' | '.join(bars)


def arpejo(acordes, figura, barra, dur='8', lo=40):
    passo, bars = DUR[dur], []
    for ac in acordes:
        acs, t, k, toks = ac.split(), 0.0, 0, []
        while t < barra - 1e-9:
            r, _, iv = acorde(acorde_em(acs, t, barra))
            pilha = sorted(raiz_em(r, lo) + i + 12 * o for o in range(4) for i in iv)
            toks.append(nome(pilha[figura[k % len(figura)]]) + '/' + dur)
            t += passo
            k += 1
        bars.append(' '.join(toks))
    return ' | '.join(bars)


def bloco(acordes, barra, lo=52, dur=None):
    """Acordes cheios, um por metade ou compasso inteiro."""
    bars = []
    for ac in acordes:
        acs = ac.split()
        d = dur or dur_txt(barra / len(acs))
        toks = []
        for a in acs:
            r, _, iv = acorde(a)
            base = raiz_em(r, lo)
            toks.append('[' + ','.join(nome(base + i) for i in iv) + ']/' + d)
        bars.append(' '.join(toks))
    return ' | '.join(bars)


def tremolo(seq, n=4, dur='16'):
    return ' '.join(f'{x}/{dur}' + (' ' + ' '.join([x] * (n - 1)) if n > 1 else '') for x in seq.split())


def transpor(padrao, st):
    return re.sub(r'([A-G]#?)(-?\d)', lambda m: nome(nota(m[0]) + st), padrao)


def abafar(padrao):
    return re.sub(r'([A-G]#?-?\d)(?=/|\s|$)', r'\1m', padrao)


def harmonizar(padrao, esc, graus):
    """Voz paralela: cada nota anda 'graus' passos na escala (terça abaixo = -2)."""
    def mover(m):
        n = nota(m[0])
        if n % 12 not in esc:
            return nome(n + (4 if graus > 0 else -3))
        o, pc = divmod(n, 12)
        i = esc.index(pc) + graus
        return nome(12 * (o + i // len(esc)) + esc[i % len(esc)])
    return re.sub(r'([A-G]#?)(-?\d)', mover, padrao)


CELULAS = {
    1: [[2], [1], [1], [1.5, .5], [.5, .5], [1, 1]],
    2: [[1], [.5, .5], [.5, .5], [.75, .25], [.5, .25, .25], [.25, .25, .5], [1.5, .5]],
    3: [[.25] * 4, [.25] * 4, [.25] * 4, [.5, .25, .25], [1 / 3] * 3, [.5, .5], [.25, .25, .5]],
}


def improviso(esc, acordes, barra, semente, intensidade=2, lo=64, hi=88):
    """Solo: passeio pela escala com motivos que se repetem, notas do acorde nos tempos fortes
    e nota longa no fim de cada frase de quatro compassos."""
    rnd = random.Random(semente)
    notas = [n for n in range(lo, hi + 1) if n % 12 in esc]
    i, bars, ant = len(notas) // 2, [], None
    frase = 2 if intensidade == 1 else 4
    for b, ac in enumerate(acordes):
        acs = ac.split()
        repete = ant is not None and b % 2 == 1 and rnd.random() < .6
        if repete:
            ritmo = ant[0][:]
        else:
            ritmo, t = [], 0.0
            while t < barra - 1e-9:
                ops = [c for c in CELULAS[intensidade] if sum(c) <= barra - t + 1e-9] or [[barra - t]]
                c = rnd.choice(ops)
                ritmo += c
                t += sum(c)
        ultimo = b == len(acordes) - 1
        if b % frase == frase - 1 or ultimo:
            t, novo = 0.0, []
            for d in ritmo:
                if t >= barra / 2 - 1e-9 and abs(t * 4 - round(t * 4)) < 1e-6:   # nunca no meio de uma tercina
                    break
                novo.append(d)
                t += d
            novo += partes_dur(barra - t)[:1]
            resto = barra - t - novo[-1]
            novo += partes_dur(resto)
            ritmo = novo
        toks, t, idx = [], 0.0, []
        desloc = rnd.choice([-2, -1, 1, 2])
        for k, d in enumerate(ritmo):
            forte = k == 0 or abs(t - barra / 2) < 1e-6
            pcs = acorde(acorde_em(acs, t, barra))[1]
            if not forte and rnd.random() < (.12 if intensidade == 1 else .07):
                toks.append('r/' + dur_txt(d))
                t += d
                idx.append(i)
                continue
            if repete and k < len(ant[1]):
                i = max(0, min(len(notas) - 1, ant[1][k] + desloc))
            else:
                passo = rnd.choice([-2, -1, -1, -1, 1, 1, 1, 2] + ([3, -3, 4, -4] if rnd.random() < .18 else []))
                if i + passo < 0 or i + passo >= len(notas):
                    passo = -passo
                i = max(0, min(len(notas) - 1, i + passo))
            final = k == len(ritmo) - 1 and (ultimo or b % frase == frase - 1)
            if forte or final:
                alvo = [acorde(acorde_em(acs, t, barra))[0]] if (final and ultimo) else pcs
                cand = [j for j, x in enumerate(notas) if x % 12 in alvo]
                if cand:
                    i = min(cand, key=lambda j: (abs(j - i), j))
            toks.append(nome(notas[i]) + '/' + dur_txt(d))
            idx.append(i)
            t += d
        ant = (ritmo, idx)
        bars.append(' '.join(toks))
    return ' | '.join(bars)


# ---------------------------------------------------------------- bateria
ESTILO = {
    'rock':     {'K': 'x.......x.x.....', 'S': '....x.......x...', 'H': 'x.x.x.x.x.x.x.x.'},
    'ride':     {'K': 'x.......x.x.....', 'S': '....x.......x...', 'R': 'x.x.x.x.x.x.x.x.'},
    'pratos':   {'K': 'x.......x.x.....', 'S': '....X.......X...', 'C': 'x...x...x...x...'},
    'metade':   {'K': 'x.....x...x.....', 'S': '........X.......', 'H': 'x.x.x.x.x.x.x.x.'},
    'thrash':   {'K': 'x...x...x...x...', 'S': '..x...x...x...x.', 'H': 'x.x.x.x.x.x.x.x.'},
    'duplo':    {'K': 'xxxxxxxxxxxxxxxx', 'S': '....X.......X...', 'R': 'x...x...x...x...'},
    'galope':   {'K': 'x.xxx.xxx.xxx.xx', 'S': '....x.......x...', 'H': 'x.x.x.x.x.x.x.x.'},
    'punk':     {'K': 'x.x...x.x.x...x.', 'S': '....x.......x...', 'H': 'x.x.x.x.x.x.x.x.'},
    'blast':    {'K': 'x.x.x.x.', 'S': '.x.x.x.x', 'R': 'xxxxxxxx'},
    'doom':     {'K': 'x.......x.......', 'S': '........X.......', 'R': '....x.......x...'},
    'balada':   {'K': 'x......x.x......', 'S': '....x.......x...', 'H': 'x.x.x.x.x.x.x.x.'},
    'leve':     {'K': 'x.......x.......', 's': '....x.......x...', 'H': 'x.x.x.x.x.x.x.x.'},
    'synth':    {'K': 'x.......x.......', 'S': '....X.......X...', 'H': 'xxxxxxxxxxxxxxxx'},
    'chip':     {'K': 'x.......x.x.....', 'S': '....x.......x...', 'H': 'x.x.x.x.x.x.x.x.'},
    'prog78':   {'K': 'x.x.....x.x...', 'S': '....x.......x.', 'H': 'x.x.x.x.x.x.x.'},
    'rock68':   {'K': 'x.......x...', 'S': '......X.....', 'H': 'x.x.x.x.x.x.'},
    'balada68': {'K': 'x...........', 'S': '......x.....', 'H': 'x.x.x.x.x.x.'},
    'duplo68':  {'K': 'xxxxxxxxxxxx', 'S': '......X.....', 'R': 'x.....x.....'},
    'chimbal':  {'H': 'x.x.x.x.x.x.x.x.'},
}


def virada(estilo):
    """Último quarto do compasso vira caixa e tons descendo."""
    n = len(next(iter(estilo.values())))
    corte = n * 3 // 4 if n >= 8 else n // 2
    out = {k: v[:corte] + '.' * (n - corte) for k, v in estilo.items()}
    resto = n - corte
    meio = corte + resto // 2
    out['S'] = out.get('S', '.' * n)[:corte] + 'x' * (meio - corte) + '.' * (n - meio)
    tons = ''.join('TMF'[min(2, (j * 3) // max(1, n - meio))] for j in range(n - meio))
    for t in 'TMF':
        out[t] = '.' * meio + ''.join('x' if c == t else '.' for c in tons)
    return out


# ---------------------------------------------------------------- música
class Faixa:
    def __init__(self, nome_, programa, canal, vel=96, gate=.92):
        self.nome, self.programa, self.canal, self.vel, self.gate = nome_, programa, canal, vel, gate
        self.notas = []

    def por(self, ini, dur, padrao, barra):
        if isinstance(padrao, list):
            padrao = ' | '.join(padrao)
        evs, comp = ler(padrao, barra)
        if comp <= 0:
            return
        vezes = dur / comp
        if comp < dur and abs(vezes - round(vezes)) > 1e-6:
            raise ValueError(f'{self.nome}: padrão de {comp:g} tempos não divide a seção de {dur:g}')
        for k in range(math.ceil(vezes - 1e-9)):
            for t, d, ns, mudo, acento in evs:
                a = ini + k * comp + t
                if a >= ini + dur - 1e-9:
                    break
                d = min(d, ini + dur - a)
                g = .45 if mudo else self.gate
                v = min(127, int(self.vel * (.85 if mudo else 1) + (18 if acento else 0)))
                for n in ns:
                    self.notas.append((a, a + max(.03, d * g), n, v))


class Bateria(Faixa):
    def por(self, ini, dur, spec, barra):
        nome_, flags = (spec, '') if isinstance(spec, str) else spec
        base = ESTILO[nome_]
        compassos = round(dur / barra)
        for b in range(compassos):
            pad = virada(base) if 'f' in flags and b == compassos - 1 else base
            t0 = ini + b * barra
            if 'c' in flags and b == 0:
                self.notas.append((t0, t0 + .5, BATERIA['C'], 115))
            for inst, s in pad.items():
                passo = barra / len(s)
                for j, c in enumerate(s):
                    if c in 'xXo':
                        v = {'x': 100, 'X': 118, 'o': 55}[c]
                        self.notas.append((t0 + j * passo, t0 + (j + .8) * passo, BATERIA[inst], v))


class Musica:
    def __init__(self, titulo, bpm, compasso=(4, 4)):
        self.titulo, self.faixas, self.pos = titulo, [], 0.0
        self.tempos, self.metros, self.compasso = [(0.0, bpm)], [(0.0, compasso)], compasso
        self._canal = 0

    @property
    def barra(self):
        n, d = self.compasso
        return n * 4 / d

    def faixa(self, nome_, programa, **kw):
        if nome_ == 'Bateria':
            f = Bateria(nome_, 0, 9, **kw)
        else:
            f = Faixa(nome_, PROG.get(programa, programa), self._canal, **kw)
            self._canal += 2 if self._canal == 8 else 1
        self.faixas.append(f)
        return f

    def secao(self, compassos, partes, bpm=None, ate=None, compasso=None):
        if compasso and compasso != self.compasso:
            self.compasso = compasso
            self.metros.append((self.pos, compasso))
        if bpm is not None and ate is not None:
            for i in range(compassos):
                self.tempos.append((self.pos + i * self.barra, bpm + (ate - bpm) * i / max(1, compassos - 1)))
        elif bpm is not None:
            self.tempos.append((self.pos, bpm))
        dur = compassos * self.barra
        for f, p in partes.items():
            if p is not None:
                f.por(self.pos, dur, p, self.barra)
        self.pos += dur

    def midi(self):
        def vlq(n):
            b = [n & 0x7f]
            n >>= 7
            while n:
                b.append((n & 0x7f) | 0x80)
                n >>= 7
            return bytes(reversed(b))

        def trilha(evs):
            evs.sort(key=lambda e: (e[0], e[1]))
            out, ult = b'', 0
            for t, _, dados in evs:
                out += vlq(t - ult) + dados
                ult = t
            out += b'\x00\xff\x2f\x00'
            return b'MTrk' + struct.pack('>I', len(out)) + out

        tk = lambda beats: round(beats * DIV)
        txt = lambda tipo, s: bytes([0xff, tipo]) + vlq(len(s.encode())) + s.encode()
        cond = [(0, 0, txt(3, self.titulo))]
        for t, (n, d) in self.metros:
            cond.append((tk(t), 0, bytes([0xff, 0x58, 4, n, int(math.log2(d)), 24, 8])))
        for t, bpm in self.tempos:
            cond.append((tk(t), 0, b'\xff\x51\x03' + round(60e6 / bpm).to_bytes(3, 'big')))
        trilhas = [trilha(cond)]
        for f in self.faixas:
            evs = [(0, 0, txt(3, f.nome)), (0, 1, bytes([0xc0 | f.canal, f.programa]))]
            for a, b, n, v in f.notas:
                if 0 <= n < 128:
                    evs.append((tk(a), 3, bytes([0x90 | f.canal, n, v])))
                    evs.append((max(tk(a) + 1, tk(b)), 2, bytes([0x80 | f.canal, n, 0])))
            trilhas.append(trilha(evs))
        return b'MThd' + struct.pack('>IHHH', 6, 1, len(trilhas), DIV) + b''.join(trilhas)


def config(esq, dir_, faixas, oitava_esq=0, oitava_dir=0, acorde_esq='grave'):
    return {'versao': 1,
            'faixas': [{'nome': f.nome, 'canal': 'esquerdo' if f.nome in esq else 'direito' if f.nome in dir_ else 'desligada'}
                       for f in faixas],
            'canais': [{'ganho': 70, 'passaBaixa': 20000, 'oitava': oitava_esq, 'acorde': acorde_esq},
                       {'ganho': 70, 'passaBaixa': 20000, 'oitava': oitava_dir, 'acorde': 'agudo'}]}


def banda(m, extra=()):
    """Faixas comuns: bateria, baixo, guitarra base, melodia, guitarra solo."""
    f = {'bat': m.faixa('Bateria', 0), 'bx': m.faixa('Baixo', 'baixo', vel=100),
         'gb': m.faixa('Guitarra base', 'dist', vel=92), 'mel': m.faixa('Melodia', 'voz', vel=104, gate=.95),
         'gs': m.faixa('Guitarra solo', 'over', vel=108, gate=.95)}
    for chave, nome_, prog, kw in extra:
        f[chave] = m.faixa(nome_, prog, **kw)
    return f


# ================================================================ as músicas


def rei_da_montanha():
    m = Musica('Na Gruta do Rei da Montanha (metal)', 100)
    f = banda(m, [('gs2', 'Guitarra solo 2', 'over', {'vel': 100, 'gate': .95})])
    B = m.barra
    # E. Grieg, Peer Gynt (1875), domínio público
    tema = ('B2/8 C#3/8 D3/8 E3/8 F#3/8 D3/8 F#3/4 | F3/8 C#3/8 F3/4 E3/8 C3/8 E3/4 | '
            'B2/8 C#3/8 D3/8 E3/8 F#3/8 D3/8 F#3/8 B3/8 | A3/8 F#3/8 D3/8 F#3/8 A3/2')
    har = ['Bm', 'C#7 C', 'Bm', 'D']
    har5 = ['F#m', 'G#7 G', 'F#m', 'A']
    gal = '8m 16m 16m 8m 16m 16m 8m 16m 16m 8m 16m 16m'
    m.secao(8, {f['bx']: transpor(tema, -12)}, bpm=100, ate=118)
    m.secao(8, {f['bx']: transpor(tema, -12), f['gb']: abafar(tema), f['bat']: ('chimbal', '')}, bpm=120, ate=140)
    m.secao(8, {f['bx']: riff(har, gal, B, 28, False), f['gb']: riff(har, gal, B), f['gs']: transpor(tema, 12),
                f['bat']: ('galope', 'cf')}, bpm=142, ate=165)
    m.secao(8, {f['bx']: riff(har, gal, B, 28, False), f['gb']: riff(har, gal, B), f['gs']: transpor(tema, 24),
                f['gs2']: transpor(tema, 12), f['bat']: ('thrash', 'cf')}, bpm=168, ate=195)
    m.secao(8, {f['bx']: riff(har5, gal, B, 28, False), f['gb']: riff(har5, gal, B), f['gs']: transpor(tema, 19),
                f['gs2']: transpor(tema, 7), f['bat']: ('duplo', 'cf')}, bpm=198, ate=225)
    m.secao(8, {f['bx']: riff(har, '8 8 8 8 8 8 8 8', B, 28, False), f['gb']: riff(har, '16m 16m 16m 16m 16m 16m 16m 16m 8 8 8 8', B),
                f['gs']: transpor(tema, 24), f['gs2']: transpor(tema, 12), f['bat']: ('blast', 'cf')}, bpm=228, ate=240)
    fim = 'B2*/4 r/4 F#2*/4 r/4 | B2*/4 r/4 F#2*/4 r/4 | B2*/1'
    m.secao(3, {f['gb']: fim, f['bx']: transpor(fim.replace('*', ''), -12), f['gs']: 'B4/4 r/4 F#4/4 r/4 | B4/4 r/4 F#4/4 r/4 | B4/1',
                f['bat']: ('pratos', 'c')}, bpm=240)
    return m, config(['Guitarra base', 'Guitarra solo 2', 'Baixo'], ['Guitarra solo'], m.faixas, acorde_esq='agudo')


def tocata():
    m = Musica('Tocata em Ré menor (metal)', 72)
    f = banda(m, [('org', 'Órgão', 'orgao', {'vel': 90, 'gate': .98})])
    # J. S. Bach, Tocata e Fuga em Ré menor, BWV 565, domínio público
    motivo = 'A4/16 G4/16 A4/2 r/4 r/8 | G4/16 F4/16 E4/16 D4/16 C#4/2 r/4 | D4/1'
    subida = 'C#3/16 E3 G3 A#3 C#4 E4 G4 A#4 C#5/2 | [D3,F3,A3,D4]/1'
    intro = motivo + ' | ' + transpor(motivo, -12) + ' | ' + transpor(motivo, -24)
    m.secao(9, {f['org']: intro, f['gs']: transpor(motivo, 12) + ' | ' + motivo + ' | ' + transpor(motivo, -12),
                f['bat']: None})
    m.secao(2, {f['org']: subida, f['gb']: 'r/1 | D2*/1', f['bx']: 'r/1 | D1/1', f['bat']: ('chimbal', 'c')})
    corridas = ('A4/16 G4 A4 F4 A4 E4 A4 D4 A4 C#4 A4 D4 A4 E4 A4 F4 | A4/16 G4 A4 F4 A4 E4 A4 D4 C#4 E4 G4 A#4 A4 G4 F4 E4 | '
                'D5/16 C#5 D5 A#4 D5 A4 D5 G4 D5 F4 D5 E4 D5 F4 D5 G4 | C#5/16 A4 E4 C#4 A3 C#4 E4 A4 C#5 E5 G5 E5 C#5 A4 G4 E4')
    har = ['Dm', 'A7', 'Gm', 'A7']
    B = 4
    cha = '8m 8m 8m 8m 8m 8m 8 8'
    riff_g = 'D2*m/8 D2*m D2*m F2*/8 D2*m/8 D2*m G2*/8 F2*/8 | D2*m/8 D2*m D2*m A#2*/8 A2*/4 C#3*/4'
    riff_b = 'D1/8 D1 D1 F1 D1 D1 G1 F1 | D1/8 D1 D1 A#1 A1/4 C#2/4'
    s_corr = {f['gs']: transpor(corridas, 12), f['gb']: riff(har, cha, B), f['bx']: riff(har, '8 8 8 8 8 8 8 8', B, 28, False),
              f['bat']: ('duplo', 'cf')}
    s_riff = {f['gb']: riff_g, f['bx']: riff_b, f['org']: transpor(motivo.rsplit('|', 1)[0], 12), f['bat']: ('thrash', 'cf')}
    m.secao(8, s_corr, bpm=132)
    m.secao(4, s_riff)
    m.secao(8, {**s_corr, f['org']: bloco(har, B, 50)})
    m.secao(8, {f['gb']: riff(har, cha, B), f['bx']: riff(har, '8 8 8 8 8 8 8 8', B, 28, False), f['bat']: ('duplo', 'cf'),
                f['gs']: improviso(escala('D', 'harm'), har * 2, B, 101, 3)})
    m.secao(4, s_riff)
    m.secao(3, {f['gs']: transpor(motivo, 12), f['org']: motivo, f['gb']: 'A2*/1 | A2*/1 | D2*/1', f['bx']: 'A1/1 | A1/1 | D1/1',
                f['bat']: ('pratos', 'c')}, bpm=84)
    m.secao(1, {f['gs']: 'D5/1', f['org']: '[D3,F3,A3,D4]/1', f['gb']: 'D2*/1', f['bx']: 'D1/1', f['bat']: ('chimbal', 'c')}, bpm=60)
    return m, config(['Guitarra base', 'Órgão'], ['Guitarra solo'], m.faixas, acorde_esq='agudo')


def fur_elise():
    m = Musica('Für Elise (rock)', 66, (3, 8))
    f = banda(m, [('pd', 'Piano (mão direita)', 'piano', {'vel': 90, 'gate': 1.0}),
                  ('pe', 'Piano (mão esquerda)', 'piano', {'vel': 70, 'gate': 1.0}),
                  ('gs2', 'Guitarra solo 2', 'over', {'vel': 100, 'gate': .95})])
    # L. van Beethoven, Bagatela WoO 59 (1810), domínio público
    A = ('E5/16 D#5 E5 B4 D5 C5 | A4/8 r/16 C4 E4 A4 | B4/8 r/16 E4 G#4 B4 | C5/8 r/16 E4 E5 D#5 | '
         'E5/16 D#5 E5 B4 D5 C5 | A4/8 r/16 C4 E4 A4 | B4/8 r/16 E4 C5 B4 | A4/8 r/16 r E5 D#5')
    me = ('r/4. | A2/16 E3 A3 r/8. | E2/16 E3 G#3 r/8. | A2/16 E3 A3 r/8. | '
          'r/4. | A2/16 E3 A3 r/8. | E2/16 E3 G#3 r/8. | A2/16 E3 A3 r/8.')
    Bep = ('A4/8 r/16 B4 C5 D5 | E5/8. G4/16 F5 E5 | D5/8. F4/16 E5 D5 | C5/8. E4/16 D5 C5 | '
           'B4/8 r/16 E4 E5 r | r/16 E5 E6 r r D#5 | E5/16 r r D#5 E5 D#5 | E5/16 D#5 E5 D#5 E5 D#5')
    m.secao(1, {f['pd']: 'r/4 E5/16 D#5'})
    m.secao(8, {f['pd']: A, f['pe']: me})
    # banda em 6/8: cada compasso junta dois do original
    har_a = ['E Am'] * 4
    har_b = ['Am C', 'G Am', 'E E', 'E E']
    seis = '8 8 8 8 8 8'
    pares = lambda p: ' | '.join(' '.join(p.split(' | ')[i:i + 2]) for i in range(0, 8, 2))
    a68, b68 = pares(A), pares(Bep)

    def banda68(mel, har, estilo, faixa=f['gs']):
        return {faixa: mel, f['gb']: riff(har, seis, 3), f['bx']: riff(har, seis, 3, 28, False), f['bat']: estilo}
    m.secao(4, banda68(a68, har_a, ('rock68', 'c')), bpm=84, compasso=(6, 8))
    m.secao(4, banda68(a68, har_a, ('rock68', 'f')))
    m.secao(4, banda68(b68, har_b, ('rock68', 'cf')))
    m.secao(4, banda68(a68, har_a, ('duplo68', 'cf')))
    m.secao(8, {f['gb']: riff(['Am', 'E'] * 4, seis, 3), f['bx']: riff(['Am', 'E'] * 4, seis, 3, 28, False),
                f['bat']: ('duplo68', 'cf'), f['gs']: improviso(escala('A', 'harm'), ['Am', 'E'] * 4, 3, 111, 3)})
    m.secao(4, {**banda68(a68, har_a, ('rock68', 'cf')), f['gs2']: harmonizar(a68, escala('A', 'harm'), -2)})
    m.secao(1, {f['gs']: 'A4/2.', f['gs2']: 'E4/2.', f['gb']: 'A2*/2.', f['bx']: 'A1/2.', f['bat']: ('chimbal', 'c')})
    return m, config(['Guitarra base', 'Piano (mão esquerda)', 'Guitarra solo 2'], ['Guitarra solo', 'Piano (mão direita)'],
                     m.faixas, acorde_esq='agudo')


def greensleeves():
    m = Musica('Greensleeves (balada metal)', 84, (6, 8))
    f = banda(m, [('gl', 'Guitarra limpa', 'limpa', {'vel': 80, 'gate': 1.3}),
                  ('gs2', 'Guitarra solo 2', 'over', {'vel': 100, 'gate': .95})])
    f['mel'].programa = PROG['flauta']
    # Tradicional inglesa, século XVI, domínio público
    v = ('C5/4 D5/8 E5/8. F5/16 E5/8 | D5/4 B4/8 G4/8. A4/16 B4/8 | C5/4 A4/8 A4/8. G#4/16 A4/8 | B4/4 G#4/8 E4/4 A4/8 | '
         'C5/4 D5/8 E5/8. F5/16 E5/8 | D5/4 B4/8 G4/8. A4/16 B4/8 | C5/8. B4/16 A4/8 G#4/8. F#4/16 G#4/8 | A4/4. A4/4.')
    c = ('G5/4. G5/8. F#5/16 E5/8 | D5/4 B4/8 G4/8. A4/16 B4/8 | C5/4 A4/8 A4/8. G#4/16 A4/8 | B4/4 G#4/8 E4/4. | '
         'G5/4. G5/8. F#5/16 E5/8 | D5/4 B4/8 G4/8. A4/16 B4/8 | C5/8. B4/16 A4/8 G#4/8. F#4/16 G#4/8 | A4/4. r/4 A4/8')
    hv = ['Am', 'G', 'Am', 'E', 'Am', 'G', 'Am E', 'Am']
    hc = ['C', 'G', 'Am', 'E', 'C', 'G', 'Am E', 'Am']
    fig = [0, 2, 3, 4, 3, 2]
    seis = '4. 4 8'
    hm = escala('A', 'harm')

    def pesado(har, estilo):
        return {f['gb']: riff(har, seis, 3), f['bx']: riff(har, '8 8 8 8 8 8', 3, 28, False), f['bat']: estilo}
    m.secao(4, {f['gl']: arpejo(['Am', 'G', 'Am', 'E'], fig, 3), f['mel']: 'r/4. r/4. | r/4. r/4. | r/4. r/4. | r/4. r/4 A4/8'})
    m.secao(8, {f['gl']: arpejo(hv, fig, 3), f['bx']: riff(hv, '4. 4.', 3, 28, False), f['mel']: v, f['bat']: ('balada68', 'f')})
    m.secao(8, {**pesado(hc, ('rock68', 'cf')), f['mel']: c})
    m.secao(8, {**pesado(hv, ('rock68', 'cf')), f['gs']: v, f['gs2']: harmonizar(v, hm, -2)})
    c_fim = c.rsplit('|', 1)[0] + '| A4/4. A4/4.'
    m.secao(8, {**pesado(hc, ('duplo68', 'cf')), f['gs']: c_fim, f['gs2']: harmonizar(c_fim, hm, -2)})
    m.secao(8, {**pesado(hv, ('rock68', 'cf')), f['gs']: improviso(escala('A', 'menor'), hv, 3, 121, 2)})
    m.secao(8, {**pesado(hc, ('rock68', 'cf')), f['mel']: c_fim})
    m.secao(2, {f['gl']: arpejo(['Am', 'Am'], fig, 3)}, bpm=70)
    m.secao(1, {f['gl']: '[A2,E3,A3,C4,E4]/2.', f['bx']: 'A1/2.'}, bpm=60)
    return m, config(['Guitarra base', 'Guitarra limpa', 'Guitarra solo 2'], ['Melodia', 'Guitarra solo'], m.faixas, acorde_esq='agudo')


def canone():
    m = Musica('Cânone em Ré (rock)', 104)
    f = banda(m, [('vl', 'Violino', 'violino', {'vel': 96, 'gate': .98}),
                  ('cr', 'Cravo', 'cravo', {'vel': 70, 'gate': .9})])
    B = m.barra
    # J. Pachelbel, Cânone em Ré (c. 1680), domínio público
    har = ['D A', 'Bm F#m', 'G D', 'G A']
    bx = 'D3/2 A2/2 | B2/2 F#2/2 | G2/2 D2/2 | G2/2 A2/2'
    v1 = 'F#5/2 E5/2 | D5/2 C#5/2 | B4/2 A4/2 | B4/2 C#5/2'
    v2 = 'D5/4 C#5/4 B4/4 A4/4 | G4/4 F#4/4 G4/4 E4/4 | D4/4 F#4/4 A4/4 G4/4 | F#4/4 D4/4 F#4/4 E4/4'
    v3 = ('D5/8 F#5 A5 F#5 E5 C#5 E5 A5 | F#5 D5 B4 D5 C#5 A4 F#4 A4 | '
          'B4 D5 G5 D5 A4 D5 F#5 D5 | G5 B5 G5 D5 E5 A5 C#6 A5')
    m.secao(4, {f['cr']: bloco(har, B, 50), f['bx']: bx})
    m.secao(8, {f['cr']: arpejo(har, [0, 1, 2, 1], B, '8', 50), f['bx']: bx, f['vl']: v1})
    m.secao(8, {f['cr']: arpejo(har, [0, 1, 2, 1], B, '8', 50), f['bx']: bx, f['vl']: v2, f['bat']: ('leve', 'f')})
    m.secao(8, {f['gb']: riff(har, '8 8 8 8 8 8 8 8', B), f['bx']: riff(har, '8 8 8 8 8 8 8 8', B, 28, False),
                f['gs']: v3, f['bat']: ('rock', 'cf')})
    m.secao(8, {f['gb']: riff(har, '8m 8m 8m 8m 8m 8m 8m 8m', B), f['bx']: riff(har, '8 8 8 8 8 8 8 8', B, 28, False),
                f['gs']: improviso(escala('D', 'maior'), har * 2, B, 131, 3, 62, 90), f['bat']: ('duplo', 'cf')})
    m.secao(8, {f['gb']: riff(har, '4 4 4 4', B), f['bx']: riff(har, '8 8 8 8 8 8 8 8', B, 28, False),
                f['gs']: transpor(v1, 12), f['vl']: v3, f['bat']: ('pratos', 'cf')})
    m.secao(1, {f['gb']: 'D3*/1', f['bx']: 'D2/1', f['gs']: 'D6/1', f['vl']: 'D5/1', f['cr']: '[D3,F#3,A3,D4]/1',
                f['bat']: ('chimbal', 'c')}, bpm=80)
    return m, config(['Guitarra base', 'Violino', 'Cravo'], ['Guitarra solo'], m.faixas, acorde_esq='agudo')


def quinta():
    m = Musica('Quinta de Beethoven (metal)', 110)
    f = banda(m, [('cd', 'Cordas', 'cordas', {'vel': 90, 'gate': .98})])
    B = m.barra
    # L. van Beethoven, Sinfonia nº 5 (1808), motivo de abertura, domínio público
    mot = 'r/8 G3/8 G3/8 G3/8 D#3/2 | D#3/1 | r/8 F3/8 F3/8 F3/8 D3/2 | D3/1'
    ra = 'r/8 G2*m/8 G2*m/8 G2*m/8 D#2*/2 | r/8 F2*m/8 F2*m/8 F2*m/8 D2*/2'
    rab = 'r/8 G1/8 G1 G1 D#1/2 | r/8 F1/8 F1 F1 D1/2'
    rb = 'C2*m/8 C2*m C2*m C2*m G2*/8 C2*m/8 C2*m D#2*/8 | C2*m/8 C2*m C2*m C2*m F2*/8 D#2*/8 D2*/8 B1*/8'
    rbb = 'C1/8 C1 C1 C1 G1 C1 C1 D#1 | C1 C1 C1 C1 F1 D#1 D1 B0'
    tema = ('r/8 G4/8 G4 G4 D#4/2 | r/8 F4/8 F4 F4 D4/2 | r/8 G4/8 G4 G4 G#4/2 | r/8 F4/8 F4 F4 G4/2 | '
            'r/8 D#5/8 D#5 D#5 C5/2 | r/8 G#4/8 G#4 G#4 G4/2 | r/8 C5/8 C5 C5 B4/4 G4/4 | C5/1')
    trompa = 'A#4/4 D#5/4 F5/2 | A#4/1 | G4/4 A#4/4 D#5/4 D5/4 | C5/1'
    ht = ['D#', 'A#', 'D#', 'G#']
    mot_g = 'r/8 G2*/8 G2* G2* D#2*/2 | D#2*/1 | r/8 F2*/8 F2* F2* D2*/2 | D2*/1'
    m.secao(4, {f['cd']: mot, f['bx']: transpor(mot, -12), f['gs']: transpor(mot, 12), f['gb']: mot_g})
    m.secao(4, {f['gb']: ra, f['bx']: rab, f['bat']: ('metade', 'cf')}, bpm=152)
    m.secao(8, {f['gb']: rb, f['bx']: rbb, f['gs']: tema, f['bat']: ('thrash', 'cf')})
    m.secao(8, {f['gb']: riff(ht, '4 8 8 4 4', B), f['bx']: riff(ht, '8 8 8 8 8 8 8 8', B, 28, False),
                f['gs']: trompa, f['cd']: bloco(ht, B, 55), f['bat']: ('pratos', 'cf')})
    m.secao(4, {f['gb']: ra, f['bx']: rab, f['bat']: ('metade', 'cf')})
    m.secao(8, {f['gb']: rb, f['bx']: rbb, f['bat']: ('duplo', 'cf'),
                f['gs']: improviso(escala('C', 'harm'), ['Cm', 'G'] * 4, B, 141, 3)})
    m.secao(8, {f['gb']: rb, f['bx']: rbb, f['gs']: tema, f['cd']: bloco(['Cm', 'G', 'Cm', 'G', 'Cm', 'G#', 'G', 'Cm'], B, 55),
                f['bat']: ('thrash', 'cf')})
    m.secao(4, {f['cd']: mot, f['bx']: transpor(mot, -12), f['gs']: transpor(mot, 12), f['gb']: mot_g,
                f['bat']: ('chimbal', 'c')}, bpm=120)
    m.secao(2, {f['gb']: 'C2*/4 r/4 C2*/4 r/4 | C2*/1', f['bx']: 'C1/4 r/4 C1/4 r/4 | C1/1', f['cd']: '[C4,D#4,G4]/4 r/4 [C4,D#4,G4]/4 r/4 | [C4,D#4,G4,C5]/1',
                f['gs']: 'C5/4 r/4 C5/4 r/4 | C5/1', f['bat']: ('pratos', 'c')}, bpm=140)
    return m, config(['Guitarra base', 'Cordas'], ['Guitarra solo'], m.faixas, oitava_esq=1, acorde_esq='agudo')


def korobeiniki():
    """Коробейники, canção popular russa de 1861 sobre poema de N. Nekrasov, em domínio
    público — o tema que o Tetris de 1989 espalhou pelo mundo. Em mi menor, bem rápida."""
    m = Musica('Korobeiniki (metal)', 150)
    f = banda(m)
    B = m.barra
    tema = ('E5/4 B4/8 C5/8 D5/4 C5/8 B4/8 | A4/4 A4/8 C5/8 E5/4 D5/8 C5/8 | '
            'B4/4. C5/8 D5/4 E5/4 | C5/4 A4/4 A4/2 | '
            'r/8 D5/4 F5/8 A5/4 G5/8 F5/8 | E5/4. C5/8 E5/4 D5/8 C5/8 | '
            'B4/4 B4/8 C5/8 D5/4 E5/4 | C5/4 A4/4 A4/2')
    ponte = ('E5/2 C5/2 | D5/2 B4/2 | C5/2 A4/2 | G#4/2 B4/2 | '
             'E5/2 C5/2 | D5/2 B4/2 | C5/4 E5/4 A5/2 | G#5/1')
    h_tema = ['Em', 'Am', 'B', 'Em', 'Dm', 'Am', 'B', 'Em']
    h_ponte = ['Em', 'Em', 'Am', 'B', 'Em', 'Em', 'Am', 'B']

    def base(har, ritmo='8m 8m 8m 8m 8m 8m 8 8'):
        return {f['gb']: riff(har, ritmo, B), f['bx']: riff(har, '8 8 8 8 8 8 8 8', B, 28, False)}

    m.secao(4, {**base(h_tema[:4]), f['bat']: ('rock', 'c')})
    m.secao(8, {**base(h_tema), f['mel']: tema, f['bat']: ('rock', 'cf')})
    m.secao(8, {**base(h_ponte, '4 4 4 4'), f['mel']: ponte, f['bat']: ('pratos', 'cf')})
    m.secao(8, {**base(h_tema, '8 8 8 8 8 8 8 8'), f['mel']: tema, f['bat']: ('galope', 'cf')})
    m.secao(8, {**base(h_tema), f['bat']: ('ride', 'cf'),
                f['gs']: improviso(escala('E', 'harm'), h_tema, B, 31)})
    m.secao(8, {**base(h_ponte, '4 4 4 4'), f['gs']: ponte, f['bat']: ('duplo', 'cf')})
    m.secao(8, {**base(h_tema, '8 8 8 8 8 8 8 8'), f['mel']: tema, f['bat']: ('duplo', 'cf')}, bpm=166)
    m.secao(1, {f['gb']: 'E2*/1', f['bx']: 'E1/1', f['bat']: ('pratos', 'c')}, bpm=110)
    return m, config(['Guitarra base', 'Baixo'], ['Melodia', 'Guitarra solo'], m.faixas)


MUSICAS = [
    (rei_da_montanha, 'arranjo metal de E. Grieg, Peer Gynt'),
    (tocata, 'arranjo metal de J. S. Bach, BWV 565'),
    (fur_elise, 'arranjo rock de L. van Beethoven, WoO 59'),
    (greensleeves, 'arranjo metal da canção tradicional inglesa'),
    (canone, 'arranjo rock de J. Pachelbel'),
    (quinta, 'arranjo metal de L. van Beethoven, Sinfonia nº 5'),
    (korobeiniki, 'arranjo metal de Korobeiniki, canção popular russa de 1861 (tema do Tetris)'),
]


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    creditos = {}
    for fn, sobre in MUSICAS:
        m, cfg = fn()
        base = m.titulo
        (DESTINO / f'{base}.mid').write_bytes(m.midi())
        (DESTINO / f'{base}.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        creditos[f'{base}.mid'] = {'autor': sobre, 'licenca': 'deste projeto', 'fonte': 'tools/compor_rock.py'}
        tempos = sorted(m.tempos, key=lambda x: x[0])
        fins = [x[0] for x in tempos[1:]] + [m.pos]
        seg = sum((fim - t) * 60 / bpm for (t, bpm), fim in zip(tempos, fins))
        print(f'  {base:42} {len(m.faixas)} faixas · {int(seg // 60)}:{int(seg % 60):02d}')
    arq = DESTINO / 'creditos.json'   # mescla: a pasta tem arquivos que não vêm daqui
    antes = json.loads(arq.read_text(encoding='utf-8')) if arq.is_file() else {}
    antes.update(creditos)
    arq.write_text(json.dumps(dict(sorted(antes.items())), ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{len(MUSICAS)} músicas em {DESTINO.relative_to(RAIZ)}')


if __name__ == '__main__':
    main()
