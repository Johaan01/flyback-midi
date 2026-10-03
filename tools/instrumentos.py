"""Descobre que instrumentos uma gravação tem, para dizer ao MuScriptor o que esperar.

A lista de instrumentos que se passa ao MuScriptor não é um filtro: é o condicionamento do
modelo, que passa a esperar exatamente aqueles instrumentos. Com a lista certa, a voz de
Borboletas sai na faixa de voz (60% de concordância com a versão do Mirelo); sem lista, o modelo
põe metade do canto no violão (22%). Só que ninguém sabe de cabeça a instrumentação de cada
música — e o site do MuScriptor não detecta nada, repassa o que o usuário marca.

Então a detecção é feita por outra IA, o PANNs (Cnn14 treinado no AudioSet do Google, que
reconhece 527 classes de som, entre elas canto e dezenas de instrumentos), aplicado não na
mistura, onde só se ouve o instrumento dominante, mas em cada stem que o Demucs separa:

- voz: o **peso do stem de voz** na mistura, não o rótulo. O PANNs reconhece canto em quatro
  de cinco músicas, mas em Do Fundo da Grota dá 0,04 — o stem de voz vem cheio do acordeão. O
  peso separa limpo: 0,48 a 0,61 com canto, 0,04 a 0,12 em instrumental. O corte é 0,2, e não
  0,3 como começou: em Paranoid (remaster de 2012, guitarra muito à frente) a voz pesa 0,28;
- baixo: "Bass guitar" no stem de baixo (0,60 a 0,91 quando há; 0,06 numa orquestra; 0,29 em
  Paranoid, pelo mesmo motivo — corte também em 0,2);
- bateria: "Drum kit" no stem de bateria (0,13 a 0,72; tímpano de orquestra fica em 0,08);
- o resto: os rótulos do stem "other", traduzidos para os grupos do MuScriptor.

Calibrado em sete gravações — cinco com voz (sertanejo, música gaúcha, rock, metal, abertura de
anime) e duas sem (Satriani e Grieg orquestral). O stem "other" é o elo fraco: acerta violão,
acordeão, metais e cordas, mas em BLOODY STREAM toma guitarra distorcida por órgão. Para o arco
isso pesa pouco — o que pesa é a voz vir na faixa dela, e essa parte é a mais firme.

Os pesos do PANNs (327 MB, Zenodo) e a lista de rótulos (Google) são baixados na primeira vez
para ~/panns_data. O pacote `panns_inference` tentaria baixá-los com wget, que não existe no
Windows.
"""
import urllib.request
from pathlib import Path

import numpy as np

PANNS = Path.home() / 'panns_data'
ARQUIVOS = {
    'class_labels_indices.csv':
        'http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/class_labels_indices.csv',
    'Cnn14_mAP=0.431.pth':
        'https://zenodo.org/record/3987831/files/Cnn14_mAP%3D0.431.pth?download=1',
}
SR = 32000          # taxa do PANNs
JANELA = 10.0       # segundos por janela de análise

# rótulos do AudioSet no stem "other" -> grupo do MuScriptor
FAMILIAS = {
    'organ': ['Accordion', 'Organ', 'Electronic organ', 'Hammond organ', 'Harmonica', 'Bagpipes'],
    'acoustic_guitar': ['Acoustic guitar', 'Banjo', 'Mandolin', 'Ukulele', 'Steel guitar, slide guitar'],
    'eletrica': ['Electric guitar'],
    'acoustic_piano': ['Piano', 'Harpsichord'],
    'electric_piano': ['Electric piano'],
    'synth_pad': ['Synthesizer', 'Sampler'],
    'brass_section': ['Brass instrument', 'Trumpet', 'Trombone', 'French horn'],
    'string_ensemble': ['Orchestra', 'String section', 'Bowed string instrument', 'Violin, fiddle', 'Cello', 'Pizzicato'],
    'tenor_sax': ['Saxophone'],
    'flutes': ['Flute'],
    'clarinet': ['Clarinet'],
    'orchestral_harp': ['Harp'],
    'chromatic_percussion': ['Marimba, xylophone', 'Glockenspiel', 'Vibraphone', 'Steelpan'],
}
# gênero na mistura que decide se a guitarra elétrica é distorcida
ROCK = ['Rock music', 'Heavy metal', 'Punk rock', 'Grunge', 'Progressive rock', 'Psychedelic rock', 'Rock and roll']


def preparar():
    """Baixa o que faltar em ~/panns_data. Precisa existir antes de importar panns_inference."""
    PANNS.mkdir(exist_ok=True)
    for nome, url in ARQUIVOS.items():
        alvo = PANNS / nome
        if not alvo.exists() or alvo.stat().st_size == 0:
            print(f'  baixando {nome}…', flush=True)
            tmp = alvo.with_suffix('.parcial')
            urllib.request.urlretrieve(url, tmp)
            tmp.replace(alvo)


