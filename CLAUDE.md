# CLAUDE.md

Contexto do projeto para quem for continuar o desenvolvimento.

## O que é

Três páginas web que geram áudio para alimentar **alto-falantes de plasma** — arcos elétricos de transformadores flyback que reproduzem som. O hardware é um projeto de eletrônica de potência separado; estas páginas são apenas a fonte de áudio.

- `index.html` — abre MIDI ou Guitar Pro (do acervo ou do aparelho), roteia cada faixa de instrumento para o canal esquerdo ou direito, e sintetiza onda quadrada.
- `stems.html` — carrega dois arquivos de áudio já separados (stems) e toca um em cada canal.
- `tom.html` — gerador de tom contínuo, um por canal: frequência livre no slider, forma de onda à escolha e varredura.

As três são **arquivo único, sem build, sem dependência de pacote**. Fontes do Google Fonts via CDN; o leitor de Guitar Pro vem do jsDelivr, carregado só quando um arquivo que não é MIDI é aberto. Devem funcionar abertas direto do disco e servidas pelo GitHub Pages.

Arquivos de apoio, fora das páginas:

| Arquivo | Papel |
|---|---|
| `sw.js` | Service worker: uso sem internet. Rede primeiro para o próprio site, cópia guardada primeiro para CDN |
| `manifest.webmanifest`, `icones/` | Instalação na tela inicial do celular |
| `musicas/` | Acervo. Tudo que estiver aqui aparece no site |
| `tools/gerar_acervo.py` | Gera `musicas/index.json`, a lista do acervo, juntando `creditos.json` e `pastas.txt`. Só biblioteca padrão |
| `tools/compor_rock.py` | Compõe os arranjos de `musicas/exemplos` numa notação de texto própria, com configuração pronta para cada um |
| `tools/baixar_mutopia.py` | Baixa os MIDIs do Mutopia Project para `musicas/classicos`, com crédito e licença de cada um |
| `tools/curar_acervo.py` | Enxuga `classicos` e o rearruma em `<região>/<compositor>/`. Lê cada MIDI e mede o aproveitamento em dois canais monofônicos |
| `tools/baixar_bandas.py` | Baixa transcrições de midiworld, zeppelinmidi, maidenmidi, do acervo Lakh via rawl.rocks e do folk russo do FreeSheetMusic |
| `tools/organizar_bandas.py` | Identifica, tira repetidas e arruma `musicas/bandas` por artista, medindo o quanto cada música é conhecida (Wikipedia e ListenBrainz). Com `--plano` serve a acervo sem artista, como o folk russo |
| `tools/popularidade.json` | O que as duas APIs responderam, guardado. Faz as rodadas seguintes não precisarem de internet e darem o mesmo resultado |
| `USO-EDUCACIONAL.md` | Finalidade do acervo, atribuição e canal de remoção. É o documento que sustenta a pasta `bandas` |
| `tools/servir.py` | Servidor local para teste, inclusive pelo celular na mesma rede |
| `tools/publicar.ps1`, `tools/publicar.cmd` | Cria o repositório, envia e liga o GitHub Pages via GitHub CLI |
| `.github/workflows/pages.yml` | A cada push na `main`: gera o índice do acervo e publica |

## A restrição que define tudo

Cada flyback é **monofônico**. O arco produz uma nota por vez, sempre em timbre de onda quadrada, sem envelope, sem dinâmica de amplitude perceptível.

Consequências que já estão implementadas e não devem ser revertidas:

- Cada canal de saída toca uma nota por vez. Acordes são reduzidos a uma nota (mais aguda ou mais grave, à escolha do usuário) por varredura cronológica do conjunto de notas ativas.
- A síntese é `OscillatorNode` com `type = 'square'`, não senoide. O comparador LM311 do hardware vai quadratear o sinal de qualquer jeito; sintetizar quadrada já deixa o preview fiel.
- Faixas de percussão são detectadas (canal 10 do MIDI ou nome) e ficam fora dos presets automáticos, porque percussão não tem altura definida.
- Separação estéreo é **dura**, via `ChannelMergerNode`, não `StereoPannerNode`. Cada lado vai para um flyback fisicamente distinto e não pode haver vazamento. Vale também para o WAV exportado: o teste confere que o canal sem faixa sai com amostras exatamente zero.

