# Envelope no arco: protocolo serial v2 e firmware para a placa V5

Especificação para implementar no site (`index.html`) e no firmware (`firmware/flyback-esp32/`).
Lugar sugerido no repositório: `docs/envelope-v5.md`. Foi escrita a partir do `index.html`, do
`docs/protocolo-serial.md` e do `flyback-esp32.ino` da `main` de hoje: os nomes de função citados
(`serialStart`, `serialPinos`, `scheduleVoice`, `envOf`, `velOf`, `ENVELOPES`, `ATAQUE`) são os de lá.

---

## 0. Resumo

A placa de potência V5 (UC3843 + shunt + IRFP264N) tem **duas entradas de controle por flyback**,
as duas isoladas por 6N136:

- **NOTA**: liga e desliga o arco na frequência da nota. É o que o GPIO já faz hoje.
- **ENV**: um PWM rápido (10 kHz). A placa filtra esse PWM e usa a média como **limite de
  corrente** do UC3843. Com mais duty, cada pulso leva mais corrente e o arco fica mais forte.

O site **continua mandando uma linha serial só**, com eventos que levam carimbo de tempo, como
hoje. Mudam três coisas:

1. cada nota passa a levar a sua **força** (a velocity, já com a curva que o áudio usa);
2. cada canal recebe uma vez a **receita do envelope**: ataque, decaimento, sustentação e soltura;
3. cada canal recebe uma vez a **calibração do seu flyback**: o duty de ENV que dá o arco mínimo e
   o que dá o máximo.

**O ESP desenha a curva do envelope**, recalculando a cada 1 ms, e é ele que gera os dois sinais
elétricos de cada canal. Tudo é compatível com o firmware v1: a página só manda as mensagens novas
depois que o firmware se anuncia v2.

---

## 1. A ideia: uma linha serial, dois fios por canal

```
 site ──── USB serial: um fluxo de texto ────► ESP32 ──► canal 1: NOTA ─┐
   "E 0 4 450 350 6"   receita do canal 1                 canal 1: ENV  ─┴─► placa V5, flyback 1
   "N 0 1500 440.00 873"  nota com força                    …
   "F 0 2100"             soltura                         canal 6: NOTA ─┐
                                                          canal 6: ENV  ─┴─► placa V5, flyback 6
```

| | O que é | Quem produz | Com que frequência |
|---|---|---|---|
| evento de nota | "no instante t, o canal c toca f Hz com força a" ou "solta" | site | uma vez por nota |
| receita do envelope | ataque, τ, sustentação e soltura do canal | site | ao conectar e quando mudar |
| calibração | duty do mínimo e do máximo daquele flyback | site (guarda no navegador) | ao conectar e quando mudar |
| **NOTA** (fio) | onda quadrada na frequência da nota | ESP, timer de hardware | contínuo |
| **ENV** (fio) | PWM de 10 kHz, com o nível do envelope naquele milissegundo como duty | ESP, LEDC, recalculado a cada 1 ms | contínuo |

**Por que a curva não vai pela serial ponto a ponto.** Seis canais a 1 kHz com linhas de uns 14
bytes dão 84 kB/s. A 115200 baud cabem 11,5 kB/s, sete vezes menos. Mesmo a 100 Hz (degraus de
10 ms, que se ouvem no ataque) seriam 73% do enlace, e a página despacha de 20 em 20 ms
(`setInterval(pump, 20)`), com o jitter do navegador por cima. Mandando a receita, a curva sai
exata no ESP e a serial continua leve: o pior caso da seção 3.6 é de uns 3 kB/s.

---

## 2. Contrato com a placa V5

Esta seção descreve o que o firmware pode supor sobre o hardware. Quem gera a portadora de
chaveamento (22 a 54 kHz) é o **UC3843 da placa**, com a frequência no trimpot PR_T. O ESP nunca
gera essa portadora: ele só abre e fecha o arco (NOTA) e ajusta o teto de corrente (ENV).

### 2.1 Sinais

| Entrada da placa | Nível no GPIO | Efeito |
|---|---|---|
| NOTA | ALTO | Q2 cortado, COMP livre: arco **liberado** |
| NOTA | BAIXO, solto, ESP desligado ou em boot | Q2 aterra o COMP: arco **cortado** |
| ENV | duty 0% (BAIXO fixo), solto, ESP desligado | limite de corrente zero: arco não acende **nem com NOTA em ALTO** |
| ENV | duty ≈ 20% | limiar: o limite de corrente começa a subir de 0 A |
| ENV | duty subindo | cerca de +2,5 A de pico a cada +10% de duty |
| ENV | duty ≈ 100% | teto do pino CS, ≈ 20 A (18 a 22 A conforme o lote do CI), ou o teto do PR_I via D_CL, o que for menor |

O arco só acende com as **duas** entradas liberando. Isso dá duas travas independentes, e as duas
ficam do lado seguro sozinhas: um GPIO solto deixa o LED do 6N136 apagado, e LED apagado quer
dizer arco cortado nas duas entradas.

Na placa, o jumper JP1 escolhe de onde vem o limite de corrente:

- **JP1 em ENV** (normal): quem manda é o ENV, e o PR_I vira **teto** através de D_CL.
- **JP1 em TRIM**: o PR_I fixa a corrente e o ENV é ignorado. A NOTA continua valendo, e a placa
  vira um OOK puro, como a V3.5. É a posição para ajustar o teto com a ponta no shunt.

### 2.2 Relação duty → corrente (números de projeto, só para entender a forma)

Com R_SH = 0,05 Ω, pull-ups de 22 kΩ, divisor 47 k/47 k e R_IN = R_F = 100 kΩ:

$$
V_{ENV} \approx 4{,}35 - 3{,}79\,d
$$

$$
I_{pico} = \frac{V_{COMP} - 1{,}4}{3\,R_{SH}} = \frac{3{,}6 - V_{ENV}}{0{,}15} \approx 25\,(d - 0{,}20)\ \text{A}
$$

Aqui d é o duty do ENV, de 0 a 1. A relação é **linear** entre o limiar (d ≈ 0,20) e o teto. O
firmware **não usa nenhum destes números**: usa `dmin` e `dmax`, medidos em cada flyback (seção 7).
Atraso do 6N136, tolerância do CI e lote do resistor deslocam tudo alguns por cento.

### 2.3 Tempos que importam para o firmware

| O quê | Quanto | Consequência |
|---|---|---|
| filtro do ENV (C_E 100 nF, ~20 kΩ vistos, com a carga de R_IN) | τ ≈ 2 ms | o nível real segue o duty com uns 5 ms de 10 a 90%: o ataque de 4 ms fica arredondado para ~5 ms, sem diferença audível |
| COMP depois que a NOTA sobe | 25 a 40 µs | é o "tempo morto" de cada meia-onda ligada |
| bordas do 6N136 com pull-up de 22 kΩ | 1 a 2 µs | deslocam o duty do ENV em 1 a 2% a 10 kHz, e a calibração absorve isso |
| ondulação de 10 kHz no COMP | ~1,5 mV | ~10 mA de corrente, desprezível |

**Faixa útil da NOTA.** Cada meia-onda ligada precisa conter o tempo morto do COMP e mais alguns
pulsos do UC3843:

$$
n_{pulsos} \approx \left(\frac{\ell}{f_{nota}} - 35\,\mu s\right) f_{sw}
$$

Aqui ℓ é a largura da meia-onda ligada (0,5 na onda quadrada). Com f_sw = 30 kHz: a 440 Hz
cabem ~33 pulsos, a 2 kHz uns 6, e a 4 kHz menos de 3. **Acima de ~3 kHz o arco enfraquece e
falha.** O "agudo máx" de cada instrumento resolve isso, então o firmware não precisa limitar.

### 2.4 O que o firmware TEM de garantir

1. No `setup()`, **antes da `Serial`**, colocar a NOTA de todos os canais no silêncio e o ENV em
   BAIXO fixo.
2. ENV em **0% fixo** (pino em BAIXO, não um PWM com duty pequeno) no boot, no `X`, no watchdog,
   no sinal de vida expirado, no fim do `D` e quando o canal é liberado.
3. Quem liga e desliga o arco é **sempre a NOTA**. O ENV muda de valor com a NOTA já ligada, ou
   fica estacionado. Nunca usar o ENV para cortar uma nota: o filtro levaria milissegundos.
4. Entre as notas de uma música (depois de `R`), deixar o ENV **estacionado em `dmin`**. Com a NOTA
   em BAIXO não passa corrente nenhuma (Q2 segura o COMP). Ainda assim o filtro já fica no
   limiar, e a nota seguinte começa sem tempo morto. Sem estacionar, uma nota fraca gastaria 2 a
   3 ms só para o filtro sair do zero e chegar ao limiar, e o ataque ficaria mole.

### 2.5 Placas V3.5 no meio

A V3.5 (NE555 com NPN no pino 4) tem a NOTA **invertida**: com GPIO em ALTO o arco é cortado. Ela
também não tem ENV. Enquanto houver placas das duas versões, a polaridade fica **por canal no
firmware** (`INVERTIDO[6]`, seção 4.7), e não na página. O motivo é o mesmo de hoje: o silêncio tem
de estar certo no boot e com o navegador fechado. Num canal V3.5 o pino de ENV fica sem nada
ligado, e o PWM ali é inofensivo.

**Com a V5, o P2 do computador não aciona a placa**, porque as entradas são lógicas e isoladas. Nesse
caso o ESP é necessário para qualquer número de flybacks, inclusive 1 ou 2. A página já manda a
serial sempre que há ESP conectado, então nada muda no roteamento.

---

## 3. Protocolo v2

### 3.1 Regras de compatibilidade

- Tudo do v1 continua igual: `P`, `R`, `N`, `F`, `X`, `?`, 8N1, linhas ASCII terminadas em `\n`,
  eventos ~100 ms adiantados.
- O único campo novo numa mensagem existente é a força `a`, no **fim** do `N`. O firmware v1 lê
  com `sscanf("%d %ld %f")` e para no terceiro campo, então ignoraria a força. Mesmo assim a página
  só manda a força para firmware v2, para o registro de uma placa v1 continuar idêntico ao de hoje.
- As mensagens novas (`L`, `K`, `E`, `D`, `.`) só saem **depois que o firmware se anunciar v2**
  com `V`. Sem anúncio, a página fala v1.
- Com o registro aberto e sem ESP conectado, a página mostra o fluxo **v2**, porque o registro serve
  para escrever o firmware.

### 3.2 Mensagens

`→` vai da página para o ESP, e `←` volta do ESP para a página.

