#!/usr/bin/env python3
"""Enxuga e reorganiza musicas/classicos.

    python tools/curar_acervo.py              # só mostra o que sairia
    python tools/curar_acervo.py --aplicar    # move, apaga e reescreve creditos.json

O download do Mutopia traz perto de 4.900 arquivos, e a maior parte não serve para um par de
flybacks: livro de método, estudo de digitação, e sobretudo pedaço solto de ópera e de cantata
— 2.988 dos 4.867 títulos terminam em " - NN", que é um movimento ou um número de uma obra
maior, sozinho e fora de contexto. O acervo fica grande demais para achar qualquer coisa.

Esta ferramenta deixa o repertório reconhecível e o que soa bem em duas vozes monofônicas,
arrumado em `classicos/<região>/<compositor>/`. A região é o país de origem do compositor, o
que dá um filtro de primeiro nível que presta e junta, por exemplo, todos os russos.

Os três critérios, nesta ordem:

  1. Corte seco       — método e estudo (estilo "Technique"), arquivo curto demais, e
                        compositor fora da tabela REGIOES abaixo.
  2. Aproveitamento   — quanto da música sobrevive à redução a duas linhas monofônicas.
                        Medido de verdade: o arquivo é lido, roteado pelo mesmo critério do
                        site e reduzido nota a nota.
  3. Cota por obra    — de uma obra com muitos movimentos ficam só os melhores, e de cada
                        compositor fica no máximo a cota da tabela.

Nada se perde de verdade: o que sai continua no histórico do Git. Rodar de novo sobre o acervo
já enxugado não corta mais nada, porque tudo que ficou já passou pelos mesmos critérios.

Só usa a biblioteca padrão do Python.
"""
import argparse
import hashlib
import json
import re
import shutil
import stat
import struct
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / 'musicas' / 'classicos'

DUR_MIN = 25.0      # abaixo disso é exercício ou fragmento, não música
NOTAS_MIN = 48
MOV_MAX = 3         # de uma obra em vários movimentos, no máximo estes