Hoje são 2 canais (esquerdo e direito). O projeto de hardware prevê 6 canais no futuro, acionados por ESP32 via serial. A estrutura interna já está no formato certo para isso: `ch[i].segs` é uma lista de segmentos monofônicos `{start, end, n, f}`, que é exatamente o que o firmware consome pela saída serial.

## Estado atual

### index.html — player MIDI

Parser de Standard MIDI File escrito à mão, sem biblioteca. Suporta formato 0 e 1, running status, eventos meta de tempo e nome de faixa, arquivo truncado (aproveita o que leu) e RIFF MIDI (procura `MThd` no início). Não suporta divisão SMPTE (lança erro).

Faixas: cada MTrk é separado por canal, então um formato 0 com quatro instrumentos vira quatro faixas. Sem nome de faixa, o nome vem do programa General MIDI (`gm: true`, e aí a detecção de bateria por nome é ignorada, para "Synth Drum" num canal melódico não sumir). Nomes repetidos ganham sufixo numérico, porque a configuração casa faixas pelo nome.

Guitar Pro (3 a 8, `.gpx`, `.gp`) e MusicXML: `scoreTracks()` carrega o AlphaTab (`@coderline/alphatab@1.8.4`, UMD), gera um SMF formato 1 com `MidiFileGenerator` e passa para o mesmo parser com `porCanal = false`. O AlphaTab resolve repetições, ligaduras, quiálteras e andamento. Cada MTrk corresponde à faixa de mesmo índice na partitura (`t.mtrk`), de onde vêm os nomes. O canal secundário que o AlphaTab usa para bends fica dentro da mesma faixa.

Fluxo: `openBuffer()` → `parseMidi()` ou `scoreTracks()` → configuração inicial → `buildSegs(canal)` monta a linha monofônica → `scheduleVoice()` agenda no Web Audio com `setValueAtTime` e rampas de 4 ms para evitar cliques. A mesma `scheduleVoice()` serve para tocar ao vivo e para o `OfflineAudioContext` do WAV.

Presets de roteamento implementados:

| Preset | Critério |
|---|---|
| Baixo e melodia | faixa de nota média mais grave à esquerda, mais aguda à direita |
| Guitarras somadas | faixas com nome de guitarra somadas à direita, baixo à esquerda |
| Principal e acompanhamento | faixa com mais notas sozinha à direita, resto somado à esquerda |
| Melodia inteira, resto sem atropelo | a melodia sai inteira à direita; à esquerda, a base e o que couber nas brechas dela |
| Grave e agudo | ordena por nota média e divide ao meio |

**O preset "Melodia inteira, resto sem atropelo".** Era força bruta sobre 3^n atribuições minimizando sobreposição, o que tratava todas as faixas por igual e com frequência partia a melodia ao meio. Agora é dirigido:

1. `scoreVoz()` escolhe a faixa principal, de preferência a voz. Pontua monofonia (`monofonia()`, fração de notas que entram sem nada mais soando na faixa — linha de canto fica perto de 1, naipe de acordes perto de 0), altura média, cobertura do tempo, mais um bônus para nome de voz ou melodia (`RX_VOZ`, que pega tanto nome de faixa quanto programa General MIDI: Choir Aahs, Voice Oohs, Lead 1…) e uma penalidade para baixo.
2. Essa faixa vai **sozinha** para a direita, com prioridade 3, e sai inteira.
3. À esquerda vai a faixa de maior cobertura como base, com prioridade 2.
4. As demais entram à esquerda com prioridade 1, e só se trouxerem brecha de verdade: pelo menos 6% da duração da música em tempo que a base não ocupa, e pelo menos 30% do material próprio.

