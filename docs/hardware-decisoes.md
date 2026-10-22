# Flyback Musical — Registro de Decisões Técnicas

**Projeto:** FBMD / LMD — Lightning Modulated Driver
**Revisões cobertas:** V3 → V3.5 → V3.6 → V4 (em definição)
**Data do registro:** setembro de 2026; bancada de 21/out/2026 e simulações da V3.6 na seção 9

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

**Atualização (21/out/2026):** a placa medida tem **IRFP264N** (250 V) no lugar do IRFP260N, e o zener de gate não existe nas versões novas. Ver a seção 9.

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

**Atualização (21/out/2026):** no ponto medido o dreno chega a ~211 V em todo ciclo (seção 9.2). Um TVS de 100 V ou de 130 V (1.5KE130A: ruptura de 124 a 137 V) entre dreno e terra conduziria a cada pulso, e não só no caso ruim. A V3.6 ficou sem TVS.

### 3.10 MOSFET

**Decisão:** manter IRFP260N por ora.

O IRFP4227 tem Q_g de 70 nC contra 236 nC e R_DS(on) de 24 mΩ contra 40 mΩ. Em análise inicial isso valia ~2 W. Porém o ponto de operação real tem corrente alta, regime em que R_DS(on) pesa mais que Q_g. Decisão adiada até haver medida de corrente de entrada.

**Atualização (21/out/2026):** a placa passou ao **IRFP264N** (250 V, 60 mΩ), para aguentar os picos de ~220 V do flyback sem avalanche. A corrente de entrada está medida na seção 9.2.

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

**21/out/2026:** a capacitância (300 nF, medida fora da placa), a corrente de entrada e o grampo do primeiro vale estão medidos na seção 9. Falta o deslocamento da frequência ótima com o arco.

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
- Eletrodos a no máximo 50 mm, para não danificar o isolamento do flyback

A página não fala em capacitância efetiva diferente da nominal. Pelo dono do projeto, o banco de entrada do Franzoli começou com 2× 2200 µF e passou a 4× 470 µF, o mesmo desta placa (isso não está na página).

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
| Com 300 nF e oscilação de 175 kHz, o primário teria ~3 µH | Era suposição. A bancada de 21/out dá **8 a 12 µH** (seção 9.3); os ~3 µH batem com a dispersão, não com o primário |
| O banco leu 66 nF na placa: os capacitores seriam de 22 nF | Cada capacitor do lote mede ~100 nF fora da placa: o banco é de 300 nF. Na placa, o MUR860 e o primário em paralelo enganam o capacímetro |
| Na V3.6, 150 nF no dreno no lugar de 300 nF | O valor vinha de um primário suposto de 20 µH. Com 8 a 10 µH, 150 nF sobe o dreno de 35 a 60 V e quase não dá arco a mais: ficam os 300 nF (seção 9.4) |

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
4. **Trocar o IRFP260N** — feito: a placa usa o IRFP264N (seção 9).

---

## 9. Bancada de 21/out/2026 e simulações da V3.6

Medidas do dono do projeto num flyback de 10 espiras, e o que as simulações em ngspice tiraram delas. As simulações ficam em `FlybachSimulations/`, fora deste repositório; o script de cada resultado vai entre parênteses.

### 9.1 A placa medida

| Item | Valor |
|---|---|
| Base | Easy-Flyback I do Franzoli (seção 5), com totem pole, MUR860 e IRFP264N |
| MOSFET | **IRFP264N**, 250 V |
| Capacitor de dreno | 3× 100 nF MKP = **300 nF** |
| Banco de entrada | 4× 470 µF; fonte em 24,03 V |
| Primário | 10 espiras, externo |
| Bobina de realimentação | 3 espiras |
| Núcleo | 1,2 × 1,7 cm, tratado nas simulações como a seção da perna (2,04 cm²) |

### 9.2 Medidas

| Grandeza | Valor |
|---|---|
| Gate | 15,68 µs ligado, 9,55 µs desligado, 39,69 kHz: o ponto de arco mais eficiente achado pela bobina |
| Bobina de realimentação, pulso ligado | +7 V |
| Logo depois de desligar | mergulho em V de ~3,5 µs até −56 V |
| Em seguida | ~5 µs de volta ao nível do pulso ligado: o MUR860 conduz e a energia volta ao banco (o grampo previsto em 4.5) |
| Logo antes de religar | mergulho pequeno, ~−16 V |
| Dreno, de pico | 24 + 56 × 10/3 ≈ **211 V**, calculado pela bobina |
| Fonte, nota de 100 Hz a 50 %, arco longo sem apagar | 4,9 A médios (4,8 a 5,1); ~9,3 A (~223 W) durante a rajada |
| Fonte, em repouso | 0,25 A |
| Fonte, arco apagado | **9,2 A**; com o arco curto, bem menos que 4,9 A |

