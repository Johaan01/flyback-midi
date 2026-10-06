# Bancada: gravar e testar o firmware no ESP32

Roteiro para o computador que tem o ESP32 no USB — feito para ser seguido pelo Claude Code
dessa máquina (peça: "siga docs/bancada-esp32.md") ou à mão. O firmware foi escrito em outro
computador, sem placa e **sem compilar**: o passo 2 é a primeira compilação dele, e erro ali é
esperado e deve ser corrigido no próprio `firmware/flyback-esp32/flyback-esp32.ino`.

Ao terminar, anote o resultado em **Resultados**, no fim deste arquivo, e faça commit e push:
é assim que a sessão do outro computador fica sabendo o que aconteceu.

## O teste de agora

- **Placa:** ESP32 comum ("ESP32 Dev Module"; o "S1" de `hardware-decisoes.md`).
- **Flybacks:** 2, placas **V3.5** — NE555 com um NPN aterrando o pino 4 (reset). Lógica
  **invertida**: GPIO em ALTO corta o arco; BAIXO, solto ou ESP desligado, o arco fica livre.
  É o `LOGICA_INVERTIDA = true` do firmware, que já vem assim.
- **Pinos:** canal 1 no GPIO 18, canal 2 no GPIO 19 (os padrões do site e do firmware).
- **Firmware:** o v1, que só liga e desliga o arco na frequência da nota. O envelope
  (`docs/envelope-v5.md`) é para a placa V5, que ainda não existe; não faz parte deste teste.

Contexto para quem não conhece o projeto: `CLAUDE.md` (seção "Saída serial") e
`docs/protocolo-serial.md`, que descreve as mensagens e, no fim, o firmware.

## Segurança antes de tudo

Com a lógica invertida, **falta de sinal libera o arco**: durante o boot do ESP (~300 ms), com o
ESP travado ou desligado, o 555 oscila e o flyback fica ligado direto.

- Os passos 1 a 6 são **sem a placa de potência ligada** — o ESP sozinho, ou com o osciloscópio
  ou um LED (com resistor) nos GPIO 18 e 19.
- Ligue a potência só com o ESP já rodando; desligue a potência antes de tirar o USB.
- Recomendado: resistor de 10 kΩ de cada GPIO de nota ao 3,3 V, que segura o arco cortado
  durante o boot.

## 1. Ferramentas

Windows:

```
winget install ArduinoSA.CLI
arduino-cli config init
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32
pip install pyserial
```

(Depois do `winget`, abra um terminal novo para o `arduino-cli` entrar no PATH. O pacote do
ESP32 baixa algumas centenas de MB.)

Se o ESP não aparecer como porta COM no passo 3, falta o driver do conversor USB da placa:
CP210x (Silicon Labs) ou CH340 (WCH), conforme o chip ao lado do conector.

## 2. Compilar

```
arduino-cli compile --fqbn esp32:esp32:esp32 firmware/flyback-esp32
```

Se der erro, corrija no `.ino` e compile de novo. Pontos mais prováveis, porque dependem da versão
do pacote: os nomes do `driver/ledc.h` (`LEDC_AUTO_CLK`, `ledc_timer_config_t`,
`ledc_channel_config_t`), a macro `SOC_LEDC_SUPPORT_HS_MODE` e o `Serial.printf`. Anote em
Resultados a versão do pacote (`arduino-cli core list`) e o que precisou mudar.

## 3. Achar a porta

```
arduino-cli board list
```

## 4. Gravar

```
arduino-cli upload -p COM5 --fqbn esp32:esp32:esp32 firmware/flyback-esp32
```

Trocando `COM5` pela porta do passo 3. Se aparecer "Failed to connect", segure o botão BOOT da
placa enquanto o upload começa.

## 5. Testar pela serial, sem o site

```
python firmware/testar_serial.py COM5
```

Esperado:

- `← flyback-esp32 pronto · lógica invertida (ALTO corta o arco) · 6 canais`
- a resposta do `?` com os pinos `18 19 21 22 23 25`
- no osciloscópio (ou no LED): GPIO 18 e 19 **em ALTO parados**; onda quadrada de 440 Hz e 50%
  por 1 s em cada um, um de cada vez; depois a escala no 18; no fim, ALTO de novo.

O script fecha a porta ao terminar. Só um programa usa a porta por vez: feche monitor serial,
Arduino IDE ou o próprio script antes do passo 7.

## 6. Conferir à mão (opcional)

Num monitor serial a 115200 (`arduino-cli monitor -p COM5 -c baudrate=115200`), as linhas do
protocolo funcionam digitadas: `R`, `N 0 0 440.00`, `F 0 2000`, `X`, `?`.

## 7. Pelo site

1. Chrome ou Edge, em https://johaan01.github.io/flyback-midi/
2. Painel de saída: **Flybacks 2**, **Placa ESP32**, pinos 18 e 19, 115200, **Conectar ESP32**.
3. "testar" em cada canal: um lá de 0,6 s.
4. Abrir uma música e tocar. Com 2 flybacks a serial manda só os canais 1 e 2.

## 8. Com os flybacks

Só depois de 5 e 7 funcionarem. ESP rodando e conectado → ligar a potência → "testar" →
música → parar → desligar a potência → só então tirar o USB.

## Resultados

Preencher a cada sessão de bancada (data, o que funcionou, o que não, o que mudou no código).

- _(nada ainda)_
