# Flyback Musical — Registro de Decisões Técnicas

**Projeto:** FBMD / LMD — Lightning Modulated Driver
**Revisões cobertas:** V3 → V3.5 → V4 (em definição)
**Data do registro:** setembro de 2026

---

## 1. Objetivo do sistema

Reproduzir música através do arco de plasma de um transformador flyback, com dois modos de operação:

- **OOK / Interrupter** — portadora de largura fixa, ligada e desligada na frequência da nota. Arco agressivo, som "quadrado", silêncio absoluto entre notas.
- **Modulação contínua / Classe D** — portadora sempre presente, largura de pulso variando com o áudio. Arco denso e contínuo, fidelidade maior, estresse térmico maior.

Meta de longo prazo: seis canais independentes, telemetria de frequência e temperatura, e um circuito que não precise de recalibração manual a cada transformador.

---

## 2. Ponto de partida

### V3 (funcional, baseado no Easy-Flyback do Franzoli Electronics)

Um único NE555 gerando frequência com duty fixo. Interrupção feita aterrando o pino 4 por um transistor. Cru, mas funcional.

**Limitação:** sem controle de largura de pulso. A única variável era a frequência.

### V3.5 (funcional, evolução própria)

| Bloco | Implementação |
|---|---|
| Base de frequência | NE555 astável (U12): R14 6K8 + PR4 5k + R13 10K + C21 4n7 |
| Largura de pulso | NE555 monoestável (U13): R15 2K2 + PR5 5k + C24 4n7 |
| Limiar OOK | LM311 (U10): C8 1µF, terra virtual 6 V por R11/R16 100K, limiar por PR6 10k entre R9/R10 4K7, histerese R17 1M, pull-up R18 4K7 |
| Roteamento | `FOut → FIn`, `MusicOut → pino 4 do U13`, `OUTPUT → placa de potência` |

**Placa de potência:** 24 V, banco de 4× 470 µF, primário externo de 10 espiras, IRFP260N, MUR860 em antiparalelo do dreno ao terra, zener 15 V no gate, R13 22 Ω com 1N4148 em paralelo (ligamento amortecido, desligamento rápido), totem pole BC337/BC327 alimentado em 12 V, e banco de 3× 100 nF MKP entre dreno e terra.

**Problemas identificados:**

1. MOSFET esquentando de forma incômoda.
2. Ajuste inteiramente manual, válido para um transformador específico.
3. Sem proteção de nenhum tipo além do zener de gate.
4. Sem telemetria.

---

## 3. Decisões de arquitetura da V4

### 3.1 PLL de fase vs malha travada em frequência

**Problema:** a literatura de hobby e uma consulta anterior a outra IA trataram "PLL com microcontrolador" como inviável por causa do jitter de software.

**Análise:** são dois problemas distintos que estavam sendo confundidos.

- **PLL de fase** — a borda do gate é derivada diretamente da bobina de realimentação. O atraso de laço importa ciclo a ciclo. Exige hardware analógico (CD4046 ou realimentação direta). O ESP realmente não cabe nesse laço.
- **Malha travada em frequência** — a bobina só serve para *medir* o período. Quem gera a borda é o timer do MCPWM, em hardware. O ESP escreve o registrador de período de vez em quando.

**Decisão:** malha de frequência.

**Justificativa:** o jitter de borda passa a ser um tick de clock (~6 ns), porque a CPU nunca toca na borda. O jitter do RTOS afeta apenas a banda de controle, e a ressonância do flyback deriva em escala de milissegundos, não de microssegundos. Atualizar o período a cada 1 ms é ordens de grandeza mais rápido que o fenômeno físico.

Esse era exatamente o "PLL solto" proposto originalmente. A implementação anterior falhava por usar contagem por interrupção de software em vez de captura por hardware.

### 3.2 Modulação analógica vs digital

**Decisão:** analógica para o modo contínuo.

**Justificativa:**