# ---------------------------------------------------------------- quem fica, de onde é, quanto fica
# Compositor -> (região, cota). Quem não está aqui sai do acervo. A região é o país de origem;
# Handel fica em Alemanha e Áustria porque é lá que nasceu e que se formou, embora tenha feito
# carreira em Londres, e Clementi na Itália pelo mesmo motivo ao contrário.
REGIOES = {
    'Alemanha e Áustria': {
        'Bach (J. S.)': 40, 'Mozart (W. A.)': 30, 'Beethoven (L. V.)': 25, 'Handel (G. F.)': 12,
        'Schubert (F.)': 14, 'Schumann (R.)': 12, 'Mendelssohn-Bartholdy (F.)': 12,
        'Brahms (J.)': 10, 'Haydn (F. J.)': 10, 'Telemann (G. P.)': 8, 'Buxtehude (D.)': 6,
        'Bach (C. P. E.)': 5, 'Pachelbel (J.)': 5, 'Diabelli (A.)': 5, 'Strauss Jr. (J.)': 3,
        'Luther (M.)': 2, 'Gruber (F. X.)': 2, 'Humperdinck (E.)': 2, 'Reger (M.)': 2,
        'Bruckner (A.)': 2, 'Spohr (L.)': 2, 'Kuhlau (F.)': 3, 'Froberger (J. J.)': 2,
        'Weckmann (M.)': 2, 'Fischer (J. K. F.)': 2, 'Haydn (J. M.)': 2, 'Silcher (F.)': 2,
    },
    'Rússia e Leste Europeu': {
        'Mussorgsky (M.)': 12, 'Dvořák (A.)': 12, 'Tchaikovsky (P. I.)': 11,
        'Ippolitov-Ivanov (M.)': 8, 'Rachmaninoff (S.)': 8, 'Scriabin (A.)': 6,
        'Rimsky-Korsakov (N.)': 5, 'Liszt (F.)': 4, 'Bartók (B.)': 2, 'Glazunov (A.)': 2,
        'Alyabyev (A.)': 2, 'Bortniansky (D.)': 2, 'Kopylov (A.)': 2, 'Archangelsky (A.)': 2,
        'Stanchinsky (A. V.)': 2, 'Veliumov (A.)': 2, 'Naujalis (J.)': 2, 'Iliev (G. K.)': 2,
        'Pejacsevich (D.)': 2, 'Benda (J. A.)': 2, 'Wanhal (J.)': 2, 'Knjze (F.)': 2,
    },
    'França': {
        'Satie (E.)': 10, 'Rameau (J. P.)': 8, 'Couperin (F.)': 6, 'Fauré (G.)': 6,
        'Lully (J. B.)': 6, 'Charpentier (M.-A.)': 4, 'Debussy (C.)': 4, 'Gounod (C.)': 3,
        'Bizet (G.)': 2, 'Saint-Saëns (C.)': 2, 'Dukas (P.)': 2, 'Franck (C.)': 2,
        'Widor (C.)': 2, 'Gigout (E.)': 2, 'Chabrier (E. A.)': 2, 'Lalo (E.)': 2,
        'Rouget de Lisle (C. J.)': 2, 'Grigny (N. de)': 2, 'Titelouze (J.)': 3,
        'Dandrieu (J.-F.)': 2, 'Boismortier (J. B. de)': 2, 'Devienne (F.)': 2,
        'Gossec (F.-J.)': 2, 'Méhul (E. N.)': 2, 'Coste (N.)': 3, 'Janequin (C.)': 2,
    },
    'Itália': {
        'Vivaldi (A.)': 12, 'Giuliani (M.)': 10, 'Carcassi (M.)': 8, 'Clementi (M.)': 8,
        'Verdi (G.)': 8, 'Paganini (N.)': 6, 'Carulli (F.)': 5, 'Monteverdi (C.)': 4,
        'Scarlatti (D.)': 4, 'Donizetti (G.)': 4, 'Corelli (A.)': 2, 'Marcello (B.)': 2,
        'Pergolesi (G. B.)': 2, 'Rossini (G.)': 2, 'Martini (G. B.)': 2, 'Albinoni (T.)': 2,
        'Frescobaldi (G.)': 2, 'Mercadante (S.)': 2, 'Rolla (A.)': 3, 'Barbella (E.)': 3,
        'Gesualdo (C.)': 2, 'Marenzio (L.)': 2, 'Banchieri (G.)': 2, 'Lotti (A.)': 2,
    },
    'Ilhas Britânicas': {
        'Elgar (E.)': 6, 'Holst (G. T.)': 4, 'Purcell (H.)': 3, 'Tallis (T.)': 3,
        'Morley (T.)': 3, 'Gibbons (O.)': 3, 'Dowland (J.)': 2, 'Arne (T.)': 2,
        'Sullivan (A.)': 2, 'Byrd (W.)': 3, 'Weelkes (T.)': 2, 'Croft (W.)': 2,
        'Stainer (J.)': 2, 'Smart (H. T.)': 2, 'Baltzar (T.)': 2, 'Eccles (H.)': 2,
    },
    'Ibéria e América Latina': {
        'Sor (F.)': 12, 'Tarrega (F.)': 8, 'Aguado (D.)': 6, 'Sanz (G.)': 3,
        'Milan (L.)': 3, 'Victoria (T. L. de)': 3, 'Albéniz (I. M. F.)': 2,
        'Granados (Enrique)': 2,
    },
    'Américas': {
        'Joplin (S.)': 14, 'Sousa (J. P.)': 14, 'Hall (R. B.)': 10, 'Foster (S. C.)': 4,
        'Gershwin (G.)': 4, 'Turpin (T.)': 3, 'Gottschalk (L. M.)': 2, 'Emmett (D. D.)': 2,
        'Joly (D.)': 2, 'Mason (L.)': 2, 'Root (G. F.)': 2, 'Bland (J. A.)': 2,
    },
    'Nórdicos e Países Baixos': {
        'Grieg (E.)': 12, 'Prés (J. des)': 4, 'Lassus (O. de)': 3, 'Nielsen (C. A.)': 2,
        'Heise (P.)': 2, 'Monte (P. de)': 3, 'Schulz (J. A. P.)': 2, 'Duyse (F. Van)': 2,
        'Benoit (P.)': 2, 'Bourgeois (L.)': 2, 'Japart (J.)': 2, 'Grandi (A.)': 2,
    },
    'Tradicional e anônimo': {
        'Traditional': 25, 'Anonymous': 6, 'Arbeau (T.)': 3,
    },
}
CASA = {comp: reg for reg, d in REGIOES.items() for comp in d}
COTA = {comp: n for d in REGIOES.values() for comp, n in d.items()}