Quem decide no choque é a prioridade, não a altura: `buildSegs()` monta a chave de cada nota como `(altura << 4) | prioridade` e, no instante em que mais de uma nota está soando, escolhe primeiro pela prioridade e só depois pela altura. Assim a base nunca perde uma nota para quem está preenchendo as brechas — medido sobre os MIDIs de `exemplos`, `bandas` e uma amostra de `classicos`, a linha da base é idêntica tocando sozinha ou dentro do canal.

Com todas as faixas em prioridade 0 — que é como os outros presets ficam — `buildSegs()` se comporta exatamente como antes. A prioridade vai junto na configuração salva, como campo opcional `prioridade` de cada faixa.

### Achar a linha de canto

Este é o ponto que mais muda como a música soa no arco, e levou duas correções.

**Polifonia, não monofonia.** `scoreVoz()` media "uma voz só" contando quantas notas entravam enquanto outra ainda soava. Está errado para este fim: linha gravada em *legato* — que é como se grava canto — tem cada nota começando antes de a anterior soltar, e pontuava quase zero. Na transcrição de *Back In Black* a faixa literalmente chamada `vocal` tirava **0,21**, e o preset mandava a guitarra solo (465 notas, 38% do tempo) para o canal principal no lugar da voz (1.184 notas). A medida certa é `polifonia()`: quantas notas soam ao mesmo tempo, em média, enquanto a faixa soa. 1,0 é uma linha; 3,0 é naipe de acordes.

**Cobertura é porteira, não bônus.** Com a cobertura valendo pouco, um `choir` de 39 notas em 4% da música ganhava do resto e o detector dizia que havia voz onde não há. Agora abaixo de `COBRE_MIN` (12% do tempo) a faixa nem concorre.

Outras armadilhas que a pontuação trata, todas encontradas em arquivo real:

- **`lead` sozinho não é voz.** "lead guitar" é o nome mais comum de faixa de guitarra solista; dar-lhe bônus de voz fazia o detector preferir a guitarra ao vocal. `RX_CANTO` exige `lead voc`/`lead vox`, e `RX_INSTRUM` desconta quem se anuncia como instrumento.
- **Vocal de apoio não é a melodia.** `voc -bu`, `bck vox`, `choir` são harmonia; `RX_APOIO` reduz o bônus de 3,0 para 0,4.
- **Baixo sem nome.** No acervo Lakh a faixa quase sempre se chama "Track 7", então o nome não acha o baixo — entram os programas 32-39 do General MIDI e o registro (média abaixo de F2 não é voz humana).

`achar_lead()` devolve `(faixa, nota)` e `veredito_lead()` reduz a `sim` / `talvez` / `nao` (limiares 5,0 e 3,8). Os extremos são confiáveis — *Stairway to Heaven* 8,0, *Highway to Hell* 2,3 —, e o meio é honestamente incerto, por isso são três respostas e não duas. A mesma pontuação vive em `tools/curar_acervo.py` e em `index.html`: se mexer numa, mexa na outra.

**Para que serve na prática.** O acervo Lakh costuma ter três ou quatro transcrições da mesma música e normalmente só uma traz o vocal, então `qualidade()` em `organizar_bandas.py` dá à linha de canto quase metade do peso ao escolher qual versão fica. E o veredito vai para o `creditos.json` no campo `vocal`, de onde o site tira o marcador "· vocal" em cada linha e o botão **só com vocal** — que é a única forma de responder "quais das minhas 718 têm canto?" sem ouvir uma a uma.

Métricas mostradas ao usuário: **toca X% das notas** (fração das notas atribuídas que realmente soa) e **ativo X% do tempo**. Servem para julgar rapidamente se uma música cabe em dois canais.

Linha do tempo abaixo do osciloscópio: os segmentos de cada canal, altura relativa à extensão do canal. Tocar ou arrastar nela muda a posição.

### Acervo

`musicas/index.json` não é versionado: o workflow gera a cada publicação, e `tools/servir.py` gera ao servir. Se o índice faltar (Pages publicado a partir de branch, por exemplo), a página lista a pasta pela API de árvores do GitHub, deduzindo usuário e repositório de `usuario.github.io/repositorio`.