| Parâmetro | Digital (ADC + MCPWM) | Analógico (rampa + LM311) |
|---|---|---|
| Resolução de largura | ~12 bits a 30 kHz | contínua |
| Amostragem de áudio | limitada pelo ADC | tempo real |
| Jitter | sujeito ao RTOS | determinado pela física |

O ESP32-S3 tem ADC interno de ~9 bits efetivos e ruidoso. Não tem Bluetooth Classic, então A2DP está fora; áudio digital exigiria I2S com ADC externo ou USB Audio. Para tocar o celular pelo P2, o analógico é superior sem discussão.

### 3.3 Rampa que preenche o período vs monoestável de largura constante

**Problema encontrado:** a topologia originalmente desenhada para a V4 tinha uma dente-de-serra gerada por fonte de corrente constante, resetada pelo clock do ESP, preenchendo todo o período. A amplitude dessa rampa é:

```
V_pico = I / C × t_carga ≈ I / (C × f)
```

Ou seja, **inversamente proporcional à frequência**. Varrendo 20 a 33 kHz, o pico cairia de 7,1 V para 4,3 V. O índice de modulação colapsaria, e em frequência alta o áudio simplesmente deixaria de cruzar a rampa — duty travado, arco apagado.

Esse defeito estava presente no esquemático `ControlBoardV4` e nunca havia sido resolvido nas discussões anteriores, apenas adiado.

**Decisão:** inverter quem reseta a rampa. Em vez de o clock resetá-la no fim do período, o **próprio cruzamento com o áudio** a reseta.

```
t_ligado = C × V_áudio / I
```

A frequência não aparece na equação. A profundidade de modulação fica constante em toda a faixa de varredura.

**Consequência:** essa topologia (rampa + comparador + latch + transistor de descarga) já existe empacotada no NE555 em modo monoestável, com o pino 5 como entrada do nível de comparação.

### 3.4 Rampa exponencial vs fonte de corrente constante

**Decisão:** fonte de corrente constante (BC557C + 2× 1N4148 de referência + resistor de emissor).

**Justificativa:** carga por resistor segue curva exponencial, o que torna a relação tensão-tempo logarítmica e gera distorção harmônica severa. Com corrente constante, `dV/dt` é fixo e a conversão é linear.

Substituir o resistor de temporização do 555 por essa fonte lineariza a modulação pelo pino 5.

### 3.5 NE555 é adequado?

**Dúvida levantada:** o 555 tem fama de componente de hobby, usado como clock e temporizador. Seria adequado para esta aplicação?

**Análise:** internamente o 555 é dois comparadores, um latch RS, um transistor de descarga e uma saída de 200 mA. Usado como monoestável com fonte de corrente, é exatamente esse conjunto de primitivas que se está usando. A má fama vem do uso com RC, que é o uso ruim.

Defeitos reais, sem romantismo:

- Pico de corrente de curto na transição de saída (exige 100 nF colado ao pino 8).
- ~100 ns de atraso no comparador de threshold — menos de 1% sobre um pulso de 12 µs.
- Não redisparável durante o próprio pulso. Se o período ficar menor que t_ligado, ele ignora disparos e divide a frequência. Já observado na prática.

**Decisão:** manter, com caminho de upgrade para TLC555/LMC555 (mesma pinagem, CMOS, bordas ~30 ns, sem crowbar) se o jitter se mostrar relevante.

**Vantagem estrutural:** o RC impõe um **teto de largura em hardware** que nenhum erro de firmware alcança. Essa propriedade é perdida se o 555 for eliminado.

### 3.6 Optoacoplador: 6N136 vs 6N137

**Decisão:** 6N137 obrigatório no caminho de realimentação.

**Justificativa:** orçamento de tempo para o atraso do vale.

| Etapa | Atraso |
|---|---|
| LM311 do detector de fase | ~200 ns |
| Optoacoplador (6N136 / 6N137) | 800 ns / 50 ns |
| Sincronismo de entrada do ESP | ~10 ns |
| Saída do ESP + inversor NPN | ~200 ns |
| Disparo do 555 | ~100 ns |
| FOD3184 | ~350 ns |

