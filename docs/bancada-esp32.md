# Bancada: gravar e testar o firmware no ESP32

Roteiro para o computador que tem o ESP32 no USB — feito para ser seguido pelo Claude Code
dessa máquina (peça: "siga docs/bancada-esp32.md") ou à mão. O firmware foi escrito em outro
computador, sem placa e **sem compilar**: o passo 2 é a primeira compilação dele, e erro ali é
esperado e deve ser corrigido no próprio `firmware/flyback-esp32/flyback-esp32.ino`.

Ao terminar, anote o resultado em **Resultados**, no fim deste arquivo, e faça commit e push:
é assim que a sessão do outro computador fica sabendo o que aconteceu.

**Mudou em 11/out:** o teste passou a ser na placa **V3.6** (lógica direta). O firmware veio com
`LOGICA_INVERTIDA = false` e ganhou a mensagem `D` (tom contínuo), e o gerador de tom (`tom.html`)
ganhou o modo "ESP32 pela serial". Se este repositório foi clonado antes, rode `git pull` antes
do passo 2.

## O teste de agora

- **Placa:** ESP32 comum ("ESP32 Dev Module"; o "S1" de `hardware-decisoes.md`).
- **Flybacks:** 2, placas de controle **V3.6** — a NOTA entra pelo optoacoplador 6N136 e
  passa pelo Q1 até o RESET do 555 monoestável (U13). As duas inversões se anulam: lógica
  **direta**, GPIO em ALTO libera o arco; BAIXO, solto, em boot ou ESP desligado, o arco fica
  cortado. É o `LOGICA_INVERTIDA = false` do firmware, que já vem assim.
- **Áudio não serve:** a entrada da V3.6 é lógica, e o P2 do computador não a aciona. Tudo passa
  pelo ESP: o player e o gerador de tom.
- **Pinos:** canal 1 no GPIO 18, canal 2 no GPIO 19 (os padrões do site e do firmware).
- **Firmware:** o v1, que liga e desliga o arco na frequência da nota, mais o `D` do gerador de
  tom: tom contínuo com a fração aberta de cada período (500 ‰ = onda quadrada, o volume
  máximo), que apaga sozinho 2 s depois do último `D`. O envelope (`docs/envelope-v5.md`) é para
  a placa V5, que ainda não existe; não faz parte deste teste.

Contexto para quem não conhece o projeto: `CLAUDE.md` (seção "Saída serial") e
`docs/protocolo-serial.md`, que descreve as mensagens e, no fim, o firmware.

## Segurança antes de tudo

Na V3.6 **falta de sinal corta o arco**: com o ESP em boot, travado, desligado ou com o cabo
solto, o LED do 6N136 fica apagado e o 555 parado. O que liga o arco é o GPIO em ALTO.

- Os passos 1 a 6 são **sem a placa de potência ligada** — o ESP sozinho, ou com o osciloscópio
  ou um LED (com resistor) nos GPIO 18 e 19.
- Mesmo assim: ligue a potência com o ESP já rodando e desligue antes de tirar o USB. Um firmware
  com `LOGICA_INVERTIDA = true` gravado por engano deixaria os GPIO em ALTO parados, com o arco
  ligado direto — confira a linha "lógica direta" no passo 5 antes de ligar a potência.
- Não é preciso pull-up nos GPIO de nota (era para a V3.5). O R5 da placa fica.

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

- `← flyback-esp32 pronto · lógica direta (ALTO libera o arco) · 6 canais`
- a resposta do `?` com `lógica direta` e os pinos `18 19 21 22 23 25`
- no osciloscópio (ou no LED): GPIO 18 e 19 **em BAIXO parados**; onda quadrada de 440 Hz e 50%
  por 1 s em cada um, um de cada vez; depois a escala no 18; depois 220 Hz no 18 por uns 3 s
  (o `D` renovado) e, sem renovar, **BAIXO de novo em até 2 s** — é o desligamento automático do
  tom contínuo; no fim, BAIXO.

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
5. Desconectar no player (só uma página usa a porta por vez) e abrir o **gerador de tom**
   (https://johaan01.github.io/flyback-midi/tom.html). Em "Saída", **ESP32 pela serial** →
   **Conectar ESP32**. Ele usa os pinos do painel do player.
6. Pelo ESP o gerador tem um canal só. Saída 1, ▶: tom contínuo no GPIO 18, na frequência do
   slider; o osciloscópio à direita desenha o pulso que sai no pino. O volume vira a fração
   aberta ("aberto 50%" no volume máximo; menos volume, pulso mais estreito). Escolher a saída 2
   move o tom para o GPIO 19 e apaga o 18. Fechar a aba com o tom tocando: o ESP apaga em 2 s.

## 8. Com os flybacks

Só depois de 5 e 7 funcionarem. ESP rodando e conectado → ligar a potência → "testar" →
música → parar → desligar a potência → só então tirar o USB.

Com a potência ligada, o gerador de tom pelo ESP é o jeito de achar o vale de cada flyback e
medir: frequência fixa num canal por vez, varredura, e o volume (a fração aberta) para ver quanto
o arco perde abaixo de 50%. Anote em Resultados o que ouvir e medir em cada canal.

## Se a serial cair com o arco ligado

Em 16/out a porta caiu poucos segundos depois de o gerador de tom começar, com o arco aberto sem parar;
tocando música, não. Para saber se o ESP **reiniciou** ou se só o **USB** caiu:

1. Depois da queda, abra o monitor serial e digite `?`. A resposta traz `ligado há N s` e `último
   reinício: ...`.
   - `ligado há` grande (não zerou): o ESP nem reiniciou — caiu só a ligação USB. É interferência no
     cabo: afaste o cabo USB do flyback, use cabo curto com ferrite, e o notebook na bateria.
   - `QUEDA DE TENSÃO (brownout)`: a alimentação do ESP afundou com o arco. Fonte do ESP separada da
     do flyback, capacitor junto do ESP, terra em estrela.
   - `TRAVAMENTO (...)`: erro no firmware — anote em Resultados o que estava tocando.
   - `energia ligada` ou `pino de reset`: o ESP desligou de verdade (alimentação ou reset por ruído).
2. Repita com a **potência do flyback desligada** (só o ESP, osciloscópio no pino): se a porta não cai
   assim, o problema é do circuito de potência, não do site nem do firmware.

## Resultados

Preencher a cada sessão de bancada (data, o que funcionou, o que não, o que mudou no código).

- _(nada ainda)_