O botão "Enviar música para o acervo" aponta para `github.com/USUARIO/REPO/upload/main/musicas`: é assim que se adiciona música pelo celular, sem ferramenta nenhuma. O push dispara o workflow.

Abrir uma música do acervo troca o endereço para `?m=caminho`; esse endereço reabre a música.

O acervo tem 1.363 músicas em quatro pastas de primeiro nível:

| Pasta | Quantas | O que é |
|---|---|---|
| `bandas` | 718 | transcrições de fã, **uma pasta por artista** (110 deles) |
| `classicos` | 590 | Mutopia, em `<região>/<compositor>/` |
| `folk russo` | 45 | tradicional e soviético, pasta plana |
| `exemplos` | 10 | arranjos do projeto para dois flybacks, mais casos de teste |

Eram 4.867 só em `classicos`, todos numa pasta por compositor, o que tornava o filtro inútil: a lista era um balaio só. `tools/curar_acervo.py` resolveu as duas coisas ao mesmo tempo.

**Por que artista, e não nível de popularidade.** As bandas já estiveram em `mais ouvidas` / `conhecidas` / `para fãs`, e foi pior: 554 caíam no último nível, que virava uma parede, e não havia como pedir "me mostra o AC/DC". Pior ainda, o nível de uma música **muda quando o número de escutas muda** — ela trocaria de pasta sozinha, e o link dela (`?m=caminho`) quebraria. Artista é coisa estável. A popularidade continua medida e gravada em `posicao`, e virou filtro na interface.

**A descoberta que guia a curadoria:** o sufixo " - NN" do título do Mutopia **não é número de movimento**. Em `Air (BWV 1068)` os cinco arquivos têm a mesma duração e são a partitura inteira (4 faixas, 516 notas) mais cada parte de instrumento sozinha; já em `French Suite no. 3` os 14 arquivos são 7 movimentos, cada um gravado duas vezes. O que separa um caso do outro é a **duração**. Por isso a ferramenta agrupa pela chave `mutopia` do `creditos.json`, separa movimentos pela duração (com folga de 1,5 s ou 2%), e de cada movimento fica com o arquivo de mais faixas — a partitura inteira, a única que serve para repartir entre dois canais. Só isso tirou 1.722 arquivos.

### Navegação do acervo

Um seletor só, com todas as pastas numa lista, não dá conta de 1.363 músicas. São **duas peças**:

- `montarAcervos()` desenha um **botão por pasta de primeiro nível**, mais "tudo". Escolher um deles define `acervo`.
- `montarFiltro()` desenha o **seletor do que há dentro** do acervo escolhido. O grupo é sempre a **pasta mais funda**, e a de cima, quando existe, vira cabeçalho de `<optgroup>`: em `bandas` saem 107 artistas numa lista rasa, em `classicos` saem 139 compositores agrupados pelas 9 regiões. Pasta plana (`folk russo`, `exemplos`) não tem o que desdobrar, e o seletor se esconde.

`prefixo()` devolve o que está de fato selecionado — o grupo quando há um, senão o acervo inteiro — e é o que `filtrar()` e `renderLib()` usam. O botão **só as mais ouvidas** filtra por `posicao <= TOPO` (60) e só aparece se o acervo carregado tiver esse campo.

A busca cobre título, pasta, autor, artista, instrumentos e estilo. Continuam valendo: acervo lembrado no aparelho, no máximo `LIMITE` (200) botões por vez, "Sortear uma" e "Guardar para usar sem internet" dentro do filtro atual.

`creditos.json` numa pasta dá os campos de `CAMPOS` em `gerar_acervo.py` — `autor`, `artista`, `instrumentos`, `estilo`, `licenca`, `credito`, `transcricao`, `popularidade`, `posicao` e `fonte` — dos arquivos dela; o gerador copia para o índice e o site mostra o crédito abaixo de "Faixas encontradas". É o que cumpre a atribuição pedida pelas licenças CC BY e CC BY-SA do Mutopia, e é também onde a pasta `bandas` declara quem compôs e quem transcreveu.