Com o 6N137 a cadeia consome ~910 ns. Com o 6N136, ~1660 ns. Contra um quarto de período de oscilação de ~1,43 µs, o 6N136 estoura o orçamento inteiro.

### 3.7 Totem pole vs FOD3184

**Decisão:** migrar para o FOD3184.

**Justificativa:**

| | Corrente de pico | Tempo de transição |
|---|---|---|
| BC337 / BC327 em coletor comum | ~1 A | ~236 ns |
| FOD3184 | 3 A | ~79 ns |

Com os 236 nC do IRFP260N, a perda de cruzamento escala com esse tempo. Some-se a saída MOS trilho a trilho (o seguidor de emissor perde um V_BE em cada extremo, entregando ~11,3 V ao gate e desligando a ~0,7 V acima do source) e o isolamento galvânico entre a placa lógica e a de potência.

**Custo:** propagação piora de ~50 ns para ~350 ns, consumindo parte do orçamento do vale. Atraso fixo é deslocamento de fase, não perda.

**Efeito colateral positivo:** desligamento três vezes mais rápido permite reduzir a capacitância de snubber no dreno, o que reduz o `½CV²` do ligamento. As duas mudanças andam juntas.

### 3.8 Alimentação do FOD3184

**Decisão:** regulador 7815 derivado dos 24 V da própria placa de potência.

**Descartado 24 V direto:** a saída do FOD3184 é trilho a trilho, então V_CC de 24 V coloca 24 V no gate. O IRFP260N aceita ±20 V. O zener de gate teria que afundar 3 A e morre antes do MOSFET.

**Descartado 7812:** a família do FOD3184 (compatível com HCPL-3120) tem bloqueio por subtensão com limiar entre 11 e 13,5 V e faixa recomendada de 15 a 30 V. A 12 V a operação fica sobre o limiar, com risco de não ligar ou de operação intermitente.

**Consequências:**
- Zener de gate de 15 V → 18 V (1N4746), senão ele conduz no joelho com trilho de 15 V.
- Desacoplamento de 1 µF em paralelo com 100 nF a menos de 5 mm dos pinos 5 e 8. Os 3 A de pico saem dos capacitores, não do regulador.
- Dissipação do 7815: ~15 mA médios com 9 V de queda, pouco mais de 100 mW. Sem dissipador.

**Sobre o isolamento:** não é necessária fonte isolada por transformador. Basta que o lado do LED fique referenciado ao terra lógico e o lado de saída ao terra de potência, com os dois terras nunca se encontrando. **Verificar com multímetro em continuidade** que as duas fontes não compartilham terra pela tomada.

### 3.9 TVS de grampeamento

**Decisão:** se usar, 1.5KE100A. **Nunca 130 V.**

**Justificativa:** um TVS de 130 V de standoff grampeia em torno de 179 a 188 V sob pulso nominal. Somando os 24 V de entrada, o dreno chega a ~212 V, acima dos 200 V do IRFP260N. O MOSFET entra em avalanche antes do TVS atuar — o componente não protege nada.

O de 100 V grampeia perto de 162 V, resultando em 186 V no dreno com 14 V de margem.

**Estado atual:** operando sem TVS há horas sem falhas, com a energia de dispersão indo para avalanche do próprio MOSFET, que tem especificação para isso. Não é urgente, mas protege o caso ruim (arco apagando de repente, secundário abrindo).

**Malha RCD:** só faz sentido em conjunto com o TVS, para tirar dele a dissipação contínua. Sozinha, com energia de dispersão pequena, adiciona perda em vez de tirar.

### 3.10 MOSFET

**Decisão:** manter IRFP260N por ora.

O IRFP4227 tem Q_g de 70 nC contra 236 nC e R_DS(on) de 24 mΩ contra 40 mΩ. Em análise inicial isso valia ~2 W. Porém o ponto de operação real tem corrente alta, regime em que R_DS(on) pesa mais que Q_g. Decisão adiada até haver medida de corrente de entrada.

### 3.11 Comparador vs ADC no detector de fase

