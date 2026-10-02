#!/usr/bin/env python3
"""Gera MIDI a partir de uma gravação, separando voz, baixo e acompanhamento em faixas.

    python tools/transcrever.py musica.mp3
    python tools/transcrever.py musica.mp3 --saida "musicas/unsorted" --titulo "Banda - Música"
    python tools/transcrever.py --url "https://..."        # precisa de yt-dlp instalado

Por que isto existe: o acervo vive de transcrição feita por fã, e a qualidade varia muito —
boa parte não tem a linha de canto, ou tem acorde onde deveria ter melodia. Transcrever direto
do áudio tira a interpretação de terceiros do caminho.

E o problema fica mais fácil do que parece justamente por causa do aparelho. Cada flyback é
monofônico: toca uma nota por vez. Então não é preciso resolver transcrição polifônica, que é
o problema difícil — basta rastrear a **altura dominante de cada stem**, que é o problema
fácil e onde o resultado é confiável. Daí saem exatamente as linhas de que o site precisa:

    vocal      melodia principal, uma nota por vez
    baixo      linha de baixo, uma nota por vez
    harmonia   o que sobra (guitarras, teclas), reduzido à voz mais saliente

O caminho:

  1. Separação de stems com Hybrid Demucs, que vem embutido no torchaudio
     (`HDEMUCS_HIGH_MUSDB_PLUS`) — não precisa do pacote `demucs`.
  2. Rastreio de altura por faixa com pYIN (librosa), que é estimador monofônico e devolve,
     por quadro, a frequência e a probabilidade de haver som com altura definida.
  3. Os quadros viram notas: junta quadros vizinhos de mesma altura, descarta nota curta
     demais, e a energia do trecho vira a velocity.

A bateria é separada mas não transcrita: percussão não tem altura definida, e o site já
mantém faixa de percussão fora dos presets.

Precisa de torch, torchaudio e librosa — ao contrário do resto de `tools/`, que é só
biblioteca padrão. É opcional: nada no site depende disto.
"""
import argparse
import math
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DIV = 480          # ticks por semínima no MIDI gerado
BPM = 120          # andamento nominal; as notas vão em tempo absoluto, então não altera o som

# Faixa de busca de altura por stem, em Hz. Limitar ajuda muito o pYIN: fora destes limites
# ele erra oitava, que é o erro mais comum e o mais audível.
STEMS = {
    'vocals': {'nome': 'Vocal', 'programa': 85, 'fmin': 80.0, 'fmax': 1100.0, 'min_dur': .08},
    'bass': {'nome': 'Baixo', 'programa': 33, 'fmin': 38.0, 'fmax': 400.0, 'min_dur': .10},
    'other': {'nome': 'Harmonia', 'programa': 30, 'fmin': 70.0, 'fmax': 1600.0, 'min_dur': .10},
}
ORDEM = ['vocals', 'bass', 'other']


def log(*a):
    print(*a, flush=True)


def achar_no_winget(*programas):
    """Garante que estes programas estejam no PATH do processo.

    O yt-dlp precisa do ffmpeg para extrair o áudio e, desde 2025, de um runtime JavaScript
    (deno) para o extrator do YouTube. Instalados pelo winget, eles só entram no PATH depois de
    reabrir o terminal — e quem acabou de rodar a instalação não tem por que saber disso.
    """
    import os
    import shutil
    base = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'WinGet'
    faltam = []
    for nome in programas:
        if shutil.which(nome):
            continue
        achou = False
        for raiz in (base / 'Links', base / 'Packages'):
            if not raiz.is_dir():
                continue
            for p in raiz.rglob(nome + '.exe'):
                os.environ['PATH'] = str(p.parent) + os.pathsep + os.environ.get('PATH', '')
                achou = True
                break
            if achou:
                break
        if not achou:
            faltam.append(nome)
    return faltam