Leituras que **não** valem:

- **Indutância pelo multímetro:** 0,005 mH é o menor passo do aparelho (o seguinte é 0,010). Não há resolução para µH.
- **Capacitância do banco na placa:** 66 nF, e depois uma leitura oscilando entre nF e µF, mesmo sem o MOSFET. O MUR860 e o primário (com o banco de 470 µF atrás) ficam em paralelo e enganam o capacímetro. Fora da placa, cada capacitor do lote mede ~100 nF.

### 9.3 O que o modelo tira disso

- **Primário: 8 a 12 µH.** O ajuste da forma de onda com os 300 nF dá 8 a 10 µH, com ~3 µH de dispersão (`sim_ajuste_dispersao.py`). A energia por pulso, (V·t)²·f / 2L = 223 W, dá até 12,6 µH. Substitui os ~3 µH da seção 4.4, que eram suposição.
- **A oscilação rápida de 4.3 bate com a dispersão.** 2π√(3 µH × 300 nF) = 6,0 µs, perto dos 5,7 µs medidos; com o primário inteiro seriam 10 a 12 µs. É hipótese: o teste de 9.5 decide.
- **O que o modelo ainda erra:**
  - o mergulho sai com 5 a 6 µs (medido: 3,5);
  - o dreno fica 20 a 40 V abaixo do real;
  - o arco apagado puxa 0,5 A (medido: 9,2 A).

  Falta física. A candidata mais provável é a capacitância do secundário refletida no primário. Os números abaixo são tendência, não valor exato.
- **O núcleo está longe do joelho:** 0,13 a 0,18 T de pico no ponto medido, contra 0,30 a 0,35 T para saturar a ferrite.

### 9.4 Decisões

**Capacitor de dreno: 300 nF, também na V3.6** (`sim_mais_potencia.py`, parte B, com 200, 300 e 400 nF):

- **200 nF dá menos arco no mesmo dreno.** Com 8 µH: 343 W com o dreno a 230 V (18 µs), contra 395 W a 228 V com 300 nF (22 µs).
- **400 nF empata com 300 nF.** O mesmo pulso dá dreno mais baixo e arco menor; o mesmo arco pede pulso mais longo, com um pouco mais de corrente.
- **150 nF**, o valor que a V3.6 tinha, foi escolhido quando se supunha um primário de 20 µH. Com 8 a 10 µH, no pulso de hoje, ele sobe o dreno de 35 a 60 V por ~10 % a mais de arco.

Na placa final: 3 × 100 nF MKP e uma quarta posição vazia (C11), para os 400 nF se algum flyback encostar no limite antes do pulso desejado.

**Para mais arco, alongar o pulso no vale; não subir a frequência** (`sim_mais_potencia.py`, IRFP264N, 300 nF).

Subir a frequência com o pulso fixo em 15,68 µs:

1. Primeiro o MOSFET liga com a energia ainda voltando ao banco, e o arco cai (8 µH: de 254 W em 39,7 kHz para 87 W em 45,7 kHz).
2. Depois o MOSFET sai do vale e os 300 nF descarregam nele: 104 a 110 W de perda em 51,7 kHz.

O núcleo não passa de 0,14 T: subir a frequência não carrega mais o núcleo.

Alongando o pulso, com 300 nF e a frequência reajustada no vale. O vale aqui é o fim do grampo do MUR860: a frequência de mais arco entre as que ligam com o dreno abaixo de 10 V. Mais acima, o MOSFET liga ainda no grampo, com a corrente voltando ao banco, e o arco cai até 25 %. O arco fica aceso o tempo todo; na música a média é menor.

| Pulso | 8 µH: vale, arco / MOSFET / dreno | 10 µH: vale, arco / MOSFET / dreno |
|---|---|---|
| 15,7 µs | 40 kHz, 251 W / 24 W / 189 V | 39 kHz, 216 W / 17 W / 173 V |
| 18 µs | 38 kHz, 309 W / 34 W / 204 V | 39 kHz, 238 W / 20 W / 178 V |
| 20 µs | 37 kHz, 345 W / 40 W / 214 V | 39 kHz, 295 W / 28 W / 190 V |
| 22 µs | 35 kHz, 395 W / 52 W / 228 V | 36 kHz, 394 W / 47 W / 217 V |
| 24 µs | 33 kHz, 446 W / 67 W / 244 V | 34 kHz, 451 W / 62 W / 234 V |