**Decisão:** comparador (LM311).

**Justificativa:** a limitação não é resolução, é taxa de amostragem. Para localizar um evento de 175 kHz com precisão de 100 ns seriam necessários ~10 MSPS. O ADC do ESP32 entrega centenas de kSPS na prática. Um comparador não amostra: comuta no instante do cruzamento, com resolução temporal igual ao seu tempo de propagação.

O próprio Franzoli Electronics usa um LM311 como detector de cruzamento por zero no Easy-Flyback.

**Uso correto do ADC:** amplitude e diagnóstico, amostrado devagar (a cada ms), para detectar que o arco apagou. Tempo pelo comparador, amplitude pelo ADC.

### 3.12 Limiar fixo vs auto-zero

**Problema:** calibrar seis limiares na mão, um por canal, é impraticável e não é universal entre transformadores.

**Decisão:** referência do comparador tirada de um filtro passa-baixas do próprio sinal.

**Justificativa:** um RC com constante de tempo de alguns milissegundos tem corte perto de 100 Hz. As feições do sinal estão em 22 kHz e 175 kHz — três ordens de grandeza acima. O filtro extrai apenas o valor médio. Trocar de flyback muda a ressonância, mas não muda o fato de que a média é a média.

Um resistor e um capacitor por canal, sem trimpot, sem calibração individual.

**Complemento:** histerese (resistor da saída para a entrada não inversora) para eliminar o *chatter* do comparador no cruzamento, mais um deslocamento de 100 a 200 mV no limiar para evitar comutação no ruído quando o sinal está parado.

### 3.13 Atraso do vale: RC fixo vs calculado pelo ESP

**Decisão:** calculado pelo ESP.

**Justificativa:** a frequência de oscilação é `1/(2π√(L·C))`. Trocar o flyback muda L, muda a oscilação, e um RC fixo passa a estar calibrado para o transformador errado. Com o ESP medindo o período da oscilação (a mesma captura que ele já faz), o atraso se recalibra sozinho.

A geração do atraso permanece em hardware: o evento arma o timer, o timer dispara depois do valor programado. A CPU só escreve o número, e escreve devagar.

Essa arquitetura é a que os controladores quase-ressonantes comerciais implementam. A nota AN1326 da ST (L6565) descreve a detecção de desmagnetização pelo enrolamento auxiliar, cuja tensão reproduz a de dreno escalada pela relação de espiras. Patentes de QR *auto-tuning* descrevem medir a largura do pulso de comparação, dividir para obter um quarto de período e armazenar o valor.

**Vantagem adicional:** permite *valley skipping* (pular vales quando o cálculo cairia cedo demais), impossível com RC fixo. O NCP1342 da onsemi implementa exatamente isso.

### 3.14 Meio período vs um quarto de período

**Correção importante.** O atraso correto depende do que o comparador detecta:

- Do **colapso do patamar** até o vale: **meio período** (no colapso o dreno está no máximo).
- Do **cruzamento por zero** até o vale: **um quarto de período** (nesse instante o dreno já desceu até a tensão de entrada).

Um comparador com limiar perto de zero detecta o cruzamento. Para uma oscilação de 5,7 µs, o atraso é **1,43 µs**, não 2,85 µs.

**Detalhe de implementação da AN1326:** o circuito de detecção precisa ser *armado* antes de disparar — só aceita a borda de descida depois de ter visto uma subida acima de um limiar mais alto. Isso impede que ruído durante o tempo ligado dispare o gate. Vale replicar essa lógica de duas etapas.

### 3.15 Proteção de sobrecorrente (OCP)

**Motivação:** se o 555 for eliminado e o ESP passar a definir a largura, a corrente de pico no primário vira consequência de um número na memória de um microcontrolador:

```
I_pico = V_entrada × t_ligado / L_primário
```

Um registrador escrito errado, um glitch no boot ou um travardo no instante errado produz um pulso de duração arbitrária. Núcleo satura, indutância despenca, MOSFET abre.

