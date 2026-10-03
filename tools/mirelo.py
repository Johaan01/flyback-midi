"""Transcrição pela API do Mirelo (api.mirelo.ai), para quando se quer a fidelidade deles.

Usado pelo servidor.py quando a janela "Baixar músicas" do site pede "Mirelo". Segue a
documentação pública (mirelo.ai/api-docs):

1. o áudio sobe como asset: POST /v3/assets devolve um endereço e campos de formulário, e o
   arquivo vai por um POST multipart para lá, como a última parte, chamada 'file';
2. detecção de instrumentos: POST /v2/audio-to-midi/v1.0/instruments — é assim que o Mirelo
   "sabe" o que há na música, e é grátis até 10 por dia;
3. transcrição assíncrona: POST /v2/audio-to-midi/v1.0/jobs com a lista recomendada, e
   consulta ao job_url até 'succeeded', 'failed' ou 'expired';
4. o MIDI vem de um link temporário em result.midi.url — baixado na hora.

Cobra 2,5 créditos por segundo de áudio: uma música de 4 min são 600. A chave da API fica só
nesta máquina (~/.flyback-servidor.json, campo "mirelo", ou MIRELO_API_KEY), nunca no site.

Escrito pela documentação e testado só até a autenticação: sem uma chave válida não há como
exercitar o resto. Erro da API sobe com o código e a mensagem dela.
"""
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = 'https://api.mirelo.ai'
BASE = '/v2/audio-to-midi/v1.0'


class ErroMirelo(RuntimeError):
    pass


def _pedir(metodo, url, chave=None, corpo=None, cabecalhos=None, bruto=None, tipo=None):
    cab = dict(cabecalhos or {})
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode()
        cab['Content-Type'] = 'application/json'
    elif bruto is not None:
        dados = bruto
        cab['Content-Type'] = tipo
    if chave:
        cab['Authorization'] = f'Bearer {chave}'
    req = urllib.request.Request(url if url.startswith('http') else API + url, data=dados, method=metodo, headers=cab)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            corpo_r = r.read()
            return (json.loads(corpo_r) if corpo_r[:1] in (b'{', b'[') else corpo_r), r.headers
    except urllib.error.HTTPError as e:
        texto = e.read().decode('utf-8', 'replace')
        try:
            err = json.loads(texto).get('error', {})
            raise ErroMirelo(f"{e.code} {err.get('code', '')}: {err.get('message', texto)[:200]}")
        except ValueError:
            raise ErroMirelo(f'{e.code}: {texto[:200]}')


def _multipart(campos, arquivo, tipo):
    """Corpo multipart/form-data com os campos do asset e o arquivo por último, como 'file'."""
    limite = uuid.uuid4().hex
    partes = []
    for k, v in campos.items():
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="{arquivo.name}"\r\n'
                  f'Content-Type: {tipo}\r\n\r\n'.encode())
    partes.append(arquivo.read_bytes())
    partes.append(f'\r\n--{limite}--\r\n'.encode())
    return b''.join(partes), f'multipart/form-data; boundary={limite}'


def chave():
    if os.environ.get('MIRELO_API_KEY'):
        return os.environ['MIRELO_API_KEY']
    cfg = Path.home() / '.flyback-servidor.json'
    if cfg.is_file():
        return json.loads(cfg.read_text(encoding='utf-8')).get('mirelo') or None
    return None


def creditos_previstos(segundos, k=None):
    """Quanto a transcrição vai custar, sem cobrar nada (preflight)."""
    r, _ = _pedir('GET', f'{BASE}/preflight?duration_ms={int(segundos * 1000)}', k or chave())
    return r


def transcrever(audio, aviso=None, k=None):
    """(bytes do MIDI, instrumentos usados). `aviso(etapa, pct)` acompanha o andamento."""
    k = k or chave()
    if not k:
        raise ErroMirelo('sem chave da API do Mirelo: ponha em ~/.flyback-servidor.json, campo "mirelo"')
    avisa = aviso or (lambda *a: None)
    # o wav do YouTube passa de 50 MB; mp3 de 192 kbps são uns 6 MB e o Mirelo aceita
    with tempfile.TemporaryDirectory() as d:
        mp3 = Path(d) / (Path(audio).stem + '.mp3')
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(audio), '-b:a', '192k', str(mp3)], check=True)
        avisa('enviando ao Mirelo', 0)
        asset, _ = _pedir('POST', '/v3/assets', k, {'content_type': 'audio/mpeg'})
        if asset.get('max_bytes') and mp3.stat().st_size > asset['max_bytes']:
            raise ErroMirelo(f"o áudio passa do limite do Mirelo ({asset['max_bytes'] // 2**20} MB)")
        corpo, tipo = _multipart(asset.get('fields') or {}, mp3, 'audio/mpeg')
        _pedir('POST', asset['upload_url'], bruto=corpo, tipo=tipo)
    audio_ref = {'type': 'asset', 'asset_id': asset['id']}

    avisa('Mirelo detectando os instrumentos', 0)
    det, _ = _pedir('POST', f'{BASE}/instruments', k, {'audio': audio_ref, 'max_credits': 0})
    instrumentos = det.get('recommended_instruments') or []

    avisa('Mirelo transcrevendo', 0)
    pedido = {'audio': audio_ref, 'instruments': instrumentos}
    if det.get('instrument_detection_id'):
        pedido['instrument_detection_id'] = det['instrument_detection_id']
    job, _ = _pedir('POST', f'{BASE}/jobs', k, pedido)
    url, inicio = job['job_url'], time.time()
    while True:
        estado, cab = _pedir('GET', url, k)
        if estado.get('status') == 'succeeded':
            break
        if estado.get('status') in ('failed', 'expired'):
            raise ErroMirelo(f"o Mirelo terminou como {estado.get('status')}: {json.dumps(estado.get('error') or {})[:200]}")
        # sem porcentagem na API: o andamento é o tempo, contra ~1x a duração como referência
        avisa('Mirelo transcrevendo', min(95, int((time.time() - inicio) / 3)))
        time.sleep(max(2, min(30, int(cab.get('Retry-After') or 5))))
    midi_url = estado['result']['midi']['url']
    midi, _ = _pedir('GET', midi_url)
    return midi, instrumentos