# Títulos que ficam de qualquer jeito, mesmo com aproveitamento ruim: é o repertório que alguém
# procura pelo nome. Comparado sem acento e em caixa baixa, como trecho do título.
#
# Só entra aqui título de peça, nunca nome de forma musical. "Canon", "Prelude", "Minuet",
# "Etude" e "Nocturne" são formas, e o acervo tem centenas de cada uma: deixá-las na lista fazia
# o Bach gastar 11 das 40 vagas dele com os 14 Canons (BWV 1087), que ninguém procura.
DESTAQUES = [
    # Bach
    'toccata and fugue', 'toccata et fugue', 'air on the g', 'jesu, joy', 'brandenburg',
    'badinerie', 'chaconne', 'sheep may safely', 'wachet auf', 'sleepers awake',
    # Beethoven
    'fur elise', 'fuer elise', 'moonlight', 'mondschein', 'ode to joy', 'pathetique',
    'symphony no. 5', 'symphony no. 9', 'turkish march', 'marcia alla turca',
    # Mozart
    'eine kleine', 'rondo alla turca', 'requiem', 'lacrimosa', 'queen of the night',
    'konigin der nacht', 'symphony no. 40', 'zauberflote', 'figaro',
    # barroco
    'canon in d', 'kanon in d', 'ave maria', 'ombra mai', 'trumpet voluntary', 'messiah',
    'hallelujah', 'water music', 'music for the royal', 'four seasons', 'quattro stagioni',
    # romântico
    'clair de lune', 'gymnop', 'gnossienne', 'liebestraum', 'la campanella',
    'hungarian rhapsody', 'hungarian dance', 'revolutionary', 'raindrop', 'funeral march',
    'marche funebre', 'minute waltz', 'military polonaise', 'heroic polonaise',
    'fantaisie-impromptu', 'wedding march', 'bridal chorus', 'humoresque',
    'slavonic dance', 'new world',
    # Grieg, Mussorgsky e os russos
    'peer gynt', 'mountain king', 'morning mood', 'anitra', 'solveig',
    'pictures at an exhibition', 'great gate', 'bald mountain', 'nutcracker', 'swan lake',
    'sleeping beauty', '1812', 'flight of the bumble', 'scheherazade', 'sabre dance',
    'caucasian', 'sardar',
    # marcha, rag e popular
    'entertainer', 'maple leaf', 'stars and stripes', 'washington post', 'liberty bell',
    'semper fidelis', 'pomp and circumstance', 'rhapsody in blue', 'blue danube',
    'radetzky', 'can-can', 'infernal galop',
    # ópera
    'william tell', 'guillaume tell', 'carmen', 'habanera', 'toreador',
    'barber of seville', 'va pensiero', 'la donna e mobile', 'nessun dorma',
    'anvil chorus', 'triumphal march',
    # violão
    'recuerdos', 'alhambra', 'asturias', 'leyenda', 'malaguena', 'romance anonimo',
    'lagrima', 'adelita', 'capricho arabe',
    # tradicional
    'greensleeves', 'scarborough', 'danny boy', 'amazing grace', 'auld lang',
    'marseillaise', 'god save the', 'rule britannia', 'star spangled', 'yankee doodle',
    'dies irae', 'stille nacht', 'silent night', 'o tannenbaum', 'jingle bells',
    'kalinka', 'korobein', 'volga', 'ochi chern', 'dark eyes', 'troika',
]

GM_BATERIA = re.compile(r'drum|bateri|percus|kit', re.I)
RX_VOZ = re.compile(r'voc|voz|canto|cantor|sing|choir|coro|melod|lead|vox|aahs|oohs', re.I)
RX_BAIXO = re.compile(r'bass|baix|contrabai', re.I)
RX_NAO_BAIXO = re.compile(r'bassoon|fagote', re.I)
# numeração de movimento: aparece no fim ("Suite - 07") e também no meio ("14 Canons - 10 (BWV
# 1087)"). Até três dígitos, para não comer um "1812" que é nome de peça.
RX_MOV = re.compile(r'\s*[-–]\s*\d{1,3}\b')
RX_NUM = re.compile(r'[,\s]*\bN[oº]\.?\s*\d{1,3}\b', re.I)
RX_COPIA = re.compile(r'\s*\(\d+\)$')
# livro de método e estudo de digitação: só fica se o título estiver nos destaques
RX_ESTUDO = re.compile(
    r'\b(stud(y|ies)|etudes?|études?|exercises?|lessons?|progressive|vocalise|solfegg?io'
    r'|method|scales?|arpeggi|technique|petites?\s+pi[eè]ces?)\b', re.I)


def sem_acento(s):
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).casefold()


# ---------------------------------------------------------------- leitura do MIDI
class Faixa:
    __slots__ = ('chan', 'nome', 'gm', 'prog', 'notas')

    def __init__(self, chan):
        self.chan, self.nome, self.gm, self.prog, self.notas = chan, '', False, 0, []


def _vlq(b, p):
    v = 0
    while True:
        c = b[p]
        p += 1
        v = (v << 7) | (c & 0x7F)
        if not c & 0x80:
            return v, p