**Decisão:** shunt não indutivo no source, filtro RC (para o pico de comutação não disparar o comparador todo ciclo), LM311 contra referência, saída em coletor aberto derrubando o sinal antes do gate driver.

**O que o OCP faz e o que não faz:**

- Controla o **desligamento**. Substitui "termine depois de X µs" por "termine quando a corrente chegar a Y A".
- **Não** controla o ligamento. Não sabe onde está o vale.
- Ao manter a corrente de pico constante, mantém a energia por pulso constante, portanto a duração da desmagnetização constante, portanto **o vale parado no tempo**.

Essa última propriedade é o que permite ao Franzoli operar sem realimentação nenhuma: OCP estabiliza o alvo, e uma sintonia manual feita uma vez continua valendo.

**Contrapartida:** com o OCP definindo o fim do pulso, o tempo ligado passa a variar sozinho conforme indutância, tensão de entrada e temperatura. Um oscilador de frequência fixa perde o vale assim que o OCP começar a atuar. OCP e rastreamento se combinam bem, mas o OCP torna o rastreamento **mais** necessário, não menos.

O NCP1342 descreve exatamente esse par: desligamento determinado pelo limite de corrente de pico, ligamento determinado pela desmagnetização.

### 3.16 Distorção em MIDI gerado pelo ESP

**Problema observado em tentativa anterior:** música vinda de MIDI, gerada diretamente pelo ESP, saía distorcida.

**Diagnóstico:** não é resolução. É quantização de rajada.

A portadora está em ~32 kHz e a nota Lá em 440 Hz. São 72,7 ciclos de portadora por ciclo de nota — não inteiro. Cortando a portadora de forma assíncrona, cada período da nota contém ora 72, ora 73 pulsos. Pior: se o corte cair no meio de um pulso, o último pulso sai truncado, com variação de até 100% na energia.

**Soluções:**

1. **Gating sincronizado.** Não alternar o GPIO. Habilitar e desabilitar o *gerador* do MCPWM, que respeita o limite do ciclo do timer: o pulso corrente termina inteiro e o próximo arranca numa borda.
2. **Contar pulsos em vez de tempo.** A nota Lá vira "72 pulsos ligados, 72 desligados". A frequência sai ~0,7% errada (muito menos que um semitom) e em troca cada período tem exatamente o mesmo número de pulsos.

**Observação:** é provável que a V3.5 soe melhor que a tentativa direta pelo ESP não por causa dos 555, mas porque o monoestável já fazia o sincronismo de rajada sem que isso fosse intencional — um monoestável já iniciado termina o pulso antes de obedecer ao reset.

---

## 4. Campanha de medição

### 4.1 Método

Bobina de captação improvisada: 3 espiras de fio em volta do núcleo de ferrite, uma ponta ao terra de potência, outra a um resistor de ~220 Ω em série até a ponta do osciloscópio (10x). Sem conexão elétrica com o circuito, apenas acoplamento magnético. Tensão de saída de 1 a 3 V.

Ponta em 10x obrigatória: em 1x os ~100 pF da ponta amortecem a própria oscilação que se quer medir, e o rating de tensão é insuficiente.

Garra de terra curta (mola, não o rabicho jacaré): com dV/dt de milhares de volts por microssegundo, uma espira de 15 cm capta ringing que não existe no circuito.

Osciloscópio Tektronix TDS 1012C-EDU. CH1 na captação, CH2 na saída do segundo 555, trigger em CH2, RUN/STOP para congelar antes de posicionar cursores.

### 4.2 Cuidado com as medidas automáticas

As medidas automáticas de largura do osciloscópio usam o cruzamento a 50% entre topo e base detectados. O sinal tem três patamares diferentes mais oscilação, então o limiar de 50% cai onde não há transição física. O osciloscópio reportou `Larg. Pos` de 36,34 µs num período de 38,25 µs (95% de duty), quando o duty real era ~35%.

**Período e frequência são confiáveis** (dependem só de contar cruzamentos repetidos). Largura positiva, negativa e ciclo de trabalho **não são**. Use cursores.