def _janelas(y):
    n = int(JANELA * SR)
    bl = [y[i:i + n] for i in range(0, len(y) - n // 2, n)] or [y]
    return np.stack([np.pad(b, (0, n - len(b))) for b in bl])


def _ouvir(tagger, y):
    b = _janelas(y)
    return b, np.concatenate([tagger.inference(b[i:i + 8])[0] for i in range(0, len(b), 8)])


def detectar(stems, sr, mistura, dispositivo='cuda'):
    """(lista de grupos do MuScriptor, linhas de evidência) para os stems do Demucs.

    `stems` é {'vocals'|'drums'|'bass'|'other': onda mono}, `mistura` a onda mono original,
    as duas na taxa `sr`.
    """
    import librosa
    preparar()
    from panns_inference import AudioTagging, labels
    pos = {l: i for i, l in enumerate(labels)}
    tagger = AudioTagging(checkpoint_path=str(PANNS / 'Cnn14_mAP=0.431.pth'), device=dispositivo)

    para32 = lambda y: librosa.resample(np.asarray(y, dtype=np.float32), orig_sr=sr, target_sr=SR)
    mix = para32(mistura)
    rms_mix = float(np.sqrt(np.mean(mix ** 2))) or 1e-9
    _, Pmix = _ouvir(tagger, mix)

    medida = {}
    for nome in ('vocals', 'drums', 'bass', 'other'):
        y = para32(stems[nome])
        b, P = _ouvir(tagger, y)
        # janela calada não conta: no silêncio o PANNs chuta qualquer coisa
        vivas = np.sqrt((b ** 2).mean(1)) > .1 * rms_mix
        Pv = P[vivas] if vivas.any() else P[:1] * 0
        medida[nome] = {'peso': float(np.sqrt(np.mean(y ** 2)) / rms_mix), 'ativo': float(vivas.mean()),
                        'media': Pv.mean(0), 'presenca': (Pv > .2).mean(0)}
    m = lambda stem, rot: float(medida[stem]['media'][pos[rot]])
    pr = lambda stem, rot: float(medida[stem]['presenca'][pos[rot]])

    lista, prova = [], []
    v = medida['vocals']
    if v['peso'] >= .2 and v['ativo'] >= .4:
        lista.append('voice')
    prova.append(f'voz: stem com peso {v["peso"]:.2f}, ativo em {v["ativo"]*100:.0f}% do tempo')

    baixo = m('bass', 'Bass guitar')
    if m('bass', 'Double bass') >= .15 and m('bass', 'Double bass') > baixo:
        lista.append('contrabass')
    elif baixo >= .2:
        lista.append('electric_bass')
    prova.append(f'baixo: "Bass guitar" {baixo:.2f}, "Double bass" {m("bass", "Double bass"):.2f}')

    kit, timp = m('drums', 'Drum kit'), m('drums', 'Timpani')
    if kit >= .1 and kit >= timp:
        lista.append('drums')
    if timp >= .1 and timp > kit:
        lista.append('timpani')
    prova.append(f'bateria: "Drum kit" {kit:.2f}, "Timpani" {timp:.2f}')

    # resto: cada família vale se algum rótulo dela aparece com força ou com constância
    forca = {}
    for grupo, rotulos in FAMILIAS.items():
        forca[grupo] = max(max(m('other', r), .5 * pr('other', r)) for r in rotulos if r in pos)
    achados = [g for g, f in forca.items() if f >= .12]
    # "Guitar" genérico forte sem dizer qual: decide pela que pontuou mais
    guit = m('other', 'Guitar')
    if guit >= .3 and 'acoustic_guitar' not in achados and 'eletrica' not in achados:
        achados.append('acoustic_guitar' if m('other', 'Acoustic guitar') >= m('other', 'Electric guitar') else 'eletrica')
    rock = max(float(Pmix.mean(0)[pos[g]]) for g in ROCK)
    # Stem "other" com corpo mas sem nenhum rótulo firme — em Livin' On A Prayer, teclado e
    # guitarra sob a voz. Deixar a lista só com voz, baixo e bateria é o pior caso: o modelo
    # tem de pôr esse acompanhamento em algum lugar, e o lugar disponível é a faixa de voz.
    # Uma guitarra na lista dá a ele onde pôr.
    if not achados and medida['other']['peso'] >= .25:
        achados.append('eletrica' if rock >= .1 else 'acoustic_guitar')
    if 'eletrica' in achados:
        achados[achados.index('eletrica')] = 'distorted_electric_guitar' if rock >= .1 else 'clean_electric_guitar'
    for g in sorted(achados, key=lambda g: -forca.get(g, guit)):
        lista.append(g)
    fortes = sorted(forca.items(), key=lambda x: -x[1])[:4]
    prova.append('resto: ' + ', '.join(f'{g} {f:.2f}' for g, f in fortes) + f'; "Guitar" {guit:.2f}; rock na mistura {rock:.2f}')

    del tagger
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:
        pass
    return lista, prova
