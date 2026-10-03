# CLAUDE.md

Contexto do projeto para quem for continuar o desenvolvimento.

## O que é

Duas páginas web que geram áudio para alimentar **alto-falantes de plasma** — arcos elétricos de transformadores flyback que reproduzem som. O hardware é um projeto de eletrônica de potência separado; estas páginas são apenas a fonte de áudio.

- `index.html` — abre MIDI ou Guitar Pro (do acervo ou do computador), roteia cada faixa de instrumento para um flyback e sintetiza onda quadrada. Dois flybacks pelo áudio estéreo, ou de 1 a 6 por um ESP32 na serial.
- `tom.html` — gerador de tom contínuo, um por canal: frequência livre no slider, forma de onda à escolha e varredura.

As duas são **arquivo único, sem build, sem dependência de pacote**. Fontes do Google Fonts via CDN; o leitor de Guitar Pro vem do jsDelivr, carregado só quando um arquivo que não é MIDI é aberto. Devem funcionar abertas direto do disco e servidas pelo GitHub Pages.

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
| `tools/transcrever.py` | Gera MIDI a partir de uma gravação: separa os stems e transcreve cada um. **A única ferramenta que precisa de pacotes além da biblioteca padrão** (torch, torchaudio, librosa, basic-pitch) — é opcional, e nada no site depende dela |
| `USO-EDUCACIONAL.md` | Finalidade do acervo, atribuição e canal de remoção. É o documento que sustenta a pasta `bandas` |
| `tools/servir.py` | Servidor local para teste, inclusive pelo celular na mesma rede |
| `tools/testar_site.py` | Abre o `index.html` num Chrome de verdade (Playwright) e exercita os dois modos de saída, o roteamento, o WAV e a serial com porta simulada. Opcional; precisa de `pip install playwright` |
| `tools/publicar.ps1`, `tools/publicar.cmd` | Cria o repositório, envia e liga o GitHub Pages via GitHub CLI |
| `.github/workflows/pages.yml` | A cada push na `main`: gera o índice do acervo e publica |

## A restrição que define tudo

Cada flyback é **monofônico**. O arco produz uma nota por vez, sempre em timbre de onda quadrada, sem envelope, sem dinâmica de amplitude perceptível.

Consequências que já estão implementadas e não devem ser revertidas:

- Cada canal de saída toca uma nota por vez. Acordes são reduzidos a uma nota (mais aguda ou mais grave, à escolha do usuário) por varredura cronológica do conjunto de notas ativas.
- A síntese é `OscillatorNode` com `type = 'square'`, não senoide. O comparador LM311 do hardware vai quadratear o sinal de qualquer jeito; sintetizar quadrada já deixa o preview fiel.
- Faixas de percussão são detectadas (canal 10 do MIDI ou nome) e ficam fora dos presets automáticos, porque percussão não tem altura definida.
- Separação estéreo é **dura**, via `ChannelMergerNode`, não `StereoPannerNode`. Cada lado vai para um flyback fisicamente distinto e não pode haver vazamento. Vale também para o WAV exportado: o teste confere que o canal sem faixa sai com amostras exatamente zero.

Há dois modos de saída, e a separação dura vale para o que aciona flyback:

- **Estéreo · P2** — 2 canais pelo áudio do computador, esquerdo e direito, cada um num flyback. É como o site sempre foi.
- **ESP32 · serial** — de 1 a 6 canais, um por pino de um ESP32. Os flybacks são acionados pela serial; o áudio do computador vira **monitor**, com os canais somados nos dois lados (e com o ganho dividido por √N para a soma não saturar). O monitor não aciona flyback nenhum, então a soma ali não fere a regra.

`ch[i].segs` é uma lista de segmentos monofônicos `{start, end, n, f}` por canal, e é a mesma coisa que alimenta a síntese, o WAV e a serial.

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

No modo ESP os presets são outros, porque os de cima são pensados para dois lados:

| Preset | Critério |
|---|---|
| Um instrumento por flyback | o "sem atropelo" levado a N canais: a linha de canto (`scoreVoz()`) sozinha no canal 1, o baixo no 2, as faixas de maior ocupação uma por canal; o que sobra entra com prioridade 1 no canal onde mais traz brecha nova, pelas mesmas regras de 6% e 30% |
| Grave para agudo | ordena por nota média e divide em N grupos |