### 4.3 Resultados (frequência em 32 kHz, duty ~42%)

| Grandeza | Valor |
|---|---|
| Período | 31,25 µs |
| Tempo ligado | 13,5 µs |
| Pico de desligamento | ~2,0 µs |
| Desmagnetização | 6,8 µs |
| Período da oscilação | 5,7 µs (175,4 kHz) |
| Tempo morto restante | 8,95 µs |

Consistência: 8,95 / 5,7 = **1,57 oscilações** de tempo morto, batendo com a contagem visual de "uma e meia". As três medidas são internamente coerentes.

### 4.4 Hipóteses testadas e descartadas

**Condução contínua — DESCARTADA.** Existe oscilação amortecida visível depois do patamar. Se o pulso seguinte chegasse antes do núcleo esvaziar, o patamar seria truncado e nenhuma oscilação apareceria. O núcleo esvazia com folga.

**Capacitância excessiva sendo o único problema — INCONCLUSIVO.** Os 3× 100 nF MKP estão entre dreno e source. Na especificação do Easy-Flyback I do Franzoli, esse banco de 300 nF é descrito como **capacitor ressonante**, não snubber. Falta medir a capacitância real com capacímetro.

**Topologia ressonante sintonizada — PROVAVELMENTE NÃO.** Com 300 nF e oscilação de 175 kHz, a indutância implicada é ~3 µH. Isso é plausível para 10 espiras num núcleo com entreferro largo (núcleos de flyback de TV são entreferrados para armazenar energia). Mas significa que o tanque ressoa em 175 kHz enquanto o chaveamento está em 32 kHz — cinco vezes abaixo. O circuito opera como flyback em condução descontínua com um capacitor grande no dreno, e não como conversor ressonante sintonizado.

Reforça essa leitura o formato da onda: **patamar plano de desmagnetização seguido de oscilação rápida** é a assinatura de condução descontínua. Um tanque sintonizado produziria uma senoide contínua sem patamar.

### 4.5 O que foi confirmado

**O duty era a causa principal do aquecimento.** Operando a 70% o MOSFET ficava quente; a 30% ficou apenas morno. Num pulso triangular em condução descontínua, `I_rms² = I_pico² × D / 3`. Baixando o duty por 2,3, a corrente de pico cai por 2,3 e o duty cai por 2,3 — a perda por condução cai cerca de **doze vezes**.

**Balanço volt-segundo.** Com `V_entrada × t_ligado = V_refletida × t_desmag`:

```
24 × 13,5 = V_refletida × 6,8  →  V_refletida ≈ 48 V
```

Tensão de dreno durante a desmagnetização: ~72 V, não 186 V. O IRFP260N de 200 V opera com quase três vezes de margem.

**O primeiro vale deve ser grampeado em zero.** Como V_refletida (48 V) é maior que V_entrada (24 V), a oscilação tenta levar o dreno a −24 V. O MUR860 em antiparalelo conduz e grampeia em zero, produzindo uma **janela plana** de centenas de nanossegundos em vez de um mínimo pontiagudo. É chaveamento em tensão zero de graça, e relaxa muito a precisão exigida do atraso.

**Valley skipping observado empiricamente.** Aumentando a frequência, o número de oscilações no tempo morto caiu de 3 para 1,5. Isso é esperado: o tempo ligado é fixo pelo monoestável e a desmagnetização depende dele, então toda a variação de período é absorvida pelo tempo morto. O circuito saltou do terceiro para o segundo vale.

### 4.6 O que sobra a medir

| Medida | O que decide |
|---|---|
| Capacitância real dreno-source | confirma o valor do tanque |
| Período da oscilação com cursor (confirmação) | dimensiona o atraso do vale |
| Corrente de entrada da fonte | permite calcular indutância real e corrente de pico |
| Primeiro vale: fundo achatado ou arredondado | confirma o grampeamento do MUR860 |
| **Deslocamento da frequência ótima com o comprimento do arco** | **decide se a V4 precisa de malha de rastreamento** |