### Bandas, e a mudança de política

**A regra anterior era não aceitar transcrição de banda no repositório.** O dono do projeto reviu isso e decidiu mantê-las, com atribuição ao artista e ao transcritor e uma declaração de finalidade educacional na raiz. `USO-EDUCACIONAL.md` é esse documento: explica a finalidade, diz com todas as letras que **atribuir não substitui licença** (a Lei 9.610/98 não tem cláusula geral de *fair use*; o art. 46 cobre trecho curto para uso privado de quem copia), e abre um canal de remoção sem burocracia.

Quem for mexer aqui: essa é uma decisão do dono do projeto, registrada, não um descuido. Não reverta sozinho — e, ao acrescentar música nova, preencha a atribuição.

### Folk russo

`musicas/folk russo` veio do acervo de folk do FreeSheetMusic, que o `baixar_bandas.py` varre como fonte `folkrusso`. Duas coisas que ele resolve e que não são óbvias:

- **A mesma canção aparece transliterada de vários jeitos.** "two guitars", "dve gitari" e "dwje gitary" são a mesma peça, assim como "moscow evenings", "pod moskovniye vechera", "padmoskownye vjetsjera" e "midnight in moscow". A tabela `FOLK_RUSSO` mapeia nome de arquivo para o título canônico, e sem ela o acervo ficaria com a mesma música três vezes, sob nomes que ninguém procura. Das 71 entradas da página saem 45 peças.
- **Nem tudo é tradicional.** A tabela `AUTORIA_CONHECIDA` em `organizar_bandas.py` dá autoria e situação de direito autoral peça a peça: Kalinka é de Ivan Larionov (1860) e está em domínio público, mas Katyusha é de Matvey Blanter (1938) e **continua protegida**, como Podmoskovnye Vechera (1955) e Pust Vsegda Budet Solntse (1962). Chamar tudo de "tradicional, domínio público" seria cômodo e errado.

A pasta é plana e roda com `--plano`, que também desliga a medição de popularidade: ordenar Kalinka contra Troika por visita de artigo não diz nada e gastaria centenas de chamadas para produzir um número sem sentido.

`tools/organizar_bandas.py` ordena a pasta pelo quanto a música é conhecida, que é o que importa para demonstrar o aparelho — arco elétrico tocando algo que ninguém reconhece não demonstra nada. Duas fontes abertas:

- **Wikipedia**, visitas ao artigo da música nos últimos doze meses. É a fonte principal porque não pede chave e cobre todas as bandas por igual. O casamento do artigo é **estrito** de propósito: aceitar o primeiro resultado da busca dava número errado — "Revolution (Mother Earth)" pegava o artigo *Revolution*, com 1,4 milhão de visitas, e quatro músicas do Scorpions pegavam todas a mesma página. Só serve o artigo cujo nome é o da música, descontado o desambiguador "(… song)", e música que se chama como a banda ("Black Sabbath") é recusada, porque o artigo achado seria o da banda.
- **ListenBrainz**, total de escutas por gravação (dados CC0). Mede audição de verdade e por isso pesa mais (`PESO`), mas desde 2025 o endpoint de popularidade exige token — sem ele, a ordem sai só pela Wikipedia, o que já funciona. **Não contorne isso**: o serviço pede token por causa de scraping, e o jeito certo é pegar um de graça em listenbrainz.org/settings.

As duas escalas são incomparáveis (milhões de escutas contra dezenas de milhares de visitas), então cada uma vira **percentil dentro da própria fonte** antes de se combinarem.

A ferramenta classifica sempre o acervo inteiro — os arquivos novos da pasta de entrada **mais** os que já estão arrumados —, porque ordenar só os novos entre si jogava uma faixa qualquer para o topo só por ser a única da rodada. E ela **mescla** o `creditos.json` existente em vez de sobrescrever, preservando campo preenchido à mão (nome do transcritor, por exemplo).