"Um por flyback" é o padrão do modo ESP e foi feito para a saída do MuScriptor, que já vem com voz, guitarra, piano e baixo separados: em Borboletas sai voz no 1, baixo no 2, violão no 3, pad no 4, piano no 5 e bateria desligada.

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
{ "versao": 2, "saida": "estereo",
  "faixas": [{ "nome": "Baixo", "canal": "esquerdo", "saidas": [1] }],
  "canais": [{ "ganho": 70, "passaBaixa": 20000, "oitava": 1, "acorde": "agudo" }, { … }] }
```

Internamente o roteamento de cada faixa é uma **máscara de bits**, um bit por canal (`assign[k]`): no estéreo 0, 1, 2 e 3 são exatamente o desligada, esquerdo, direito e ambos de antes; no ESP qualquer combinação dos seis vale, e uma faixa pode ir para mais de um flyback.

`saidas` é a lista de canais, contando de 1. `canal` (`desligada`, `esquerdo`, `direito` ou `ambos`) continua sendo escrito no modo estéreo, e é lido quando `saidas` falta — é assim que os `.json` da versão 1 que estão no acervo continuam valendo. Faixas casam pelo nome; se nenhuma casar, a configuração é ignorada.

**Uma configuração por modo**, em chaves separadas: `cfg:` para o estéreo (a de sempre) e `cfgesp:` para o ESP. O roteamento para dois flybacks no P2 e para seis no ESP não têm nada a ver um com o outro, e trocar de modo não pode apagar o ajuste do outro. Prioridade ao abrir: ajuste salvo no navegador para o modo atual; depois o `.json` do acervo, que descreve dois canais e por isso só vale no estéreo ou no ESP com dois flybacks; depois o preset padrão do modo. Mudar o número de flybacks redistribui pelo preset se a música não tem ajuste salvo, e só corta as rotas para canais que deixaram de existir se tem.

Silenciar e solo (M e S em cada canal) são de sessão, como num mixer: não vão para a configuração e não afetam o WAV.

### Exportação WAV

`OfflineAudioContext` a 44,1 kHz, PCM 16 bits, **um canal do arquivo por flyback**: estéreo no modo P2, N canais no modo ESP (para uma interface de áudio multicanal). Separação dura nos dois casos: canal sem faixa sai com amostras exatamente zero, e `tools/testar_site.py` confere isso. Ganho acima de 100% satura no arquivo como saturaria na saída ao vivo.

### Saída serial

Só no modo ESP. Web Serial, texto por linha, eventos com carimbo em ms enviados 100 ms antes, mais a mensagem `P c g` que diz qual GPIO cada canal aciona — o mapa inteiro vai ao conectar e a cada mudança. Contrato completo em `docs/protocolo-serial.md`.

O painel da saída ESP32 tem o número de flybacks, a placa (ESP32 ou ESP32-S3, cada uma com a lista de pinos livres em módulo comum e seis padrão), um seletor de pino por canal que marca pino repetido, um botão "testar" por canal (um lá de 0,6 s, para achar qual flyback é qual) e o registro das linhas enviadas. **O registro funciona sem ESP conectado**: com ele aberto, tocar gera o mesmo fluxo que iria para a porta, e é o que serve para escrever e conferir o firmware.

Testado com porta simulada em `tools/testar_site.py`; ainda não há firmware.

### tom.html — gerador de tom

Dois osciladores, um por canal, criados uma vez e deixados ligados: quem dá e tira voz é o ganho, com rampa de 8 ms, e assim não há clique. Separação dura pelo mesmo `ChannelMergerNode`. A frequência vai por `setTargetAtTime` com constante de 6 ms, que é o que deixa arrastar o slider sem degrau e sem atraso perceptível.

Slider logarítmico de 20 Hz a 20 kHz em 2.000 passos (`freqOf`/`sliderOf`), campo numérico, ×½ e ×2, passo de 1 Hz e seletor de nota de E0 a B9. Formas: quadrada (padrão, que é o timbre real do arco), senoide, triangular e dente de serra. Mais varredura logarítmica entre dois limites, com ida e volta, e intervalos prontos entre os dois canais — uníssono, oitava, quinta, terça e batimento de 1 Hz, que é como se ouve se os dois arcos estão casados.

O traço do osciloscópio desenha uma janela de três ciclos da frequência atual, em vez do buffer inteiro: sem isso a forma vira um borrão em frequência alta. O desenho para quando nada toca.

Estado no endereço (`?f=…&o=…&g=…&l=…&v=…`) e no `localStorage`. A gravação é adiada 400 ms, porque a varredura mexe na frequência a cada quadro e gravar a cada quadro seria absurdo.

### Layout: interface de programa, para o computador

O dono do projeto passou a usar só pelo computador, e o layout de coluna única, pensado para o celular, desperdiçava a tela em paisagem. Agora é uma interface de editor, no espírito do OBS ou de um editor de vídeo, com a janela inteira ocupada e cada painel rolando por dentro:

- **Em cima, à esquerda — Faixas.** As faixas da música aberta, cada uma com uma luz que acende quando ela tem nota soando e o seletor de saída (E/D/ambos no estéreo, 1 a N no ESP). Os presets, o aproveitamento por canal e o crédito ficam aqui.
- **Em cima, à direita — Saídas.** Uma pista por flyback: nome, pino ou lado, nota e frequência que está soando, de onde vem (as faixas roteadas), um osciloscópio com três ciclos da nota disparado na borda de subida, e um rolo com a linha monofônica correndo numa janela de 5 a 40 s, com o cursor a um quarto da largura para mostrar o que vem.
- **Transporte**, entre as duas metades, com a linha do tempo da música inteira (uma faixa por saída) que serve de busca.
- **Embaixo — a doca**, três painéis lado a lado: **Acervo**, **Canais** (um módulo de mixer por flyback, com M e S, ganho, passa-baixa, oitava, acorde, envelope e dinâmica) e **Saída** (o painel do modo: no estéreo, a explicação do P2; no ESP, a conexão e os pinos; nos dois, WAV e configuração).

A divisória entre as duas metades arrasta (e anda com as setas), e o tamanho fica lembrado; duplo clique volta ao padrão. O padrão dá à doca uma altura estável (`clamp(200px, 100vh − 480px, 70vh)` para a metade de cima), porque é a doca que precisa de altura para o acervo e o mixer caberem — com a metade de cima proporcional à tela, a 1366×768 o acervo mostrava uma música só. A pista esconde a linha de faixas quando fica baixa demais, por container query.

O seletor de modo fica na barra de cima. Trocar de modo pausa, silencia os flybacks (`X`) e carrega a configuração do outro modo.

Arquivo se abre pelo acervo, por "Abrir arquivo…" ou **arrastando para qualquer ponto da janela**. Atalhos fora de campos de texto: espaço toca e pausa, setas andam 5 s, Home volta ao início.

Abaixo de 1100 px de largura ou 600 px de altura os painéis empilham e a página rola, com o transporte grudado embaixo: não é o uso planejado, mas abrir num notebook pequeno ou no celular não pode quebrar. Continuam valendo `navigator.audioSession.type = 'playback'`, Wake Lock enquanto toca e o desenho parado quando nada toca.

### Gerar MIDI do áudio — `tools/transcrever.py`

Duas vias, `--motor muscriptor` (padrão) e `--motor stems`. A primeira é melhor sempre que der
para usar; a segunda não depende de pesos sob licença e continua mantida porque é o caminho que
sempre funciona.

#### `--motor muscriptor` — uma faixa por instrumento

[MuScriptor](https://github.com/muscriptor/muscriptor), da Kyutai com a Mirelo: um transformer
decoder-only que lê o mel da **mistura** e escreve as notas direto, cada uma com seu instrumento.
Resolve de uma vez as duas coisas que o caminho de stems resolve mal — não existe "harmonia" como
um saco só, porque guitarra, piano e teclado saem em faixas separadas; e não há erro de oitava de
estimador de altura, porque não há estimador de altura.

Encaixa no projeto sem adaptação: escreve SMF tipo 1 com uma faixa nomeada por instrumento e
bateria no canal 10, que é o que o parser do site já espera, e o nome `voice` casa com `RX_CANTO`
sem mexer em nada. **Então o MIDI dele entra no acervo como está, sem redução** — quem reduz a
uma nota por arco é o site, no momento de tocar, como faz com todo o resto do acervo.

**`--instrumentos` não é um filtro, é uma afirmação.** Os 35 grupos que o modelo conhece estão em
`INSTRUMENTOS`. Os que não estiverem na lista ficam proibidos de ser decodificados, mas a lista
também vira o **condicionamento** do modelo (`instrument_group_from_names` devolve "the model's
conditioning string"): ele passa a esperar exatamente aqueles instrumentos. Medido em Borboletas
contra a versão que o Mirelo devolveu para a mesma música, com o `medium`:

| | voz | baixo | violão | todas as notas |
|---|---|---|---|---|
| sem lista | 123 notas, F1 22% | 80% | 84% | 77% |
| com voz, violão, baixo, piano, pad, bateria | 468 notas, **60%** | **92%** | 85% | **80%** |

Sem lista, o `medium` punha metade do canto na faixa de violão (49% da voz do Mirelo aparece lá, 13%
na voz). Com a lista certa a voz volta para a faixa dela. Com a lista errada estraga: passar os 34
grupos menos a voz "para o modelo escolher" fez ele inventar trompa, flauta e saxofone com 22 notas
simultâneas. Por isso não há atalho de lista fixa — houve um, `seis`, e foi removido: afirmava
guitarra distorcida e órgão em toda música. O piano de Borboletas não aparece nem com a lista.

Duas tentativas que **não** funcionaram, para ninguém repetir: transcrever o canto separado pelo
Demucs (`--instrumentos voice` no stem de voz) deu voz pior que a do Mirelo e que a do pYIN — o
modelo foi treinado em mistura, não em stem com artefato; e transcrever o acompanhamento sem a voz
deu o lixo da orquestra acima.

Ainda aberto: comparar o `large`. Os pesos baixam (5,5 GB em float32), mas a primeira tentativa
morreu ao carregar, por falta de RAM num computador de 16 GB — o `load_model` lê o float32 inteiro
antes de converter para float16.

A bateria, quando sai, são milhares de notas de exatamente 10 ms em meia dúzia de "alturas" que são
teclas do mapa de percussão do GM — 36 bumbo, 38 caixa, 42 prato — e não alturas de verdade. Num arco
isso são milhares de cliques em frequências arbitrárias, não ritmo; o preset "um por flyback" do site
a deixa desligada.

E uma medida que importa para o planejamento: nas mesmas duas saídas, `aproveitamento()` dá 42% e
46% em dois canais. Isso é **abaixo do `APROV_MIN` de 58 do site** — não porque a transcrição
esteja ruim, mas porque ela é fiel: cinco ou seis instrumentos não cabem em dois arcos, e mais da
metade da música é descartada na redução. Transcrição multifaixa boa e dois flybacks são
objetivos que brigam entre si, e é o segundo que precisa crescer.

| Variante | Parâmetros | Onde cabe |
|---|---|---|
| `small` | 103M | CPU |
| `medium` (padrão) | 307M | float32 numa placa de 6 GB |
| `large` | 1,4B | precisa de float16 numa placa de 6 GB — é o que `--dtype` faz sozinho |

**O código é MIT, os pesos são CC BY-NC 4.0 e exigem licença aceita numa conta do HuggingFace.**
Não há como contornar de fora: `hf_hub_download` devolve `GatedRepoError` 401. Não comercial casa
com o uso deste projeto (ver `USO-EDUCACIONAL.md`), mas é uma dependência de conta de terceiro, e
é por isso que o motor de stems não foi removido.

No Windows o `rich` do CLI dele quebra no console cp1252; `PYTHONUTF8=1` resolve. Pelo Python
(que é como `transcrever.py` chama) não acontece.

#### `--motor stems` — separação e rastreio de altura


O acervo vive de transcrição de fã, e a qualidade varia muito. Transcrever direto da gravação tira a interpretação de terceiros do caminho, e o problema é mais fácil do que parece **por causa do aparelho**: cada flyback toca uma nota por vez, então não é preciso resolver transcrição polifônica — basta a linha dominante de cada stem.

Separação com o Hybrid Demucs que vem no torchaudio (`HDEMUCS_HIGH_MUSDB_PLUS`), sem o pacote `demucs`. Depois, **o transcritor muda conforme a fonte**, e essa escolha é a diferença entre soar certo e soar cacofônico:

| Faixa | Método | Por quê |
|---|---|---|
| `Vocal` | pYIN (monofônico) | voz é monofônica por natureza; sai limpo |
| `Baixo` | pYIN (monofônico) | idem, e o registro estreito ajuda o estimador |
| `Harmonia` | basic-pitch → linha de raiz | guitarra e teclas tocam acordes |

**A `Harmonia` é o caso interessante.** Tratada como monofônica, a linha pulava entre os parciais do acorde e soava mal. Mas transcrição polifônica crua é *pior* ainda depois da redução do site: a regra de "ganha a nota mais recente" faz a linha saltar entre os membros do acorde conforme cada um entra. Medido no mesmo trecho:

| | segmentos | nota média | cobertura | saltos > 5ª |
|---|---|---|---|---|
| pYIN | 341 | 368 ms | 62% | 34% |
| basic-pitch cru | 1837 | 106 ms | 97% | 44% |
| basic-pitch → raiz, grade | 329 | 596 ms | 98% | 17% |
| basic-pitch → raiz, ataque | 670 | 280 ms | 94% | 38% |
| **raiz: tempo do ataque, altura do que soa** | **333** | **578 ms** | **96%** | **9%** |

Então o basic-pitch entra como **detector de acorde**, não como fonte de notas. Mas *como* reduzir tem duas respostas óbvias e as duas erram, e a tabela mostra por quê — o número que importa é o último, saltos maiores que a quinta, porque é o que faz a linha soar picotada no arco.

A primeira versão amostrava a nota mais grave **ativa** numa grade de 40 ms. Boa nos números, ruim no ouvido: o basic-pitch inclui a ressonância na duração da nota, então a raiz do acorde anterior **ainda está soando** quando o seguinte ataca, e continua sendo a mais grave. Saíam notas de 5,4 s — bordão, não harmonia, e foi exatamente isso que se ouviu de estranho ("muitas notas se juntaram").

A correção óbvia, tomar a mais grave de cada **ataque**, mata o bordão e estraga a linha: num dedilhado cada corda entra sozinha, viram acordes de uma nota só, e os saltos grandes vão de 17% para 38% — tão picotado quanto o basic-pitch cru.

O que funciona é tirar as duas coisas de lugares diferentes. **O ataque diz quando trocar** (notas que entram dentro de 150 ms são um acorde só); **o conjunto que soa nesse instante diz qual nota é** (a mais grave dele, que é a raiz na maioria das posições de guitarra e teclado, e que se mantém firme mesmo quando a fundamental não rebate). Mais duas regras: repetir a mesma classe de altura une em vez de picotar, porque acorde rebatido não precisa virar duas notas no arco; e um teto de 1,5 s corta o bordão nos trechos sem ataque novo. Resultado: 9% de saltos grandes, metade do método de grade, e nota mais longa de 1,5 s em vez de 5,4 s.

**`--guardar` e `--stems`.** A separação é a parte que estoura a VRAM e a única que precisa de GPU; transcrição e redução rodam em segundos. Ajustar a regra de harmonia e ouvir de novo não deveria custar uma separação nova, então `--guardar PASTA` deixa os stems em disco e `--stems PASTA` retoma deles. Foi assim que esta medição foi feita, sem reprocessar áudio.

Quatro armadilhas que custaram caro e estão resolvidas no código, todas achadas medindo o funil de filtros em vez de adivinhar:

- **`voiced_prob` não é confiança na altura.** Filtrar por ela descartava 80% dos quadros que o pYIN já aceitara pelo caminho de Viterbi; mesmo um piso de 0,1 derrubava 101 s de vocal para 55 s. Vale a decisão do Viterbi (`voiced_flag`), que usa continuidade temporal.
- **Juntar antes de cortar.** Medir a duração mínima antes de unir fragmentos da mesma nota reprovava cada pedaço sozinho: 864 trechos somando 55 s viravam 36 s.
- **Janela do pYIN.** Precisa caber dois períodos de `fmin`; com 2048 amostras e `fmin` de 30 Hz o baixo não devolvia nota nenhuma.
- **Erro de oitava.** O estimador trava no subharmônico em ~5% das notas. `corrigir_oitavas()` puxa de volta o que está a mais de 14 semitons da mediana da faixa.

Instalação: o `basic-pitch` fixa dependências antigas demais para o Python 3.13 (`resampy<0.4.3` arrasta um numpy que não compila), então vai com `pip install --no-deps basic-pitch` mais `onnxruntime pretty_midi mir_eval resampy`. O backend é ONNX; TensorFlow não entra.

Numa RTX 2060, cerca de 1min40 para uma música de cinco minutos, download incluído. Se a área de trabalho estiver usando VRAM, a separação pode falhar mesmo com memória livre — daí `--trecho 5` ou `--cpu`, e o áudio baixado fica preservado para não repetir o download.

## Convenções

- **Interface em português do Brasil.** Todos os rótulos, mensagens e comentários voltados ao usuário. Nomes de instrumento General MIDI ficam em inglês, como aparecem nos programas de música.
- **Estética de osciloscópio.** Fundo azul profundo, grade pontilhada, traço 1 amarelo-fósforo e traço 2 ciano. É referência ao Tektronix TDS 1012C que o autor usa na bancada. Amarelo é sempre o canal esquerdo (canal 1 no ESP), ciano sempre o direito (canal 2), em toda a interface — por isso destaques que não são de canal (música atual, botão ligado) usam o painel azul, não essas cores. Os canais 3 a 6 do modo ESP têm laranja, lilás, verde e rosa (`CORES` no `index.html`, `--c1` a `--c6` no CSS), e a mesma regra vale para eles: cor de canal só em coisa de canal.
- Tipografia IBM Plex Sans para interface, IBM Plex Mono para leituras numéricas.
- Sem caixa-alta decorativa, sem sombras em cartão, sem ícones genéricos.
- `box-sizing: border-box` aplicado direto em `*`, não por herança: o conteúdo de `<details>` não herda pela árvore interna do navegador, e com `inherit` os botões do acervo estouravam a largura.

## O que está aberto

- **Firmware** que consuma o protocolo serial, incluindo `P` para o mapa de pinos. O lado do navegador está pronto e testado com porta simulada; o painel "Linhas enviadas" mostra o fluxo sem ESP ligado.
- **Saída multicanal pelo áudio.** Com uma interface de áudio de 6 saídas, o Web Audio poderia acionar seis flybacks sem ESP (`destination.channelCount`). O WAV de N canais já existe; a saída ao vivo não.
- **Receber arquivo compartilhado** de outro aplicativo no celular (Web Share Target). Hoje se abre pelo seletor de arquivos ou pelo acervo.

## Contexto de hardware

`docs/hardware-decisoes.md` tem o registro completo das decisões do driver de flyback, incluindo por que a modulação é analógica, por que cada canal é monofônico, e as medições de bancada. A seção 3.16 importa para o firmware da saída serial.

## Restrições de manutenção

- Não introduzir bundler, framework ou gerenciador de pacotes. O valor destes arquivos está em abrir e funcionar.
- Não usar `localStorage` sem `try/catch` e sem funcionar quando vazio (`store` em `index.html`).
- Qualquer biblioteca externa só via `<script>` de CDN, com versão fixada.
- Arquivo novo que o site precise servir tem de entrar no passo "Montar o site" do workflow e, se for do núcleo, em `BASE` no `sw.js`. Mudou `sw.js` de forma incompatível: troque o nome de `SITE`.
- Rodar `python tools/testar_site.py` antes de publicar mudança no `index.html`. Testar com MIDI real antes de considerar pronto: um arquivo de música de videogame (3 a 4 faixas) e um arranjo de banda (6 a 8 faixas) cobrem os dois extremos. `musicas/exemplos` tem os dois casos, um Guitar Pro e os arranjos do projeto, que cobrem 6/8 e 3/8, andamento acelerando e ritardando; `musicas/bandas` tem arranjo de banda de verdade, com 8 a 16 faixas.
- Ferramenta que mexe no acervo **não altera nada sem `--aplicar`** (ou `--baixar`, no download). Sem a opção, só imprime o que faria. Mantenha assim.
- **Pasta no Windows vem com o atributo ReadOnly**, e aí `Path.rmdir()` falha com "Acesso negado" mesmo estando vazia. `remover_vazias()` em `curar_acervo.py` tira o atributo e tenta de novo, e engole a falha se ainda assim não for. Use essa função em vez de `rmdir()` direto. Pelo mesmo motivo, **grave o `creditos.json` antes da faxina de pastas**: é ele que guarda a atribuição exigida pelas licenças, e já se perdeu uma vez porque uma pasta vazia resistiu a sumir e abortou o resto.
- Rodar script com `2>/dev/null | tail` esconde o traceback e devolve o código de saída do `tail`, que é sempre 0. Foi assim que a falha acima passou despercebida.