A última é a mais importante. Se a frequência ótima se deslocar pouco quando o gap muda, o caminho do Franzoli (sintonia manual + OCP) é suficiente e a malha não se paga. Se se deslocar muito, a malha se justifica.

---

## 5. A referência: Franzoli Electronics

A V3 partiu do Easy-Flyback. A especificação publicada do Easy-Flyback I inclui:

- Fonte de 24 V / 30 A
- Oscilador NE555, onda quadrada de **50% de duty**, faixa 18 a 42 kHz, sintonizado em 22,5 kHz
- Detector de cruzamento por zero com Schmitt trigger usando **LM311**
- IRFP260N com ligamento suave (para reduzir picos de corrente vindos do banco ressonante) e desligamento rápido
- Flyback de TV CRT, primário de 8 espiras de 0,5 mm²
- **Capacitor ressonante: 3× WIMA MKP10 de 250 VAC / 100 nF em paralelo (300 nF)**
- Corrente de primário até 16 A RMS, 28 A de pico em operação, 60 A de pico na partida
- Tensão de pico no primário até 180 V em operação, 240 V na partida (avalanche em ação)
- Eficiência relatada em torno de 95% depois de sintonizado (revisão B, modo CW)

A placa mais recente (Cool Flyback) controla dois canais e traz, por canal, blocos rotulados **OCP** (sobrecorrente) e **Xsense** (sensor de corrente), além de conectores **OTP** (sobretemperatura) e **FAN**. Os conectores de saída têm pinos `+24V` e `FBK`, aparentemente os dois fios do primário, o que sugere **ausência de realimentação** — a sintonia é manual e o tanque LC, sendo capacitor de filme e primário de espiras fixas, não deriva.

### O que isso significa

O controle dele é **mais simples** que o da V3.5. Um 555 a 50% fixo. A vantagem dele não está em sofisticação de controle, está em:

1. Topologia com tanque ressonante bem casado.
2. Corrente elevada sustentada por banco de DC-link generoso.
3. Primário dimensionado para o tanque.
4. Sintonia feita corretamente uma vez.
5. As proteções (OCP, OTP) que este projeto vinha adiando.

Os 50% de duty não são escolha arbitrária: com V_refletida ≈ 2 × V_entrada, a condição de primeiro vale dá duty em torno de 50 a 55%. Ele chegou lá pelo caminho da sintonia, esta análise chegou pelo caminho do vale, e é o mesmo ponto.

---

## 6. Correções feitas ao longo da análise

Registradas para que quem ler não repita:

| Afirmação inicial | Correção |
|---|---|
| Os 300 nF no dreno seriam um snubber capacitivo lossy | São o capacitor ressonante por projeto, conforme especificação do Easy-Flyback |
| A partir disso, o circuito seria um conversor ressonante sintonizado | As medidas contradizem: patamar plano + oscilação rápida = condução descontínua. O tanque ressoa 5× acima da frequência de chaveamento |
| Atraso do vale = meio período da oscilação | Meio período a partir do colapso; **um quarto** a partir do cruzamento por zero, que é o que um comparador detecta |
| O ESP32-S1 não tem MCPWM | Tem. Dois periféricos, estrutura igual à do S3 |
| Um S3 não teria timers para seis canais | Tem. Dois grupos × três timers = seis. A objeção real era ruído, não contagem |
| Os 300 nF seriam "impossíveis" pela frequência medida | O argumento supunha indutância de centenas de µH. Com núcleo entreferrado e 10 espiras, ~3 µH é plausível e os 300 nF cabem |
| O MUR860 não teria serventia | Ele rouba a condução do diodo de corpo (lento, com recuperação reversa) e provavelmente grampeia o primeiro vale em zero |

---

## 7. Estado atual e caminhos

### Ganho já obtido, sem componente novo

Reduzir o duty de 70% para valores próximos de 40% derrubou a temperatura do MOSFET de forma clara. Subir a frequência aumentou o volume do arco e reduziu o tempo morto de 3 para 1,5 oscilações, aproximando o chaveamento do primeiro vale.