**De onde veio cada arquivo.** `baixar_bandas.py` grava `_origem.json` na pasta de entrada, com o endereço de origem de cada arquivo; `organizar_bandas.py` lê esse manifesto e copia o endereço para o campo `fonte` do `creditos.json`, além de citar o site no `credito` e em `transcricao`. Sem isso a atribuição morreria junto com a pasta de entrada, que é apagada quando tudo dela é arrumado — e a atribuição é justamente o que sustenta a pasta. Música que entrou à mão, sem passar pelo baixador, fica sem `fonte`, o que é honesto: não se sabe de onde veio.

### Rock e metal (`tools/compor_rock.py`)

Cada música tem Bateria, Baixo, Guitarra base, Melodia e Guitarra solo, às vezes Guitarra solo 2, Órgão, Sintetizador ou outras. A melodia e o solo nunca soam ao mesmo tempo, então somados no canal direito tocam 100% das notas; a guitarra base (e a segunda guitarra, nas partes de guitarras gêmeas, com "acorde: agudo") vai no esquerdo. O `.json` de cada uma já traz esse roteamento. Os solos saem de `improviso()`, com semente fixa: rodar o script de novo gera os mesmos arquivos. A notação (`E2*m/8`, `|` conferindo a soma de cada compasso) está descrita no começo do script.

### Configuração por música

Formato (o mesmo no `localStorage` e no `.json` ao lado da música):

```json
{ "versao": 1,
  "faixas": [{ "nome": "Baixo", "canal": "esquerdo" }],
  "canais": [{ "ganho": 70, "passaBaixa": 20000, "oitava": 1, "acorde": "agudo" }, { … }] }
```

`canal` é `desligada`, `esquerdo`, `direito` ou `ambos`. Faixas casam pelo nome; se nenhuma casar, a configuração é ignorada. Prioridade ao abrir: ajuste salvo no aparelho, depois `.json` do acervo, depois o preset baixo e melodia. Só ação do usuário grava no aparelho; "Restaurar" apaga o ajuste local.

### Exportação WAV

`OfflineAudioContext` estéreo a 44,1 kHz, PCM 16 bits. Ganho acima de 100% satura no arquivo como saturaria na saída ao vivo. No celular o arquivo sai por um link (toque novo, que o iOS exige) e, quando o navegador suporta, pelo compartilhamento do sistema.

### Saída serial

Web Serial, texto por linha, eventos com carimbo em ms enviados 100 ms antes. Contrato completo em `docs/protocolo-serial.md`. Testado com porta simulada; ainda não há firmware.

### tom.html — gerador de tom

Dois osciladores, um por canal, criados uma vez e deixados ligados: quem dá e tira voz é o ganho, com rampa de 8 ms, e assim não há clique. Separação dura pelo mesmo `ChannelMergerNode`. A frequência vai por `setTargetAtTime` com constante de 6 ms, que é o que deixa arrastar o slider sem degrau e sem atraso perceptível.

Slider logarítmico de 20 Hz a 20 kHz em 2.000 passos (`freqOf`/`sliderOf`), campo numérico, ×½ e ×2, passo de 1 Hz e seletor de nota de E0 a B9. Formas: quadrada (padrão, que é o timbre real do arco), senoide, triangular e dente de serra. Mais varredura logarítmica entre dois limites, com ida e volta, e intervalos prontos entre os dois canais — uníssono, oitava, quinta, terça e batimento de 1 Hz, que é como se ouve se os dois arcos estão casados.

O traço do osciloscópio desenha uma janela de três ciclos da frequência atual, em vez do buffer inteiro: sem isso a forma vira um borrão em frequência alta. O desenho para quando nada toca.

Estado no endereço (`?f=…&o=…&g=…&l=…&v=…`) e no `localStorage`. A gravação é adiada 400 ms, porque a varredura mexe na frequência a cada quadro e gravar a cada quadro seria absurdo.

### stems.html — player de áudio

Carrega dois arquivos de áudio, converte para mono, e roteia um para cada canal. Ganho, passa-baixa e mudo por canal. Exporta WAV com esses ajustes aplicados. Mais simples, sem lógica de notas.