| Linha | Sentido | Versão | Significado |
|---|---|---|---|
| `V` | → | 2 | pergunta a versão |
| `V p placa n recursos…` | ← | 2 | resposta, e também anúncio espontâneo no fim do `setup()`. Exemplo: `V 2 esp32s3 6 env` |
| `P c g` | → | 1 | a NOTA do canal c sai no GPIO g (−1 libera) |
| `L c g` | → | 2 | o ENV do canal c sai no GPIO g (−1 libera) |
| `K c dmin dmax gama larg` | → | 2 | calibração do flyback c |
| `E c atk tau sus rel` | → | 2 | receita do envelope do canal c |
| `R` | → | 1 | t = 0 e filas vazias. **No v2, também solta as notas soando e estaciona o ENV em `dmin`** |
| `N c t f [a]` | → | 1 (2: `a`) | aos t ms, o canal c toca f Hz com força a (0 a 1000; sem `a`, vale 1000) |
| `F c t` | → | 1 | aos t ms, o canal c começa a soltura e depois silencia |
| `X` | → | 1 | silêncio já, em todos os canais, e filas vazias. **No v2, também ENV a 0%** |
| `D c d f` | → | 2 | calibração: toca f Hz com o ENV fixo em d ‰ por 2 s; repetir para manter |
| `.` | → | 2 | sinal de vida enquanto toca |
| `?` | → | 1 | estado legível, para o monitor serial |
| qualquer outra | ← | — | texto do firmware (avisos, erros); a página mostra no registro |

Formatos: c vai de 0 a 5. t é inteiro em ms desde o `R`. f leva 2 decimais, com a oitava já
aplicada, como hoje. Os demais campos são inteiros. "‰" quer dizer milésimos: 1000 = 100%.

### 3.3 `V`: versão e recursos

O firmware responde a cada `V` e também **se anuncia sozinho no fim do `setup()`**:

```
V 2 esp32s3 6 env
```

