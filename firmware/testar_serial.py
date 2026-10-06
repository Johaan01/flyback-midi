"""Confere o firmware do ESP32 pela serial, sem o site.

    pip install pyserial
    python firmware/testar_serial.py COM5
    python firmware/testar_serial.py COM5 --canais 2 --baud 115200

Espera o "flyback-esp32 pronto" do boot (abrir a porta reinicia muitas placas), pergunta o
estado com "?", toca um lá de 1 s em cada canal e uma escala curta no canal 1, e termina com "X"
(silêncio). Com o osciloscópio no GPIO de cada canal: parado em ALTO no silêncio (lógica
invertida), onda quadrada de 50% na nota. Feche este script antes de conectar pelo site: só um
programa usa a porta por vez.
"""
import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit('falta o pyserial:  pip install pyserial')

ESCALA = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25]   # dó a dó


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('porta', help='COM5, /dev/ttyUSB0…')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--canais', type=int, default=2)
    a = ap.parse_args()

    s = serial.Serial(a.porta, a.baud, timeout=0.1)

    def le(seg):
        fim, out = time.time() + seg, b''
        while time.time() < fim:
            out += s.read(256)
        texto = out.decode('utf-8', 'replace').strip()
        if texto:
            print('  ← ' + texto.replace('\n', '\n  ← '))
        return texto

    def manda(linha):
        print('  → ' + linha)
        s.write((linha + '\n').encode())

    print('esperando o boot…')
    boot = le(2.5)
    if 'flyback-esp32 pronto' not in boot:
        print('  (não veio o "pronto": a placa pode não ter reiniciado ao abrir a porta; seguindo)')

    manda('?'); le(0.5)
    manda('X')
    for c in range(a.canais):
        print(f'canal {c + 1}: lá de 1 s')
        manda('R'); manda(f'N {c} 0 440.00'); manda(f'F {c} 1000')
        le(1.6)
    print('canal 1: escala de dó a dó, 300 ms por nota')
    manda('R')
    for i, f in enumerate(ESCALA):
        manda(f'N 0 {i * 300} {f:.2f}')
    manda(f'F 0 {len(ESCALA) * 300}')
    le(len(ESCALA) * 0.3 + 0.5)
    manda('X'); manda('?'); le(0.5)
    s.close()
    print('pronto. Se ouviu (ou viu no osciloscópio) cada canal e a escala, o firmware está bom.')


if __name__ == '__main__':
    main()