- **O limite é o dreno do IRFP264N.** O modelo fica abaixo da placa: 20 V com o ajuste de 8 µH e 38 V com o de 10 µH (no ponto medido, 189 e 173 V contra os 211 V da bancada). Corrigido, 20 µs dá ~230 V e 22 µs, ~250 V. Na bobina de realimentação de 3 espiras, 230 V aparecem como −62 V e 250 V como **−68 V**: dá para acompanhar no osciloscópio.
- **O flyback esquenta mais rápido que o arco cresce.** De 15,7 para 20 µs:
  - o arco sobe ×1,37;
  - o cobre do primário (I_rms²), ×1,5 a ×1,6;
  - o núcleo, ×1,5 a ×1,6 (estimativa por f^1,3 × B^2,5).

  Para 22 µs: arco ×1,6 a ×1,8, cobre ×2,0 a ×2,4, núcleo ×1,9 a ×2,2.
- **Saturar não dá mais arco.** Passado o joelho, a energia guardada para de crescer e a corrente a mais vai para o MOSFET. O ponto bom é logo abaixo do joelho, e o núcleo ainda está longe dele.

**Ponto de trabalho: ~20 µs no vale, de 37 a 39 kHz.** Dá +37 % de arco, com o dreno a ~230 V e o MOSFET a 28–40 W com o arco aceso direto (17–24 W hoje, com o MOSFET a ~40 °C na bancada). O flyback esquenta ~1,5 vez o de hoje. Quanto disso o flyback aguenta numa música longa só a bancada diz (9.5, item 4).

**Espiras: ficam 10** (`sim_espiras36.py`). Para o mesmo arco, o cobre do primário e o núcleo ficam a ±15 % entre 6 e 12 espiras: trocar espiras não resolve o aquecimento. Menos espiras alcançam mais arco, com mais corrente no MOSFET. Foi simulado com o núcleo suposto de 20 µH; falta refazer com o L medido.

**Gate: 10 Ω em paralelo com o 1N4148** (`sim_gate.py`):

- 0, 10 e 22 Ω dão a mesma perda no MOSFET no vale.
- Com 0 Ω, o Vgs vai a 14,5 V e o BC337 a ~1,2 A de pico.
- O toque no desligamento (até 1,9 V) não depende do resistor, porque passa pelo diodo. O que pesa é o laço do gate: 150 nH dão −4 a −6 V. Por isso o MOSFET fica perto do totem pole.

**Envelope no firmware, não no pino 5** (`sim_envelope.py`). Pelo pino 5 do U13 o volume não é monotônico, o vale sai do lugar e, em volume baixo, o MOSFET esquenta mais. O firmware muda a fração aberta da nota, e o volume segue sen(π·D), que é o que o gerador de tom já faz.

**Sem TVS na V3.6.** Ver a atualização em 3.9.

**Temporização da V3.6** (`v36_ajuste.py`, `sim_v36.py`):

| Bloco | Valores | Faixa |
|---|---|---|
| U12, frequência | R14 4k7 + PR4 10k multivoltas + R13 1k, C21 4n7 | 18 a 45 kHz |
| U13, largura | R15 3k3 + PR5 10k multivoltas, C24 1 nF em paralelo com C28 470 pF | 5,3 a 21,5 µs (calculado) |

Só com o C24 a faixa era de 3,7 a 14,7 µs (simulada), abaixo até do ponto da bancada (15,68 µs). Com o C28, o topo vai a 21,5 µs, perto de onde o dreno chega aos 250 V: o teto em hardware fica logo acima do ponto de trabalho. Com 390 pF no C28, o teto fica em 20,3 µs. Os 20 µs ficam com o PR5 em ~9k.

A entrada da V3.6 é 6N136 + BC547 no RESET do U13, com lógica direta: GPIO alto libera o arco. O BC547 basta, porque quem limita a velocidade é o 6N136.

### 9.5 Pendências

1. **Para onde vão os 9,2 A do arco apagado.** Fazer corridas de ~10 s olhando a bobina de realimentação:
   - fundo achatado perto de −68 V ou além: é avalanche, e a energia vai para o MOSFET, que esquenta rápido;
   - sem fundo achatado e com o MOSFET frio: a energia vai para o próprio flyback (isolamento, diodos internos, corona). É candidata ao aquecimento nas músicas longas.
2. **Distância dos eletrodos no ponto de 4,9 A.** O Franzoli recomenda no máximo 50 mm, pelo isolamento.
3. **Período da oscilação com 300 nF e com 200 nF** (T₁ e T₂). L = (T₁² − T₂²) / (4π² × 100 nF), descontada a capacitância em paralelo com o banco. Perto de 3 µH, a oscilação rápida é a dispersão (9.3); perto de 8 a 12 µH, é o primário inteiro.
4. **Escada de potência.** Alongar o pulso de 1 em 1 µs e reajustar o vale a cada passo; a frequência cai alguns kHz (de ~40 para ~37 kHz em 20 µs). Em cada passo, tocar 30 a 60 s, medir a temperatura do flyback e do MOSFET e olhar o fundo do mergulho na bobina.
5. **Refazer espiras e potência com o L medido**, e pôr no modelo a capacitância do secundário se o teste 3 apontar para ela.
