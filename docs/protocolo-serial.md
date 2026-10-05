# Protocolo serial para o ESP32

No modo **ESP32 · serial**, o `index.html` envia pela Web Serial API os segmentos
monofônicos de cada canal, os mesmos `ch[i].segs` que alimentam a síntese. São de 1 a 6
canais, um por flyback. O firmware só precisa enfileirar e executar no instante certo. O
firmware está em `firmware/flyback-esp32/` (ver **Firmware**, no fim).

No modo **Estéreo · P2** nada vai pela serial: os dois flybacks são acionados pelo áudio do
computador.

## Transporte

- Web Serial, 8N1, sem controle de fluxo. Velocidade escolhida na página:
  115200 (padrão), 230400, 460800 ou 921600.
- Texto ASCII, uma mensagem por linha, terminada em `\n`.
- Funciona em Chrome e Edge no computador. Safari e Firefox não têm Web Serial, e a página
  avisa quando não há suporte.

## Mensagens

| Linha | Significado |
|---|---|
| `P c g` | O canal `c` passa a acionar o GPIO `g`. `g = -1` libera o canal. |
| `R` | Zera o relógio: o instante em que a linha chega é t = 0. Esvazia as filas. |
| `N c t f` | No instante `t` ms, o canal `c` passa a tocar `f` Hz. |
| `F c t` | No instante `t` ms, o canal `c` silencia. |
| `X` | Silencia todos os canais agora e esvazia as filas. |

- `c` é o índice do canal, de `0` a `5` — o "Canal 1" da página é o `0`.
- `t` é inteiro, em milissegundos desde o último `R`.
- `f` tem duas casas decimais, por exemplo `440.00`. A oitava escolhida na página
  já vem aplicada.
- Duas notas seguidas no mesmo canal chegam como dois `N` sem `F` entre eles.
  O `F` só aparece quando há silêncio de verdade.

### Pinos

A página manda o mapa inteiro, os seis `P`, ao conectar, sempre que muda o pino de um
canal, a placa ou o número de flybacks, e antes de cada `R` de tocar ou testar — muitas
placas ESP32 reiniciam quando a porta serial é aberta, e o que chega durante o boot se perde. Canal acima do número de flybacks escolhido vai com
`-1`. O firmware deve silenciar o canal antes de trocar o pino dele, e ignorar `N` e `F` de
canal sem pino.

A página só oferece pinos de saída livres em módulo comum — sem os de boot (strapping), os
da memória flash e PSRAM, os da USB nativa e os da UART0:

| Placa | Pinos oferecidos | Padrão para os canais 1 a 6 |
|---|---|---|
| ESP32 | 4, 13, 14, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33 | 18, 19, 21, 22, 23, 25 |
| ESP32-S3 | 1, 2, 4–18, 21, 38–42, 47, 48 | 4, 5, 6, 7, 15, 16 |

O MCPWM chega a qualquer GPIO pela matriz, então qualquer pino da lista serve para qualquer
canal. Em módulo WROVER do ESP32 clássico, 16 e 17 são da PSRAM; em algumas placas S3, 38 ou
48 têm o LED RGB.

### Teste de canal

O botão "testar" de cada canal, com a página parada, envia:

```
R
N c 0 440.00
F c 600
```

Um lá de 0,6 s naquele canal, para achar qual flyback é qual ao montar a bancada.

## Tempo

- A página manda cada evento cerca de 100 ms antes do instante `t`. O firmware
  deve manter uma fila por canal, ordenada por `t`.
- Evento com `t` já passado executa na hora.
- Tocar, pular para outro ponto, silenciar um canal ou retomar depois de pausar gera `R` e
  recomeça a contagem. Pausar, parar, ou trocar para o modo estéreo gera `X`.
- Com a aba em segundo plano o navegador atrasa os temporizadores e os eventos
  podem chegar tarde. Deixe a página visível enquanto toca.

## Ver o que seria enviado

O painel "Linhas enviadas", na saída ESP32, mostra as últimas linhas — **também sem ESP
conectado**: com ele aberto, tocar a música gera o mesmo fluxo que iria para a porta. É o
jeito de conferir o protocolo enquanto o firmware não existe.

## Exemplo

Conectando com seis flybacks num ESP32-S3 e tocando o início do Korobeiniki do acervo, com o
preset "um instrumento por flyback":

```
X
P 0 4
P 1 5
P 2 6
P 3 7
P 4 15
P 5 16
R
N 0 60 659.26
N 1 60 82.41
N 2 60 207.65
N 1 260 164.81
```

## Recepção no firmware, em esboço

```c
// uma linha por vez, já sem o '\n'
switch (linha[0]) {
  case 'P': sscanf(linha + 2, "%d %d", &c, &g);         silencia(c); fixa_pino(c, g); break;
  case 'R': t0 = millis(); limpa_filas(); break;
  case 'X': silencia_todos(); limpa_filas(); break;
  case 'N': sscanf(linha + 2, "%d %lu %f", &c, &t, &f); enfileira(c, t0 + t, f); break;
  case 'F': sscanf(linha + 2, "%d %lu", &c, &t);        enfileira(c, t0 + t, 0); break;
}
```

A seção 3.16 de `hardware-decisoes.md` explica por que a geração da nota no ESP
deve habilitar o gerador do MCPWM, ou contar pulsos, em vez de alternar o GPIO.

## Firmware

`firmware/flyback-esp32/flyback-esp32.ino`, para a Arduino IDE ou o `arduino-cli`, placa "ESP32
Dev Module" (o ESP32 comum, o "S1" de `hardware-decisoes.md`). Só usa o que vem com o pacote
`esp32` da Espressif.

- **Nota pelo LEDC**, um timer por canal: cada canal tem a sua frequência. O ESP32 comum tem 8
  timers e cobre os 6 canais; o S3 tem 4, e lá só os canais 1 a 4 tocam. Onda quadrada de 50%,
  resolução de 13 bits — de 9,5 Hz a 9,7 kHz; com 10 bits nada abaixo de 76 Hz sairia.
- **Lógica invertida** é a constante `LOGICA_INVERTIDA`, no topo do sketch: `true` quando o GPIO
  em ALTO corta o arco (o NPN que aterra o pino 4 do 555). Fica no firmware, e não na página,
  porque o silêncio tem de estar certo também sem a página: no boot, com o navegador fechado, com
  a aba travada. Na nota, a polaridade não muda nada (50% é 50%); só o silêncio muda.
- **Pinos padrão** iguais aos da página (18, 19, 21, 22, 23, 25 no ESP32), parados no silêncio
  antes até de a serial abrir: se o mapa se perder no boot, o firmware já está no lugar.
- **Nota presa**: passou de 20 s sem nenhum evento novo no canal, silencia — é o caso de o
  navegador travar no meio de uma nota e o `F` nunca chegar.
- `?` pelo monitor serial responde a lógica, os pinos e os eventos perdidos.

**Cuidado com a lógica invertida.** Nesse circuito, a falta de sinal libera o arco: enquanto o ESP
reinicia (uns 300 ms), trava ou está desligado com a placa de potência ligada, o 555 oscila e o
flyback fica ligado direto. Ligue a potência só com o ESP já rodando, desligue antes de tirar o
USB, e prefira um resistor de pull-up (10 kΩ ao 3,3 V) no pino, que mantém o arco cortado durante
o boot. Na próxima revisão da placa, vale inverter: sem sinal, arco desligado.

Com o 555 reiniciado a cada liberação do pino 4, cada rajada começa do mesmo jeito; a distorção da
seção 3.16, de cortar uma portadora gerada pelo próprio ESP, não se aplica aqui.