### Ajuste imediato na V3.5

Trocar **os dois** capacitores de temporização (C21 do astável e C24 do monoestável) de 4n7 para 3n3, escalando a janela de frequência de 20–31 kHz para cerca de 28–44 kHz. Trocar só um deles faz o monoestável perder o curso útil do trimpot de duty na faixa nova.

Alvo estimado para o primeiro vale, mantendo t_ligado em 13,5 µs:

```
T ≈ 13,5 + 2,0 + 6,8 + 2,85 ≈ 25 µs  →  ~40 kHz
```

Não eliminar o tempo morto por completo: zero tempo morto é condução contínua. O alvo é **meia oscilação**, ou seja, um fundo antes do próximo pulso.

### Bifurcação da V4

**Caminho A — sintonia manual + OCP.** Sem bobina auxiliar, sem comparador de fase, sem 6N137, sem firmware de rastreamento. Sintoniza na mão, OCP trava a energia por pulso, marca o trimpot. É o que o Franzoli faz. Perde a agnosticidade ao transformador: seis canais, seis ajustes.

**Caminho B — rastreamento pelo ESP.** Bobina auxiliar, LM311 com auto-zero, 6N137, captura no ESP, atraso calculado, OCP. Placa agnóstica ao transformador, recalibração automática, telemetria. Custo: firmware de registrador (captura, sincronismo, período dinâmico) que ainda não existe.

A medida de deslocamento da frequência ótima com o comprimento do arco é o que decide entre os dois.

### Arquitetura consolidada do Caminho B

| Bloco | Função |
|---|---|
| Bobina auxiliar + divisor + grampo | sensor de fase |
| LM311 com auto-zero e histerese | detector do evento de desmagnetização |
| 6N137 | isolação do caminho de realimentação |
| ESP32 (captura MCPWM) | mede período, calcula atraso do vale, gera disparo |
| NE555 monoestável + fonte de corrente | largura do pulso, com teto em hardware |
| LM311 de limiar | corte OOK no pino 4 |
| NE5532 | condicionamento de áudio para modulação contínua no pino 5 |
| LM311 de corrente + shunt | OCP, veto ciclo a ciclo |
| NTC no dissipador + ADC | rollback térmico |
| FOD3184 + 7815 | isolação e acionamento do gate |

Modo contínuo e OOK coexistem porque usam pinos independentes do 555 (5 e 4). Uma chave de duas seções alterna entre eles.

### Escalabilidade para seis canais

Divisão sugerida: um ESP32-S3 como sequenciador (USB MIDI para o PC, gerando seis ondas quadradas de nota, sem tocar em flyback nenhum) e um ESP32 por canal cuidando de rastreamento, OCP e NTC. Isolamento de falha: um canal em oscilação estranha não derruba os outros cinco.

Um único S3 tem timers para os seis, mas concentra seis cabos de realimentação vindos de seis arcos de plasma num só silício. Risco de bancada, não de datasheet.

**Recomendação de ordem:** montar **um** canal completo e rodar até confiar no firmware (soft-start, limites de período, timeout de partida, rollback térmico) antes de replicar. Seis canais idênticos com um erro de firmware são seis MOSFETs.

---

## 8. Decisões pendentes

1. **Aterramento da bobina auxiliar** — referenciada ao terra lógico (poupa o optoacoplador e 50 ns, mas aceita ruído de modo comum pela capacitância entre enrolamentos) ou detector de fase na placa de potência com retorno por 6N137. Nota: o atraso do optoacoplador é constante e se cancela na medição de intervalo entre duas bordas do mesmo caminho, o que torna a opção isolada quase gratuita.
2. **Caminho A ou B**, decidido pela medida de deslocamento da frequência ótima.
3. **Manter ou eliminar o NE555 monoestável** — eliminá-lo simplifica, mas transfere o teto de largura do hardware para o firmware e torna o OCP estrutural.
4. **Trocar o IRFP260N**, decidido pela medida de corrente de entrada.