def ler_midi(dados):
    """SMF formato 0 ou 1, com running status. Cada MTrk sai separado por canal, como no site."""
    if dados[:4] != b'MThd':
        i = dados.find(b'MThd')
        if i < 0:
            raise ValueError('sem cabeçalho MThd')
        dados = dados[i:]
    _, _, ntrk, div = struct.unpack('>IHHH', dados[4:14])
    if div & 0x8000 or div == 0:
        raise ValueError('divisão SMPTE')
    p, faixas, tempos = 14, [], []
    for _ in range(ntrk):
        if p + 8 > len(dados) or dados[p:p + 4] != b'MTrk':
            break
        fim = min(len(dados), p + 8 + struct.unpack('>I', dados[p + 4:p + 8])[0])
        p += 8
        t, st, porcanal, nome, abertas = 0, 0, {}, '', {}
        while p < fim:
            try:
                d, p = _vlq(dados, p)
            except IndexError:
                break
            t += d
            if p >= fim:
                break
            b0 = dados[p]
            if b0 == 0xFF:
                tipo = dados[p + 1]
                ln, p2 = _vlq(dados, p + 2)
                corpo = dados[p2:p2 + ln]
                p = p2 + ln
                if tipo == 0x51 and ln == 3:
                    tempos.append((t, int.from_bytes(corpo, 'big')))
                elif tipo in (0x03, 0x04) and not nome:
                    try:
                        nome = corpo.decode('utf-8').strip()
                    except UnicodeDecodeError:
                        nome = corpo.decode('latin-1').strip()
                elif tipo == 0x2F:
                    break
                continue
            if b0 in (0xF0, 0xF7):
                ln, p2 = _vlq(dados, p + 1)
                p = p2 + ln
                continue
            if b0 & 0x80:
                st = b0
                p += 1
            ev, ca = st & 0xF0, st & 0x0F
            if ev in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                a, b = dados[p], dados[p + 1]
                p += 2
            elif ev in (0xC0, 0xD0):
                a, b = dados[p], 0
                p += 1
            else:
                p += 1
                continue
            f = porcanal.get(ca)
            if f is None:
                f = porcanal[ca] = Faixa(ca)
            if ev == 0xC0:
                f.prog = a
            elif ev == 0x90 and b:
                abertas.setdefault((ca, a), []).append(t)
            elif ev == 0x80 or (ev == 0x90 and not b):
                pilha = abertas.get((ca, a))
                if pilha:
                    f.notas.append((pilha.pop(0), t, a))
        p = fim
        for ca, f in sorted(porcanal.items()):
            if f.notas:
                f.nome = nome or ('Drums' if ca == 9 else '')
                f.gm = not nome
                faixas.append(f)
    if not tempos:
        tempos = [(0, 500000)]
    tempos.sort()
    if tempos[0][0] > 0:
        tempos.insert(0, (0, 500000))
    marcos, seg = [], 0.0
    for i, (tk, us) in enumerate(tempos):
        if i:
            seg += (tk - tempos[i - 1][0]) / div * (tempos[i - 1][1] / 1e6)
        marcos.append((tk, seg, us))

    def em_seg(tk):
        lo = 0
        for i, m in enumerate(marcos):
            if m[0] <= tk:
                lo = i
            else:
                break
        t0, s0, us = marcos[lo]
        return s0 + (tk - t0) / div * (us / 1e6)

    for f in faixas:
        f.notas = sorted((em_seg(a), em_seg(b), n) for a, b, n in f.notas if b > a)
    return [f for f in faixas if f.notas]


# ---------------------------------------------------------------- o mesmo roteamento do site
BIN = 0.1


def _ocupacao(faixas, dur):
    nb = int(dur / BIN) + 2
    saida = []
    for f in faixas:
        a = bytearray(nb)
        for t0, t1, _ in f.notas:
            for k in range(max(0, int(t0 / BIN)), min(nb - 1, int(t1 / BIN + .999)) + 1):
                a[k] = 1
        saida.append(a)
    return saida, nb


def _monofonia(f):
    if len(f.notas) < 2:
        return 1.0
    sobre, fim = 0, f.notas[0][1]
    for t0, t1, _ in f.notas[1:]:
        if t0 < fim - .01:
            sobre += 1
        fim = max(fim, t1)
    return 1 - sobre / len(f.notas)