# ---------------------------------------------------------------- entrada
def baixar(url, destino):
    """Áudio de uma URL, via yt-dlp. Quem roda responde pelo uso: baixar do YouTube contraria
    os termos de uso do serviço."""
    faltam = achar_no_winget('ffmpeg', 'deno')
    if 'ffmpeg' in faltam:
        sys.exit('não achei o ffmpeg, que o yt-dlp precisa para extrair o áudio.\n'
                 'Instale com: winget install Gyan.FFmpeg')
    if 'deno' in faltam:
        log('  (sem runtime JavaScript; o extrator do YouTube pode falhar — '
            'winget install DenoLand.Deno)')
    saida = destino / 'baixado.%(ext)s'
    cmd = ['yt-dlp', '-x', '--audio-format', 'wav', '--audio-quality', '0',
           '-o', str(saida), '--no-playlist', url]
    log('baixando…')
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        sys.exit(f'yt-dlp falhou:\n{r.stderr[-1500:]}')
    achados = sorted(destino.glob('baixado.*'))
    if not achados:
        sys.exit('yt-dlp não deixou arquivo nenhum')
    return achados[0]


def titulo_de(url):
    r = subprocess.run(['yt-dlp', '--no-playlist', '--print', '%(artist,uploader)s - %(title)s', url],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ''


# ---------------------------------------------------------------- separação
def separar(caminho, dispositivo):
    """Devolve {nome do stem: onda mono em 44,1 kHz} usando o Hybrid Demucs do torchaudio."""
    import librosa
    import numpy as np
    import torch
    from torchaudio.pipelines import HDEMUCS_HIGH_MUSDB_PLUS as PIPE

    modelo = PIPE.get_model()
    nomes = list(getattr(modelo, 'sources', ['drums', 'bass', 'other', 'vocals']))
    modelo = modelo.to(dispositivo).eval()
    sr = PIPE.sample_rate
    # carregado pelo librosa, e não pelo torchaudio.load: a partir da versão 2.11 ele delega a
    # leitura ao torchcodec, que é mais uma dependência pesada para fazer o que já temos
    dados, _ = librosa.load(str(caminho), sr=sr, mono=False)
    if dados.ndim == 1:
        dados = np.stack([dados, dados])
    onda = torch.from_numpy(np.ascontiguousarray(dados[:2])).float()

    ref = onda.mean(0)
    onda = (onda - ref.mean()) / (ref.std() + 1e-8)

    # Em pedaços, com sobreposição: a música inteira de uma vez não cabe em 6 GB de VRAM.
    trecho = int(sr * 20.0)
    borda = int(sr * 1.0)
    saida = None
    pos = 0
    with torch.no_grad():
        while pos < onda.shape[1]:
            ini = max(0, pos - borda)
            fim = min(onda.shape[1], pos + trecho + borda)
            pedaco = onda[:, ini:fim].unsqueeze(0).to(dispositivo)
            r = modelo(pedaco)[0].cpu()
            if saida is None:
                saida = torch.zeros(r.shape[0], 2, onda.shape[1])
            a = pos - ini
            b = a + min(trecho, onda.shape[1] - pos)
            saida[:, :, pos:pos + (b - a)] = r[:, :, a:b]
            pos += trecho
            log(f'  separando… {min(100, int(100 * pos / onda.shape[1]))}%')
    saida = saida * (ref.std() + 1e-8) + ref.mean()
    return {n: saida[i].mean(0).numpy() for i, n in enumerate(nomes)}, sr


# ---------------------------------------------------------------- altura -> notas
def notas_do_stem(onda, sr, cfg):
    """Rastreia a altura dominante e devolve [(inicio, fim, nota MIDI, velocity)]."""
    import librosa
    import numpy as np

    hop = 256
    # A janela tem de caber dois períodos da frequência mais grave procurada, senão o pYIN não
    # tem o que correlacionar e devolve quadro nenhum — foi o que aconteceu com o baixo, que
    # com fmin de 38 Hz precisa de 2.321 amostras e estava recebendo 2.048: não achava nada.
    janela = 1
    while janela < 2 * sr / cfg['fmin']:
        janela *= 2
    janela = max(2048, janela)
    f0, voz, prob = librosa.pyin(onda.astype('float32'), sr=sr,
                                 fmin=cfg['fmin'], fmax=cfg['fmax'],
                                 frame_length=janela, hop_length=hop, fill_na=np.nan)
    if f0 is None or not np.any(np.isfinite(f0)):
        return []
    rms = librosa.feature.rms(y=onda.astype('float32'), frame_length=janela, hop_length=hop)[0]
    rms = rms[:len(f0)] if len(rms) >= len(f0) else np.pad(rms, (0, len(f0) - len(rms)))
    pico = float(rms.max()) or 1.0

    midi = np.where(np.isfinite(f0), librosa.hz_to_midi(np.nan_to_num(f0, nan=1.0)), np.nan)
    # Suaviza a altura antes de arredondar. Vibrato e portamento fazem a frequência oscilar em
    # torno da fronteira de semitom; sem isto a mesma nota sustentada vira dezenas de
    # fragmentos de poucos quadros, cada um curto demais para passar na duração mínima, e a
    # melodia simplesmente some. A mediana preserva o degrau de uma nota para a outra, que uma
    # média borraria.
    from scipy.ndimage import median_filter
    suave = midi.copy()
    bons = np.isfinite(suave)
    if bons.any():
        idx = np.arange(len(suave))
        suave[~bons] = np.interp(idx[~bons], idx[bons], suave[bons])
        suave = median_filter(suave, size=9, mode='nearest')
        suave[~bons] = np.nan
    arred = np.where(np.isfinite(suave), np.round(suave), np.nan)
    # Vale a decisão do pYIN (voz), não a posterior quadro a quadro (prob). As duas discordam
    # muito: num vocal separado, o Viterbi marca 50% dos quadros como sonoros e só 9% deles
    # têm prob acima de 0,55 — filtrar por prob jogava fora quatro quintos da melodia, e a
    # música saía com 62 notas em quatro minutos. O Viterbi é melhor porque usa continuidade
    # temporal; prob fica só como piso contra lixo. A energia corta sopro e reverberação.
    # Sem piso em prob: ele discorda do Viterbi quase metade do tempo. Num vocal separado o
    # Viterbi aceita 101 s de 201 s, e exigir prob acima de apenas 0,1 derruba para 55 s —
    # quase metade da melodia jogada fora por uma salvaguarda que não salvaguarda nada.
    # A energia continua, para cortar o rastro de reverberação que sobra na separação.
    valido = np.isfinite(arred) & voz & (rms > pico * .02)

    t = lambda k: k * hop / sr
    bruto, ini, atual = [], None, None
    for k in range(len(arred)):
        n = arred[k] if valido[k] else None
        if atual is not None and (n is None or n != atual):
            bruto.append((ini, k, int(atual)))
            atual, ini = None, None
        if n is not None and atual is None:
            atual, ini = n, k
    if atual is not None:
        bruto.append((ini, len(arred), int(atual)))

    # Primeiro junta, depois descarta por duração — nesta ordem. O pYIN pisca em consoante e
    # em vibrato, e a mesma nota sustentada sai como vários trechos de poucos quadros. Medindo
    # a duração antes de juntar, cada pedaço reprova sozinho e a nota inteira se perde: era o
    # que fazia 864 trechos somando 55 s virarem 36 s de nota.
    unidas = []
    for a, b, n in bruto:
        if unidas and unidas[-1][2] == n and t(a) - t(unidas[-1][1]) < .07:
            unidas[-1] = (unidas[-1][0], b, n)
        else:
            unidas.append((a, b, n))

    notas = []
    for a, b, n in unidas:
        if t(b) - t(a) < cfg['min_dur']:
            continue
        energia = float(rms[a:b].mean()) if b > a else 0.0
        vel = int(max(28, min(127, round(28 + 99 * (energia / pico) ** .6))))
        notas.append((t(a), t(b), n, vel))
    return corrigir_oitavas(notas)


def corrigir_oitavas(notas, folga=14):
    """Puxa de volta a nota que caiu de oitava.

    É o engano mais comum do rastreio de altura: o estimador trava no subharmônico e a nota vai
    uma oitava abaixo. São poucas — 5% do vocal na primeira música medida — mas muito audíveis,
    porque quebram a linha justamente onde ela deveria seguir. A folga é generosa (14 semitons,
    mais de uma oitava) para não achatar melodia que de fato tem extensão larga: só é corrigido
    o que está longe demais para ser canto da mesma pessoa.
    """
    if len(notas) < 8:
        return notas
    import statistics
    med = statistics.median(n for _, _, n, _ in notas)
    saida = []
    for a, b, n, v in notas:
        while n < med - folga and n + 12 <= 127:
            n += 12
        while n > med + folga and n - 12 >= 0:
            n -= 12
        saida.append((a, b, n, v))
    return saida


# ---------------------------------------------------------------- escrita do MIDI
def vlq(n):
    saida = bytes([n & 0x7F])
    n >>= 7
    while n:
        saida = bytes([(n & 0x7F) | 0x80]) + saida
        n >>= 7
    return saida


def escrever_midi(faixas, titulo):
    """faixas: [(nome, programa, [(ini, fim, nota, vel)])] em segundos. SMF formato 1."""
    tk = lambda seg: int(round(seg * BPM / 60 * DIV))

    def trilha(eventos):
        eventos.sort(key=lambda e: (e[0], e[1]))
        corpo, ult = b'', 0
        for t, _, dados in eventos:
            corpo += vlq(t - ult) + dados
            ult = t
        return b'MTrk' + struct.pack('>I', len(corpo) + 4) + corpo + b'\x00\xff\x2f\x00'

    txt = lambda tipo, s: bytes([0xFF, tipo]) + vlq(len(s.encode('utf-8'))) + s.encode('utf-8')
    cab = [(0, 0, txt(3, titulo)),
           (0, 0, b'\xff\x51\x03' + round(60e6 / BPM).to_bytes(3, 'big')),
           (0, 0, bytes([0xFF, 0x58, 4, 4, 2, 24, 8]))]
    trilhas = [trilha(cab)]
    for canal, (nome, programa, notas) in enumerate(faixas):
        c = canal if canal < 9 else canal + 1          # pula o canal 10, que é percussão
        ev = [(0, 0, txt(3, nome)), (0, 1, bytes([0xC0 | c, programa]))]
        for a, b, n, v in notas:
            if 0 <= n < 128 and b > a:
                ev.append((tk(a), 3, bytes([0x90 | c, n, v])))
                ev.append((max(tk(a) + 1, tk(b)), 2, bytes([0x80 | c, n, 0])))
        trilhas.append(trilha(ev))
    return b'MThd' + struct.pack('>IHHH', 6, 1, len(trilhas), DIV) + b''.join(trilhas)


# ---------------------------------------------------------------- principal
def transcrever(args):
    import torch

    tmp = Path(tempfile.mkdtemp(prefix='flyback-'))
    titulo = args.titulo or ''
    if args.url:
        if not titulo:
            titulo = titulo_de(args.url)
        audio = baixar(args.url, tmp)
    else:
        audio = Path(args.audio)
        if not audio.is_file():
            sys.exit(f'não achei o arquivo: {audio}')
    titulo = titulo or audio.stem

    disp = 'cuda' if torch.cuda.is_available() and not args.cpu else 'cpu'
    log(f'"{titulo}"  ·  {disp}')

    stems, sr = separar(audio, disp)
    faixas = []
    for chave in ORDEM:
        if chave not in stems:
            continue
        cfg = STEMS[chave]
        log(f'  transcrevendo {cfg["nome"]}…')
        notas = notas_do_stem(stems[chave], sr, cfg)
        log(f'    {len(notas)} notas')
        if notas:
            faixas.append((cfg['nome'], cfg['programa'], notas))
    if not faixas:
        sys.exit('não saiu nota nenhuma — o áudio é instrumental puro ou muito curto?')

    saida = Path(args.saida) if args.saida else (RAIZ / 'musicas' / 'unsorted')
    if not saida.is_absolute():
        saida = RAIZ / saida
    saida.mkdir(parents=True, exist_ok=True)
    limpo = ''.join(c for c in titulo if c not in '\\/:*?"<>|').strip() or 'transcricao'
    arq = saida / f'{limpo}.mid'
    arq.write_bytes(escrever_midi(faixas, limpo))
    total = sum(len(n) for _, _, n in faixas)
    log(f'\npronto: {arq}  ({len(faixas)} faixas, {total} notas)')
    return arq


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('audio', nargs='?', help='arquivo de áudio de entrada')
    p.add_argument('--url', help='endereço para o yt-dlp baixar')
    p.add_argument('--titulo', help='nome da música no acervo')
    p.add_argument('--saida', help='pasta de destino (padrão: musicas/unsorted)')
    p.add_argument('--cpu', action='store_true', help='não usar a GPU')
    args = p.parse_args()
    if not args.audio and not args.url:
        p.error('passe um arquivo de áudio ou --url')
    transcrever(args)


if __name__ == '__main__':
    main()