### Celular

Barra de reprodução fixa no rodapé, alvos de toque de 40 px ou mais (`pointer: coarse`), campos com 16 px para o iOS não dar zoom, sem rolagem horizontal a 360 px. `navigator.audioSession.type = 'playback'` para o iOS tocar com a chave de silencioso ligada. Wake Lock enquanto toca, porque tela apagada suspende o áudio. O desenho do osciloscópio para quando nada toca, para poupar bateria.

## Convenções

- **Interface em português do Brasil.** Todos os rótulos, mensagens e comentários voltados ao usuário. Nomes de instrumento General MIDI ficam em inglês, como aparecem nos programas de música.
- **Estética de osciloscópio.** Fundo azul profundo, grade pontilhada, traço 1 amarelo-fósforo e traço 2 ciano. É referência ao Tektronix TDS 1012C que o autor usa na bancada. Amarelo é sempre o canal esquerdo, ciano sempre o direito, em toda a interface — por isso destaques que não são de canal (música atual, botão ligado) usam o painel azul, não essas cores.
- Tipografia IBM Plex Sans para interface, IBM Plex Mono para leituras numéricas.
- Sem caixa-alta decorativa, sem sombras em cartão, sem ícones genéricos.
- `box-sizing: border-box` aplicado direto em `*`, não por herança: o conteúdo de `<details>` não herda pela árvore interna do navegador, e com `inherit` os botões do acervo estouravam a largura.

## O que está aberto

- **Seis canais.** A interface e o roteamento são de dois canais; o protocolo serial já comporta seis.
- **Firmware** que consuma o protocolo serial.
- **Receber arquivo compartilhado** de outro aplicativo no celular (Web Share Target). Hoje se abre pelo seletor de arquivos ou pelo acervo.

## Contexto de hardware

`docs/hardware-decisoes.md` tem o registro completo das decisões do driver de flyback, incluindo por que a modulação é analógica, por que cada canal é monofônico, e as medições de bancada. A seção 3.16 importa para o firmware da saída serial.

## Restrições de manutenção

- Não introduzir bundler, framework ou gerenciador de pacotes. O valor destes arquivos está em abrir e funcionar.
- Não usar `localStorage` sem `try/catch` e sem funcionar quando vazio (`store` em `index.html`).
- Qualquer biblioteca externa só via `<script>` de CDN, com versão fixada.
- Arquivo novo que o site precise servir tem de entrar no passo "Montar o site" do workflow e, se for do núcleo, em `BASE` no `sw.js`. Mudou `sw.js` de forma incompatível: troque o nome de `SITE`.
- Testar com MIDI real antes de considerar pronto: um arquivo de música de videogame (3 a 4 faixas) e um arranjo de banda (6 a 8 faixas) cobrem os dois extremos. `musicas/exemplos` tem os dois casos, um Guitar Pro e os arranjos do projeto, que cobrem 6/8 e 3/8, andamento acelerando e ritardando; `musicas/bandas` tem arranjo de banda de verdade, com 8 a 16 faixas.
- Ferramenta que mexe no acervo **não altera nada sem `--aplicar`** (ou `--baixar`, no download). Sem a opção, só imprime o que faria. Mantenha assim.
- **Pasta no Windows vem com o atributo ReadOnly**, e aí `Path.rmdir()` falha com "Acesso negado" mesmo estando vazia. `remover_vazias()` em `curar_acervo.py` tira o atributo e tenta de novo, e engole a falha se ainda assim não for. Use essa função em vez de `rmdir()` direto. Pelo mesmo motivo, **grave o `creditos.json` antes da faxina de pastas**: é ele que guarda a atribuição exigida pelas licenças, e já se perdeu uma vez porque uma pasta vazia resistiu a sumir e abortou o resto.
- Rodar script com `2>/dev/null | tail` esconde o traceback e devolve o código de saída do `tail`, que é sempre 0. Foi assim que a falha acima passou despercebida.