def polifonia(notas):
    """(notas soando ao mesmo tempo em média, tempo total soando).

    1,0 é uma linha de uma voz só; 3,0 é naipe de acordes. Substitui a contagem de notas em
    sobreposição, que estava errada para este fim: linha gravada em legato — que é como se
    grava canto — tem cada nota começando antes de a anterior soltar, e pontuava quase zero.
    Na transcrição de Back In Black a faixa chamada "vocal" tirava 0,21 por isso.
    """
    if not notas:
        return 0.0, 0.0
    ev = []
    for t0, t1, _ in notas:
        ev.append((t0, 1))
        ev.append((t1, -1))
    ev.sort()
    vivos, soando, antes = 0, 0.0, None
    for t, d in ev:
        if vivos > 0 and antes is not None:
            soando += t - antes
        vivos += d
        antes = t
    return (sum(b - a for a, b, _ in notas) / soando if soando else 0.0), soando


# ---------------------------------------------------------------- achar a linha de canto
# Nome que anuncia canto de verdade. "lead" sozinho ficou de fora de propósito: "lead guitar"
# é o nome mais comum de faixa de guitarra solista, e dar bônus de voz a ela fazia o detector
# preferir a guitarra à voz. Só "lead voc"/"lead vox" conta.
RX_CANTO = re.compile(r'voc|vox|voice|vocal|\bsing|canto|\bvoz\b|melod|lyric|\blead\s*v', re.I)
# "voc -bu", "bck vox", "choir": apoio é harmonia, não a melodia principal.
RX_APOIO = re.compile(r'\b(bu|bv|bg|back|bck|harm|chorus|choir|coro)\b|backing|-bu', re.I)
# faixa que se anuncia como instrumento não é a voz, por mais aguda e monofônica que seja
RX_INSTRUM = re.compile(r'guit|gtr|piano|sax|organ|org[aã]o|string|synth|horn|trumpet|trompete'
                        r'|flute|flauta|violin|cello|harp|pad|brass|bell|banjo|accord', re.I)
# programas de voz e de lead sintetizado do General MIDI, mais os sopros que fazem o papel
PROG_VOZ = frozenset({40, 52, 53, 54, 56, 57, 64, 65, 66, 67, 71, 72, 73,
                      80, 81, 82, 83, 84, 85, 86, 87})
COBRE_MIN = .12     # linha de canto soa pelo menos isto da música; abaixo é ornamento


def medir_faixa(f, dur):
    poli, soando = polifonia(f.notas)
    media = sum(n[2] for n in f.notas) / len(f.notas) if f.notas else 0
    return {
        'nome': f.nome, 'prog': f.prog, 'n': len(f.notas), 'media': media,
        'poli': poli, 'cobre': min(1.0, soando / dur) if dur else 0.0,
        'bateria': f.chan == 9 or (not f.gm and bool(GM_BATERIA.search(f.nome))),
        # no acervo Lakh a faixa quase sempre se chama "Track 7", então o nome não basta para
        # achar o baixo: 32-39 são os programas de baixo, e média abaixo de F2 não é voz
        'baixo': (bool(RX_BAIXO.search(f.nome)) and not RX_NAO_BAIXO.search(f.nome))
                 or 32 <= f.prog <= 39 or media < 46,
    }


def nota_lead(m):
    """0 a ~9: o quanto esta faixa parece a linha de canto principal da música.

    A cobertura é porteira, não bônus: um "choir" de 39 notas em 4% da música é ornamento, e
    pontuá-lo alto fazia o detector dizer que havia voz onde não há.
    """
    if m['bateria'] or m['baixo'] or m['n'] < 25 or m['cobre'] < COBRE_MIN:
        return 0.0
    s = 2.2 * max(0.0, min(1.0, 2.0 - m['poli']))                 # uma voz só
    s += 1.2 * max(0.0, min(1.0, 1 - abs(m['media'] - 66) / 18))  # registro de canto
    s += 2.4 * min(1.0, m['cobre'] / .5)                          # presente ao longo da música
    if RX_CANTO.search(m['nome']):
        s += 0.4 if RX_APOIO.search(m['nome']) else 3.0
    if m['prog'] in PROG_VOZ:
        s += 0.6
    if RX_INSTRUM.search(m['nome']):
        s -= 0.6
    return max(0.0, s)


TEM_LEAD, TALVEZ_LEAD = 5.0, 3.8


def veredito_lead(nota):
    return 'sim' if nota >= TEM_LEAD else ('talvez' if nota >= TALVEZ_LEAD else 'nao')


def achar_lead(faixas, dur):
    """(medida da melhor candidata, nota). Acima de 6 é linha de canto; abaixo de 4,5 não há."""
    melhor, nota = None, 0.0
    for f in faixas:
        if not f.notas:
            continue
        m = medir_faixa(f, dur)
        v = nota_lead(m)
        if v > nota:
            melhor, nota = m, v
    return melhor, nota