Os campos são: protocolo (2), placa (`esp32` ou `esp32s3`), quantos canais a placa toca (6 nas
duas, a partir do v2) e recursos (`env`). A página trata como v2 se `p ≥ 2` e houver `env`.
Se a placa anunciada for diferente da escolhida na página, a página avisa ("o firmware diz
ESP32-S3; a página está em ESP32"), porque as listas de pinos são outras.

Um `V` que chega **sem a página ter perguntado** quer dizer que o ESP reiniciou (queda de tensão,
botão de reset). A página manda a configuração inteira de novo e, se estiver tocando, recomeça da
posição atual com `serialStart(position())`.

### 3.4 `K`: calibração do flyback

```
K c dmin dmax gama larg
```

| Campo | Unidade | Padrão no firmware | Significado |
|---|---|---|---|
| `dmin` | ‰ de duty do ENV | 300 | arco no mínimo estável: é o "nível 0" do envelope |
| `dmax` | ‰ de duty do ENV | 600 | arco no máximo seguro: é o "nível 1" do envelope |
| `gama` | milésimos | 500 | expoente da curva nível → duty (500 = raiz quadrada; seção 4.4) |
| `larg` | ‰ do período da nota | 500 | largura da meia-onda ligada da NOTA. 500 é a onda quadrada de hoje |

Os padrões são **conservadores de propósito**. Pela seção 2.2 dão uns 2,5 A no mínimo e uns
10 A no máximo, e valem até alguém calibrar. O firmware recusa (e escreve uma linha de aviso) se
não valer `0 ≤ dmin < dmax ≤ 1000`, `100 ≤ gama ≤ 2000` e `50 ≤ larg ≤ 900`.

Com `larg` abaixo de 500 o flyback esquenta menos e o timbre fica um pouco mais fino. Foi o que
resolveu o aquecimento na V3.5 (duty de ~70% esquentava, ~30% não). Fica por flyback porque cada
núcleo aguenta uma coisa.

### 3.5 `E`: receita do envelope

```
E c atk tau sus rel
```

| Campo | Unidade | Limites | Significado |
|---|---|---|---|
| `atk` | ms | 0 a 1000 | rampa linear de 0 até o pico. Na página: `ATAQUE` = 4 |
| `tau` | ms | 0 a 60000 | constante do decaimento até o patamar. 0 = sem decaimento |
| `sus` | ‰ do pico | 0 a 1000 | patamar |
| `rel` | ms | 0 a 2000 | rampa linear até 0 depois do `F`. Na página: 6 (a rampa final do áudio, `b - .006`) |

Tradução direta de `ENVELOPES` do `index.html`:

| Envelope na página | Linha |
|---|---|
| `nenhum` (OOK) | `E c 4 0 1000 6` |
| `percussivo` | `E c 4 120 100 6` |
| `medio` | `E c 4 450 350 6` |
| `sustentado` | `E c 4 1200 700 6` |
| `corda` | `E c 4 900 0 6` |

A página gera a linha a partir do objeto, sem copiar a tabela:
`tau = env ? env.tau*1000 : 0`, `sus = env ? env.sus*1000 : 1000`. Envelope novo em `ENVELOPES`
passa a valer no arco sem mexer no firmware.

### 3.6 `N` com força

```
N c t f a
```

`a = Math.round(1000 * p)`, e p sai da **mesma função** que o áudio usa em `scheduleVoice`:

$$
p = 0{,}25 + 0{,}75\left(\frac{\min(v,\,127)}{127}\right)^{1{,}4}
$$

Aqui v é a velocity do segmento (`s.v`, 96 quando falta). Com "Dinâmica" desligada no canal, p = 1.
O **ganho do mixer não entra**: ele é o volume do monitor (e do flyback, no P2 da V3.5). No V5, o
máximo de cada arco é o `dmax` da calibração (ver 9.1).

**Banda.** Uma linha `N` com t de 6 dígitos e força tem ~22 bytes, e uma `F` ~12. Num caso denso
(6 canais × 15 notas/s) dá ~3 kB/s, mais o `.`: uns 27% dos 115200 baud.

### 3.7 `D`: duty direto, para calibrar

```
D c d f
```

O ESP esvazia a fila do canal, toca f Hz na NOTA (com `larg`) e põe o ENV **fixo em d ‰**, sem
envelope e sem `dmin`/`dmax`. Isso dura **2 s**, e cada `D` novo renova o prazo. Se a página parar
de repetir (aba travada, cabo solto), o arco apaga sozinho. `R`, `X`, `N` ou `F` no canal cancelam
o `D`. A página repete o `D` a cada 500 ms enquanto o modo de calibração estiver ligado (seção 5.6).

### 3.8 `.`: sinal de vida

Enquanto toca, a página manda `.` a cada 500 ms (só no v2). O firmware **arma** essa proteção no
primeiro `.` depois de um `R` e a desarma no `X`. Armada, se passarem **1500 ms sem nenhum byte**,
o firmware executa um `X`.

Isso cobre a aba travada e o cabo de dados solto com o ESP ainda alimentado pela placa, casos em
que hoje a nota fica presa até o watchdog de 20 s. Quem testa à mão pelo monitor serial não manda
`.`, e nada muda para essa pessoa.

### 3.9 Ordem de envio

```
X                       ao conectar
V                       repetido até a resposta (seção 5.1)
P c g    × 6            (v1 e v2)
L c g    × 6            v2
K …      × 6            v2
E …      × 6            v2
R                       antes de tocar ou testar: P, L, K e E vão de novo antes de cada R
N … / F …               100 ms adiantados, como hoje
.                       a cada 500 ms, v2
X                       pausa, fim, desconexão
```

Mandar `P`, `L`, `K` ou `E` no meio da música é inofensivo. `P` e `L` com o mesmo pino não fazem
nada. `E` vale a partir da próxima nota. `K` vale no próximo milissegundo.

### 3.10 Exemplo completo (ESP32-S3, dois flybacks em uso)

```
→ X
→ V
← V 2 esp32s3 6 env
→ P 0 4
→ P 1 5
→ P 2 -1            (…até o 5)
→ L 0 11
→ L 1 12
→ L 2 -1            (…até o 5)
→ K 0 230 810 500 500
→ K 1 260 760 500 400
→ E 0 4 450 350 6       voz: médio
→ E 1 4 900 0 6         baixo: corda
→ R
→ N 0 0 329.63 873
→ N 1 0 82.41 1000
→ .
→ F 0 480
→ N 0 500 392.00 640
→ .
→ F 1 1000
…
→ X
```

---

## 4. Firmware

### 4.1 Periféricos

| | ESP32 comum | ESP32-S3 |
|---|---|---|
| NOTA (6 canais, cada um com a sua frequência) | LEDC, um timer por canal, **como hoje** (4 timers HS + 2 LS) | **MCPWM**: 2 grupos × 3 timers, resolução de 1 MHz |
| ENV (6 canais, todos a 10 kHz) | LEDC LS, 1 timer (o LS 2), canais LS 0–3, 6 e 7 (o 4 e o 5 são das notas) | LEDC, 1 timer, canais 0–5 |
| resolução do ENV | 12 bits (80 MHz / 10 kHz = 8000 ≥ 4096) | 12 bits |
| pinos de ENV padrão | 26, 27, 32, 33, 16, 17 | 11, 12, 13, 14, 17, 18 |
| núcleo Arduino | 2.x ou 3.x | **3.x** (IDF ≥ 5.1, API `driver/mcpwm_prelude.h`) |

**Por que o S3 precisa do MCPWM.** O LEDC do S3 tem 4 timers, e cada nota precisa de uma frequência
própria: por isso hoje ele só toca os canais 1 a 4. O MCPWM tem 6 timers. Com resolução de 1 MHz e
período de 16 bits, a frequência mínima é 15,3 Hz, e o erro de afinação fica em

$$
\Delta_{cents} \le 1200\,\log_2\!\left(1 + \frac{f}{2\cdot 10^{6}}\right)
$$

Isso dá menos de 2 cents até 2,3 kHz e menos de 4 cents até 4,6 kHz, abaixo do que se ouve, e o
arco já enfraquece acima de ~3 kHz (2.3). Abaixo de 15,3 Hz a nota é recusada, com aviso, como o
`hz < 10` de hoje.

Esquema do MCPWM por canal: 1 timer (contagem crescente, `update_period_on_empty`), 1 operador,
1 comparador em `período × larg / 1000` (`update_cmp_on_tez`) e 1 gerador (ALTO no TEZ, BAIXO no
comparador). No silêncio, `mcpwm_generator_set_force_level(gen, nível_de_silêncio, true)`, e para
tocar, `-1`. A frequência muda com `mcpwm_timer_set_period()`.

**Pinos de ENV padrão.** Saem das listas de `PLACAS` do `index.html` e não colidem com os padrões
de NOTA. No S3 ficam livres os GPIO 1, 2, 8, 9 e 10, que são ADC1, para leituras futuras
(temperatura, retorno). No ESP32 comum, os 34 a 39 (só entrada, ADC1) continuam livres.

### 4.2 Estado por canal

```c
enum Fase : uint8_t { TRAVADO, PARADO, ATAQUE, CORPO, SOLTURA, DIRETO };

struct Receita { uint16_t atk = 4, tau = 0, sus = 1000, rel = 6; };            // ms, ms, ‰, ms
struct Calib   { uint16_t dmin = 300, dmax = 600, gama = 500, larg = 500; };    // ‰

struct Evento { uint32_t quando; float f; uint16_t a; };   // f = 0: soltura

struct Canal {
  int pinoNota = -1, pinoEnv = -1;
  Fase fase = TRAVADO;
  float x = 0;          // nível do envelope, 0..1
  float pico = 1;       // a/1000 da nota atual
  float alvo = 1;       // pico * sus
  float kDec = 0;       // exp(-1/tau), calculado no E
  float passo = 0;      // por ms, no ataque e na soltura
  uint32_t ultimoEvento = 0, diretoAte = 0;
  Receita env; Calib cal;
  Evento fila[96]; int n = 0;
};
```

### 4.3 A máquina do envelope

| Acontecimento | De | Para | O que faz |
|---|---|---|---|
| boot, `X`, watchdog, sinal de vida expirado, prazo do `D` vencido | qualquer | TRAVADO | NOTA em silêncio, ENV a 0% |
| `R` | qualquer | PARADO | NOTA em silêncio, ENV em `dmin`, fila vazia |
| `N` (chegou a hora) | qualquer (em DIRETO, cancela o `D`) | ATAQUE | `pico = a/1000`, `x = 0`, NOTA em f; se o canal vinha do silêncio, zera a fase (4.7) |
| `F` (chegou a hora) | ATAQUE ou CORPO | SOLTURA | `passo = x / rel` |
| `F` (chegou a hora) | DIRETO | PARADO | cancela o `D`: NOTA em silêncio, ENV em `dmin` |
| `x ≤ 0` | SOLTURA | PARADO | NOTA em silêncio, ENV em `dmin` |
| `D` | qualquer | DIRETO | fila vazia, NOTA em f, ENV fixo em d |

`N` sobre uma nota que ainda soa (legato, sem `F` entre as duas) **recomeça o ataque do zero**,
como o áudio, que faz `setValueAtTime(0, a)` em cada segmento. Um `N` depois de um `X`, sem `R`,
também toca, como no v1 (é o teste à mão pelo monitor). Ao terminar, o canal fica em PARADO.

A cada 1 ms (Δt = 1 ms), para cada canal:

**Ataque**, rampa linear até o pico:

$$
x \leftarrow \min\!\left(p,\; x + \frac{p}{t_{atk}}\right)
$$

Quando `x = p`, a fase passa a CORPO. Com `atk = 0`, a nota começa direto em p.

**Corpo**, decaimento exponencial até o patamar:

$$
x \leftarrow x_\infty + (x - x_\infty)\,k, \qquad x_\infty = p\,s, \qquad k = e^{-1/\tau}
$$

Em tempo contínuo isso é exatamente o `setTargetAtTime` do áudio:

$$
x(t) = p\left[\,s + (1-s)\,e^{-(t - t_{atk})/\tau}\,\right]
$$

Com `tau = 0`, o x fica parado em p (OOK com dinâmica).

**Soltura**, rampa linear do valor que tinha no `F` até zero:

$$
x \leftarrow x - \frac{x_F}{t_{rel}}
$$

Quando chega a zero, a NOTA é cortada e o canal vai para PARADO. Com `rel = 0`, corta na hora.

### 4.4 Nível → duty

$$
d = d_{min} + (d_{max} - d_{min})\; x^{\gamma}, \qquad \gamma = \frac{\texttt{gama}}{1000}
$$

O duty sai em ‰ e é convertido para 12 bits por `d * 4096 / 1000`. Fora das notas, PARADO usa
`dmin` e TRAVADO usa 0.

**Por que γ = 0,5 é o padrão.** Cada pulso do UC3843 entrega ao arco

$$
E_{pulso} = \tfrac12\,L_p\,I_{pk}^2
$$

Durante a meia-onda ligada da NOTA, a potência é $P = \tfrac12 L_p I_{pk}^2 f_{sw}$. O som é a
modulação dessa potência na frequência da nota, então a amplitude acompanha $I_{pk}^2$. Como a
corrente é linear no duty (2.2), para a amplitude seguir x como no áudio, a corrente tem de seguir
$\sqrt{x}$. O `dmin` não é zero, e por isso a relação não é exata, mas fica monotônica e próxima. O
`gama` fica ajustável de ouvido: 1000 deixa linear na corrente, e menos de 500 dá mais corpo às
notas fracas.

### 4.5 Proteções

| Proteção | Condição | Ação |
|---|---|---|
| boot | `setup()`, antes da Serial | NOTA no silêncio em todos os canais, ENV em BAIXO fixo |
| nota presa (já existe) | ATAQUE ou CORPO, fila vazia, nenhum evento no canal há 20 s | TRAVADO, agora **também com ENV a 0%** |
| sinal de vida (3.8) | armado e 1500 ms sem nenhum byte | `X` |
| prazo do `D` (3.7) | DIRETO e `millis() > diretoAte` | TRAVADO |
| pino repetido | `P` ou `L` num GPIO que já é de outra função | fica o último, como no `P` de hoje, e uma linha de aviso. Vale entre NOTA e ENV também |
| canal liberado | `P c -1` ou `L c -1` | o pino vai para o nível de silêncio em `pinoSeguro()` |

### 4.6 `?`

Acrescentar ao que já mostra: a versão, a polaridade de cada canal, os pinos de ENV, o `K` e o `E`
de cada canal, a fase atual e se o sinal de vida está armado. Exemplo:

```
v2 · esp32s3 · 6 canais · vida armada · eventos perdidos 0
c1 nota 4 env 11 direta  K 230 810 500 500  E 4 450 350 6  CORPO x=0.41
c2 nota 5 env 12 direta  K 260 760 500 400  E 4 900 0 6    PARADO
…
```

### 4.7 Detalhes

- **Polaridade por canal.** `LOGICA_INVERTIDA` vira `const bool INVERTIDO[6]`, com `false` para a
  V5 e `true` para a V3.5 (NPN no pino 4 do 555). A constante antiga pode continuar como valor que
  preenche o vetor. O ENV não tem polaridade: é sempre "mais duty, mais corrente".
- **Força de saída.** Cada 6N136 pede ~10 mA do GPIO (180 Ω em série com o LED, a 3,3 V). Depois
  de configurar o pino: `gpio_set_drive_capability(g, GPIO_DRIVE_CAP_3)`, para o nível alto não
  cair abaixo de ~3 V. Com 12 LEDs são ~120 mA a mais no 3,3 V da placa do ESP. O regulador de uma
  placa de desenvolvimento aguenta, mas um hub USB fraco pode não aguentar.
- **Fase no começo da nota.** Quando a nota sai do silêncio, ela começa na meia-onda **ligada**. No
  LEDC isso é `ledc_timer_rst()`, com `hpoint = 0`. No MCPWM é um sync por software
  (`mcpwm_new_soft_sync_src`, `mcpwm_timer_set_phase_on_sync` com contagem 0,
  `mcpwm_soft_sync_activate`). Sem isso, uma nota de 55 Hz pode começar com até 9 ms de atraso.
  Em legato basta trocar o período, que vale no próximo TEZ.
- **Afinação no ESP32 comum (melhoria opcional).** `ledc_set_freq()` arredonda para Hz inteiro, e
  o E1 (41,20 Hz) sai em 41 Hz, −8 cents. O divisor do LEDC tem 8 bits fracionários: calculando o
  divisor direto, o erro some.
- **Onde roda o envelope.** No `loop()`, com `micros()`: `if (agora - ultimoTick >= 1000)`, e com
  recuperação se o loop atrasar (avança o tick em vez de pular). O loop do sketch dá dezenas de
  milhares de voltas por segundo. Um `esp_timer` também serve, mas aí a fila e o estado passam a ser
  divididos entre tarefas e precisam de seção crítica. O `loop()` é mais simples.
- **Linha.** O buffer de 64 caracteres sobra: a linha mais longa, `K 5 1000 1000 2000 900`, tem 22.
- **`V` no fim do `setup()`**, depois de configurar os pinos padrão.

### 4.8 Esqueleto do tick

```c
static void tick(Canal &k) {
  switch (k.fase) {
    case ATAQUE:
      k.x += k.passo;
      if (k.x >= k.pico) { k.x = k.pico; k.fase = CORPO; }
      break;
    case CORPO:
      if (k.env.tau) k.x = k.alvo + (k.x - k.alvo) * k.kDec;
      break;
    case SOLTURA:
      k.x -= k.passo;
      if (k.x <= 0) { k.x = 0; notaSilencio(k); k.fase = PARADO; }
      break;
    case DIRETO:
      if ((int32_t)(millis() - k.diretoAte) > 0) trava(k);
      return;                                   // o duty do D não passa pela curva
    default: break;
  }
  uint16_t d = k.fase == TRAVADO ? 0
             : k.fase == PARADO  ? k.cal.dmin
             : k.cal.dmin + (k.cal.dmax - k.cal.dmin) * powf(k.x, k.cal.gama / 1000.0f);
  envDuty(k, d);                                // ‰ → 12 bits; 0 → pino em BAIXO fixo
}
```

---

## 5. Página (`index.html`)

### 5.1 Ler a serial e o aperto de mão

Hoje a página só escreve (`ser.writer`). Ela passa também a ler:

```js
async function lerSerial(port){
  const dec = new TextDecoder(); let resto = '';
  ser.reader = port.readable.getReader();
  try {
    for (;;){
      const { value, done } = await ser.reader.read();
      if (done) break;
      resto += dec.decode(value, { stream: true });
      let i;
      while ((i = resto.indexOf('\n')) >= 0){ recebido(resto.slice(0, i).trim()); resto = resto.slice(i + 1); }
    }
  } catch (e) {} finally { try { ser.reader.releaseLock(); } catch (e) {} }
}
```

- `recebido(l)`: se a linha casar `/^V \d/`, guarda `ser.fw = { proto, placa, n, recursos }`. Se a
  página não tiver perguntado, é um reinício do ESP (3.3). Qualquer outra linha vai para o registro
  com `← ` na frente.
- `serialClose()`: `await ser.reader.cancel()` **antes** de `port.close()`, senão o `close` falha
  com a leitura presa.
- Ao conectar: `ser.fw = null`, depois `X` e `V`. O `V` se repete a cada 500 ms, até 8 vezes, ou
  até chegar a resposta. A placa pode estar reiniciando por causa da abertura da porta, e o anúncio
  espontâneo do `setup()` também conta como resposta. Sem resposta em 4 s, a página fala v1 e
  escreve em `serMsg`: "firmware antigo: o arco só liga e desliga".
- `serMsg` com v2: "conectado · firmware v2 · envelope no arco".
- `const v2 = () => (ser.fw && ser.fw.proto >= 2 && ser.fw.recursos.includes('env')) || (!ser.writer && logAberto());`

### 5.2 Configuração do canal: `serialConfig()`

`serialConfig()` substitui `serialPinos()` em todos os lugares onde ela é chamada (conexão, mudança
de pino, placa ou número de flybacks, antes de cada `R`, `testar`). Ela manda os `P` como hoje e,
se `v2()`, também `L`, `K` e `E` dos seis canais. Canal acima de `esp.n` vai com −1 no `P` e no `L`.

Ela também é chamada quando mudam o envelope de um canal ou de um instrumento (mixer,
`aplicarSons`), a calibração (5.6) e o número de flybacks.

### 5.3 Força na nota

Tirar a curva de `scheduleVoice` para uma função só, usada pelo áudio e pela serial:

```js
const picoDe = (s, usaVel) => usaVel ? .25 + .75 * Math.pow(Math.min(127, s.v || 96) / 127, 1.4) : 1;
```

- `scheduleVoice`: `const pico = vol * picoDe(s, usaVel);`
- `serialStart`: os eventos levam `a: Math.round(1000 * picoDe(s, velOf(i)))`, e o `N` sai como
  `'N ' + c + ' ' + ms + ' ' + f.toFixed(2) + (v2() ? ' ' + a : '')`.

O envelope e a dinâmica de cada canal saem de `envOf(i)` e `velOf(i)`, **as mesmas funções da
síntese**. Se a regra de qual som cada arco toca mudar (montagem fixa, `familiaDoArco`), a serial
acompanha sozinha.

### 5.4 Receita: `E`

```js
function linhaE(i){
  const env = envOf(i);
  return 'E ' + i + ' ' + Math.round(ATAQUE * 1000) + ' ' + (env ? Math.round(env.tau * 1000) : 0)
       + ' ' + (env ? Math.round(env.sus * 1000) : 1000) + ' 6';
}
```

O `6` é a rampa final do áudio, e vale virar constante (`SOLTURA = .006`), usada nos dois lugares.

### 5.5 Pinos de ENV

- `PLACAS[x].env`: os padrões da tabela 4.1. `esp.env`: um vetor de 6, validado contra a lista da
  placa como `esp.pinos`, e salvo junto em `salvarEsp()`. Trocar a placa repõe os padrões.
- No painel de pinos, cada canal ganha um segundo seletor, "env", ao lado do de "nota". A marca de
  repetido (`dup`) passa a considerar **os dois vetores juntos**.
- `subCanal(i)`: `'GPIO 4 · env 11'`.

### 5.6 Calibração

Um bloco "Calibrar flyback" no painel de saída, habilitado só com firmware v2 conectado e a
música parada:

- seletor de canal;
- frequência do tom: 110, 220 ou 440 Hz (padrão 220);
- controle deslizante de **duty do ENV**, de 0 a 100% em passos de 0,1% (o valor mandado é em ‰);
- botão **Tocar / Parar**. Ligado, ele manda `D c d f` a cada 500 ms com o valor atual do controle,
  e mover o controle manda na hora. Desliga sozinho em 30 s. Ao desligar, manda `X`;
- botões **"isto é o mínimo"** e **"isto é o máximo"**, que gravam o valor do controle em
  `esp.cal[c].min` ou `.max`. Avisam se o mínimo ficar maior ou igual ao máximo;
- campos para `gama` (padrão 0,50) e "largura da nota" (padrão 50%), escondidos atrás de "mais";
- botão **"ouvir"**, que toca uma escala curta (dó a dó, 300 ms por nota, força 1000, depois 500)
  com o envelope atual do canal. Serve para julgar a calibração de ouvido.

`esp.cal = [{ min: 300, max: 600, gama: 500, larg: 500 } × 6]` é **por canal físico**, ou seja,
por flyback. Não depende da música nem do instrumento.

Quem mede é a pessoa na bancada, com a ponta do osciloscópio no shunt. O procedimento está na
seção 7, e a página pode mostrar um resumo dele junto do bloco.

### 5.7 Sinal de vida

No `pump` de `serialStart`, se `v2()`, manda `.` sempre que tiverem passado 500 ms desde o último
envio (de qualquer linha). `serialHalt()` continua mandando `X`.

### 5.8 `testar(i)`

```
serialConfig(); R; N i 0 440.00 1000; F i 600
```

O `N` vai sem força para o v1.

### 5.9 O que **não** muda

- A síntese em onda quadrada, o envelope no áudio, o P2, o WAV e a separação dura.
- Mudo e solo (`soa(i)`): canal calado não manda evento, como hoje.
- O ganho do mixer não vai para a serial (3.6 e 9.1).
- `LOOKAHEAD`, os carimbos em ms e o `R` por começo.

---

## 6. Documentação a atualizar

- **`docs/protocolo-serial.md`**: acrescentar o v2 (seção 3 inteira), mantendo a tabela do v1.
- **`CLAUDE.md`, "A restrição que define tudo"**: hoje diz "sempre em timbre de onda quadrada,
  **sem envelope, sem dinâmica de amplitude perceptível**". Com a V5 isso deixa de valer pela
  serial: o arco continua monofônico e com timbre de quadrada, mas passa a ter dinâmica, pelo limite
  de corrente. Reescrever e citar este documento.
- **`CLAUDE.md`, "Saída serial"**: a frase sobre a polaridade ("o NPN no pino 4 do 555 corta o
  arco com o GPIO em ALTO") vale para a V3.5. Na V5 é o contrário (NOTA em ALTO libera), e a
  polaridade passa a ser por canal (`INVERTIDO`). Acrescentar que, com a V5, o P2 não aciona a
  placa (2.5).
- **`CLAUDE.md`, "O que está aberto"**: o primeiro teste de bancada passa a ser o ESP32-S3 com a
  placa V5.
- **Comentário de `ENVELOPES` no `index.html`** (o que diz que `nenhum` reproduz o OOK e que os
  outros valem para a modulação contínua): acrescentar que, na V5, todos chegam ao arco pela serial.
- **Cabeçalho do `flyback-esp32.ino`**: protocolo v2, `INVERTIDO` por canal e núcleo 3.x no S3.
- **`docs/hardware-decisoes.md`**: uma seção V5 com o contrato da seção 2 deste documento.

---

## 7. Calibração na bancada (para quem monta)

Com a ponta do osciloscópio no topo do shunt e a garra no HVGD: **1 V = 20 A** (R_SH = 0,05 Ω).

1. **Teto, com JP1 em TRIM.** Toque o teste de um canal e suba o PR_I olhando a rampa no shunt. O
   joelho em "taco de hóquei" é o núcleo saturando. Volte uns 20% abaixo dele. Esse é o teto
   seguro daquele flyback, e com JP1 em ENV ele continua valendo, através de D_CL.
2. **JP1 em ENV.** Na página, "Calibrar flyback", tom de 220 Hz, Tocar.
3. **Mínimo.** Comece em 15% e suba devagar até o arco se sustentar sem falhar. Acrescente uns 2%
   de folga e marque "isto é o mínimo".
4. **Máximo.** Continue subindo até o pico no shunt **parar de subir** (é o teto do passo 1 atuando
   pelo D_CL) e marque "isto é o máximo" nesse ponto. Acima dele é zona morta: o envelope gastaria
   resolução sem mudar nada. Se o pico chegar ao valor desejado antes do teto, pode marcar ali
   mesmo.
5. **Ouvido.** Use "ouvir" com o envelope `percussivo`: a batida tem de cair de forma audível até o
   patamar. Se as notas fracas somem, diminua o `gama`. Se tudo soa igualmente forte, aumente.
6. **Temperatura.** Toque 10 min de uma música com `corda` (muito tempo em nível baixo) e confira o
   MOSFET e o shunt. Em nível baixo os pulsos ficam curtos, e a ligação pode cair fora do vale e
   esquentar mais do que no máximo. Se esquentar, diminua a "largura da nota".

---

## 8. Testes de aceitação

### 8.1 Site (`tools/testar_site.py`, porta simulada)

A porta simulada precisa de um `readable` que responda `V`. Testar os dois firmwares:

- **v1** (não responde ao `V`): as linhas saem **idênticas às de hoje**: `P`, `R`, `N c t f`, `F`,
  `X`, sem `L`, `K`, `E`, `D` ou `.`, e o `N` sem força. Depois de 4 s, a mensagem de firmware
  antigo.
- **v2** (responde `V 2 esp32s3 6 env`):
  - antes de cada `R` saem 6 `P`, 6 `L`, 6 `K` e 6 `E`;
  - o `N` leva a força, igual a `Math.round(1000 * picoDe(...))` do mesmo segmento que o áudio
    agenda;
  - `nenhum` vira `E c 4 0 1000 6`, e `corda` vira `E c 4 900 0 6`;
  - mudar o envelope de um canal com a porta aberta manda o `E` daquele canal na hora;
  - tocando, um `.` a cada ≤ 500 ms; pausa manda `X`;
  - um `V` espontâneo durante a música dispara a configuração inteira e um `serialStart` novo;
  - na calibração, `D` a cada ≤ 500 ms, `X` ao parar, desligamento sozinho em 30 s, e o bloco
    desabilitado enquanto toca;
  - pino de ENV repetido com um de NOTA fica marcado.

### 8.2 Firmware, só o ESP (osciloscópio nos GPIO, sem placa de potência)

| Teste | Esperado |
|---|---|
| boot e regravação | NOTA e ENV em BAIXO do reset até o `setup()`, sem pulso |
| `R`, `N 0 0 440.00 1000`, `F 0 1000` | NOTA a 440 Hz, 50%, por 1 s; ENV sai de `dmin`, sobe em 4 ms até `dmax` e fica (com `E 0 4 0 1000 6`) |
| o mesmo com `E 0 4 120 100 6` | x cai com τ = 120 ms até 0,1; o duty do ENV acompanha √x e para em `dmin + (dmax−dmin)·√0,1` |
| `X` no meio de uma nota | NOTA e ENV a zero em ≤ 1 ms |
| `N` sem `F` | corta em 20 s, com ENV a 0 |
| `.` e depois silêncio na serial | `X` em 1,5 s |
| `D 0 500 220.00` uma vez só | ENV a 50%, NOTA a 220 Hz, tudo apaga em 2 s |
| seis canais no S3, frequências diferentes | seis notas ao mesmo tempo, erro < 2 cents até 2 kHz no contador do osciloscópio |
| nota saindo do silêncio | começa na meia-onda ligada (fase zerada) |
| `?` | mostra o que está na seção 4.6 |

### 8.3 Com a placa V5 (primeiro com o primário em tensão baixa, por exemplo 12 V)

- O pico no shunt acompanha o duty do ENV, e no `D` a relação é aproximadamente linear acima de ~20%.
- JP1 em TRIM: o ENV não muda nada, e a NOTA continua ligando e desligando.
- JP1 em ENV, com o ENV a 100%: o pico para no teto do PR_I (D_CL).
- ESP desligado, ou com o cabo de controle solto: nada de arco.

---

## 9. Fora do escopo e decisões em aberto

1. **Ganho do mixer no arco.** Hoje ele não vai. Uma opção é escalar x pelo ganho, mas o padrão de
   70% baixaria o arco sem ninguém pedir. Se for feito, que seja um controle próprio ("nível do
   arco"), separado do volume do monitor.
2. **ENV antecipado.** Como o ESP enxerga a fila 100 ms à frente, daria para mover o ENV uns 3 ms
   antes da NOTA subir e compensar o filtro. Com o estacionamento em `dmin` (2.4) o ganho é de ~1 ms,
   e não vale a complexidade agora.
3. **Calibração gravada no ESP** (NVS, `Preferences`). Não é necessária enquanto o ESP só toca com
   a página conectada.
4. **Leituras analógicas** (temperatura por NTC, bobina de captação, corrente média). Os pinos ADC1
   ficaram livres para isso (4.1), mas não fazem parte deste documento.
5. **Busca automática do vale pela frequência.** Continua no trimpot PR_T da placa, fora do ESP.