def _linha(faixas, atrib, pr, lado, dur):
    """Reduz o canal a uma linha monofônica: prioridade primeiro, depois a nota mais aguda."""
    ev = []
    for k, f in enumerate(faixas):
        if atrib[k] != lado:
            continue
        for t0, t1, n in f.notas:
            ev.append((t0, 1, n, pr[k]))
            ev.append((t1, 0, n, pr[k]))
    if not ev:
        return 0.0, 0.0
    ev.sort(key=lambda e: (e[0], e[1]))
    vivos, soando, cur = {}, 0.0, None
    for t, on, n, p in ev:
        ch = (p, n)
        if on:
            o = vivos.get(ch)
            if o:
                o[0] += 1
                o[1] = t
            else:
                vivos[ch] = [1, t]
        else:
            o = vivos.get(ch)
            if o:
                o[0] -= 1
                if o[0] <= 0:
                    vivos.pop(ch, None)
        # mesma ordem do site: prioridade, depois a nota que entrou por último, depois a altura
        b = max(vivos, key=lambda c: (c[0], vivos[c][1], c[1]))[1] if vivos else None
        if cur is not None and cur[1] != b:
            if t > cur[0] + .005:
                soando += t - cur[0]
            cur = None
        if b is not None and cur is None:
            cur = (t, b)
    if cur is not None:
        soando += max(0.0, dur - cur[0])
    tnotas = sum(t1 - t0 for k, f in enumerate(faixas) if atrib[k] == lado for t0, t1, _ in f.notas)
    return soando, tnotas


def aproveitamento(faixas, dur):
    """Devolve (0..1) quanto da música sobrevive à redução a dois canais monofônicos."""
    occ, nb = _ocupacao(faixas, dur)
    tam = [sum(a) for a in occ]
    cand = [i for i, f in enumerate(faixas)
            if f.chan != 9 and not (not f.gm and GM_BATERIA.search(f.nome)) and f.notas]
    if len(cand) < 2:
        if not cand:
            return 0.0
        i = cand[0]
        atrib = ['O'] * len(faixas)
        atrib[i] = 'L'
        soa, tn = _linha(faixas, atrib, [0] * len(faixas), 'L', dur)
        return .5 * (soa / tn if tn else 0) + .5 * min(1.0, soa / dur)

    # mesmo critério do preset "melodia inteira" do site, para a medida bater com o que se ouve
    li = max(cand, key=lambda i: nota_lead(medir_faixa(faixas[i], dur)))
    # instrumental, ou transcrição só de acompanhamento: a porteira zera todas as faixas, e aí
    # vale a que mais ocupa o tempo, para não cair na primeira por acaso
    if not nota_lead(medir_faixa(faixas[li], dur)):
        li = max(cand, key=lambda i: tam[i])
    resto = sorted([i for i in cand if i != li], key=lambda i: -tam[i])
    atrib = ['O'] * len(faixas)
    pr = [0] * len(faixas)
    atrib[li], pr[li] = 'R', 3
    base = resto[0]
    atrib[base], pr[base] = 'L', 2
    cheio = bytearray(occ[base])
    for i in resto[1:]:
        novo = sum(1 for k in range(nb) if occ[i][k] and not cheio[k])
        if novo < nb * .06 or novo < tam[i] * .3:
            continue
        atrib[i], pr[i] = 'L', 1
        for k in range(nb):
            if occ[i][k]:
                cheio[k] = 1
    soaL, tnL = _linha(faixas, atrib, pr, 'L', dur)
    soaR, tnR = _linha(faixas, atrib, pr, 'R', dur)
    guardado = min(soaL / tnL if tnL else 0, soaR / tnR if tnR else 0)   # o canal mais sacrificado
    ativo = min(1.0, (soaL + soaR) / (2 * dur)) if dur else 0
    return .55 * guardado + .45 * ativo


# ---------------------------------------------------------------- curadoria
def destaque(titulo):
    t = sem_acento(titulo)
    return any(d in t for d in DESTAQUES)


def obra_de(titulo):
    """Reduz o título à obra, para que os movimentos dela caiam todos no mesmo grupo.

    'French Suite no. 3 (BWV 814) - 07'          -> 'french suite (bwv 814)'
    '14 Canons - 10 (BWV 1087)'                  -> '14 canons (bwv 1087)'
    '8 Petites Pièces for Guitar, No. 3 (Op. 3)' -> '8 petites pieces for guitar (op. 3)'
    'Für Elise (WoO 59) (2)'                     -> 'fur elise (woo 59)'
    """
    t = RX_COPIA.sub('', titulo)
    t = RX_MOV.sub('', t)
    t = RX_NUM.sub('', t)
    return re.sub(r'\s{2,}', ' ', sem_acento(t)).strip(' ,-')


def examinar(caminho, dur_min, notas_min):
    try:
        faixas = ler_midi(caminho.read_bytes())
    except Exception as e:
        return None, f'ilegível ({e})'
    if not faixas:
        return None, 'sem notas'
    notas = sum(len(f.notas) for f in faixas)
    dur = max(n[1] for f in faixas for n in f.notas)
    if dur < dur_min:
        return None, f'curta demais ({dur:.0f} s)'
    if notas < notas_min:
        return None, f'poucas notas ({notas})'
    return {'dur': dur, 'notas': notas, 'faixas': len(faixas),
            'score': aproveitamento(faixas, dur + .3)}, None


def remover_vazias(raiz):
    """Apaga as pastas que ficaram sem nada dentro.

    No Windows as pastas vindas do Mutopia chegam com o atributo ReadOnly, e aí rmdir() falha
    com "Acesso negado" mesmo estando vazia. Tira o atributo e tenta de novo; se ainda assim
    não for, segue em frente — pasta vazia a mais não estraga o acervo.
    """
    sobraram = 0
    for d in sorted(raiz.rglob('*'), key=lambda p: -len(p.parts)):
        if not d.is_dir() or any(d.iterdir()):
            continue
        try:
            d.rmdir()
        except OSError:
            try:
                d.chmod(stat.S_IWRITE)
                d.rmdir()
            except OSError:
                sobraram += 1
    return sobraram


def listar(pasta):
    """Cada .mid com seu compositor, aceitando o acervo achatado e o já reorganizado."""
    saida = []
    for arq in sorted(pasta.rglob('*.mid')):
        partes = arq.relative_to(pasta).parts
        if len(partes) == 2:
            comp = partes[0]
        elif len(partes) == 3 and partes[0] in REGIOES:
            comp = partes[1]
        else:
            continue
        saida.append((arq, comp))
    return saida


def curar(args):
    if not PASTA.is_dir():
        sys.exit(f'não achei {PASTA}')
    creditos = {}
    arq_cred = PASTA / 'creditos.json'
    if arq_cred.is_file():
        creditos = json.loads(arq_cred.read_text(encoding='utf-8'))

    arquivos = listar(PASTA)
    print(f'{len(arquivos)} arquivos em musicas/classicos\n')

    fora = {}
    corta = lambda motivo: fora.__setitem__(motivo, fora.get(motivo, 0) + 1)
    candidatos, vistos = [], {}
    for i, (arq, comp) in enumerate(arquivos):
        if args.verbose and i % 500 == 0:
            print(f'  lendo… {i}/{len(arquivos)}', file=sys.stderr)
        rel_antiga = arq.relative_to(PASTA).as_posix()
        # numa segunda rodada o arquivo já está em <região>/<compositor>/, mas o creditos.json
        # pode ainda estar com a chave antiga, só <compositor>/: aceita as duas formas
        info = creditos.get(rel_antiga) or creditos.get(f'{comp}/{arq.name}') or {}
        titulo = arq.stem
        eh_destaque = destaque(titulo)
        if info.get('estilo') == 'Technique' or (RX_ESTUDO.search(titulo) and not eh_destaque):
            corta('método ou estudo')
            continue
        if comp not in CASA:
            corta('compositor fora da tabela')
            continue
        # arquivo byte a byte igual a outro: o acervo tem 57 desses
        assinatura = hashlib.md5(arq.read_bytes()).hexdigest()
        if assinatura in vistos:
            corta('cópia idêntica de outro arquivo')
            continue
        vistos[assinatura] = arq
        med, motivo = examinar(arq, args.duracao_minima, NOTAS_MIN)
        if med is None:
            corta(motivo.split(' (')[0])
            continue
        candidatos.append({
            'arq': arq, 'comp': comp, 'rel': rel_antiga, 'info': info, 'titulo': titulo,
            'obra': obra_de(titulo), 'destaque': eh_destaque, **med,
        })

    # 1) Cada peça do Mutopia chega repartida em vários arquivos, e o sufixo " - NN" do título
    #    não quer dizer movimento: em "Air (BWV 1068)" os cinco arquivos têm a mesma duração e
    #    são a partitura inteira (4 faixas, 516 notas) mais cada parte de instrumento sozinha.
    #    Já na "French Suite no. 3" os 14 arquivos são 7 movimentos, cada um gravado duas vezes.
    #
    #    O que separa um caso do outro é a duração. Então: agrupo pela peça do Mutopia, separo
    #    os movimentos pela duração, e de cada movimento fico com o arquivo mais completo — que
    #    é a partitura inteira, a única que serve para repartir entre dois canais.
    por_peca = {}
    for c in candidatos:
        peca = c['info'].get('mutopia') or f'{c["comp"]}/{c["obra"]}'
        por_peca.setdefault(peca, []).append(c)
    passo1, descartadas = [], 0
    for grupo in por_peca.values():
        movimentos = []
        for c in sorted(grupo, key=lambda c: c['dur']):
            # mesma duração, a menos de uma folga: é a mesma música, não outro movimento
            if movimentos and c['dur'] - movimentos[-1][0]['dur'] <= max(1.5, c['dur'] * .02):
                movimentos[-1].append(c)
            else:
                movimentos.append([c])
        melhores = []
        for m in movimentos:
            m.sort(key=lambda c: (c['faixas'], c['notas']), reverse=True)
            melhores.append(m[0])
            descartadas += len(m) - 1
        melhores.sort(key=lambda c: (not c['destaque'], -c['score']))
        descartadas += max(0, len(melhores) - args.movimentos)
        passo1 += melhores[:args.movimentos]
    if descartadas:
        fora['parte de instrumento ou movimento além da cota'] = descartadas

    # 2) cota por compositor, com os destaques na frente
    por_comp = {}
    for c in passo1:
        por_comp.setdefault(c['comp'], []).append(c)
    ficam = []
    for comp, grupo in por_comp.items():
        grupo.sort(key=lambda c: (not c['destaque'], -c['score']))
        ficam += grupo[:COTA[comp]]
    ficam.sort(key=lambda c: (CASA[c['comp']], sem_acento(c['comp']), sem_acento(c['titulo'])))

    saem = [a for a, _ in arquivos if a not in {c['arq'] for c in ficam}]
    print(f'ficam {len(ficam)}, saem {len(saem)}\n')
    print('motivos de corte antes da cota:')
    for k, v in sorted(fora.items(), key=lambda x: -x[1]):
        print(f'  {v:5}  {k}')
    print('\npor região:')
    for reg in REGIOES:
        g = [c for c in ficam if CASA[c['comp']] == reg]
        comps = len({c['comp'] for c in g})
        print(f'  {len(g):4} peças · {comps:2} compositores  {reg}')

    if args.listar:
        print()
        reg_atual = comp_atual = None
        for c in ficam:
            if CASA[c['comp']] != reg_atual:
                reg_atual = CASA[c['comp']]
                comp_atual = None
                print(f'\n{reg_atual}')
            if c['comp'] != comp_atual:
                comp_atual = c['comp']
                print(f'  {comp_atual}')
            marca = '*' if c['destaque'] else ' '
            print(f'   {marca} {c["score"]:.2f}  {c["dur"]:5.0f}s  {c["titulo"][:62]}')

    if not args.aplicar:
        print('\nnada foi alterado. Rode com --aplicar para valer.')
        return

    # ---- aplica: move o que fica, apaga o resto, reescreve os créditos
    novos = {}
    for c in ficam:
        destino = PASTA / CASA[c['comp']] / c['comp'] / c['arq'].name
        destino.parent.mkdir(parents=True, exist_ok=True)
        if c['arq'] != destino:
            shutil.move(str(c['arq']), str(destino))
            lado = c['arq'].with_suffix('.json')          # configuração pronta, se houver
            if lado.is_file():
                shutil.move(str(lado), str(destino.with_suffix('.json')))
        info = dict(c['info'])
        info['regiao'] = CASA[c['comp']]
        novos[destino.relative_to(PASTA).as_posix()] = info
    for arq in saem:
        arq.unlink(missing_ok=True)
        arq.with_suffix('.json').unlink(missing_ok=True)
    # os créditos vão para o disco antes da faxina: são eles que guardam a atribuição exigida
    # pelas licenças, e não podem se perder porque uma pasta vazia resistiu a sumir
    arq_cred.write_text(json.dumps(novos, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    sobraram = remover_vazias(PASTA)
    print(f'\npronto: {len(ficam)} arquivos em musicas/classicos/<região>/<compositor>/')
    if sobraram:
        print(f'({sobraram} pastas vazias resistiram a sumir; pode apagar à mão)')
    print('creditos.json reescrito. Rode tools/gerar_acervo.py para refazer o índice.')


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--aplicar', action='store_true', help='move e apaga de verdade')
    p.add_argument('--listar', action='store_true', help='imprime tudo que fica')
    p.add_argument('--movimentos', type=int, default=MOV_MAX, help=f'movimentos por obra (padrão {MOV_MAX})')
    p.add_argument('--duracao-minima', type=float, default=DUR_MIN, help=f'segundos (padrão {DUR_MIN:.0f})')
    p.add_argument('-v', '--verbose', action='store_true', help='mostra o progresso da leitura')
    curar(p.parse_args())


if __name__ == '__main__':
    main()
