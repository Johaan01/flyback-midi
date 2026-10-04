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
| `tools/instrumentos.py` | Descobre a instrumentação de uma gravação para condicionar o MuScriptor: PANNs (AudioSet) aplicado a cada stem do Demucs. Voz pelo peso do stem de voz, baixo e bateria pelos rótulos, o resto traduzido para os grupos do MuScriptor |
| `tools/lote.py` | Transcreve uma playlist do YouTube sozinho, retomável: `large` com a lista de instrumentos de cada música (`--instrumentos-por`, e aí orientação 2) ou a automática, segunda tentativa com a separação em blocos menores, e o que ainda falhar vai para `para-o-mirelo.md` com os instrumentos a marcar. Credita cada música no `creditos.json`, confere a montagem de 6 flybacks dela e quanto do canto da gravação virou nota |
| `tools/conferir_voz.py` | Separa o canto da gravação (Demucs) e mede quanto dele tem nota na faixa de voz do MIDI, com os trechos sem nota. O lote roda depois de cada música; abaixo de 60%, aviso |
| `tools/auditar_montagem.py` | Abre cada MIDI no próprio `index.html` (Playwright) com N flybacks e mede, faixa a faixa, quanto do tempo de nota soa em algum arco: aponta instrumento sem arco e melodia calada em trecho longo — o que o site, uma nota por arco, não deixa ver |
| `tools/medir_canais.py` | Mede o aproveitamento de todo o acervo em 2 e em 6 flybacks e grava no `creditos.json` — é o que o site usa nos filtros "2 canais" e "+ de 2 canais" |
| `tools/servidor.py` | O outro lado da janela "Baixar músicas": busca no YouTube, fila, download, transcrição na GPU daqui ou no Mirelo, crédito e push para o GitHub, com o andamento de cada etapa. Só biblioteca padrão; chama `lote.py` e `mirelo.py` |
| `tools/mirelo.py` | Transcrição pela API do Mirelo: sobe o áudio, pede a detecção de instrumentos, cria o job e baixa o MIDI. A chave fica só na máquina do servidor |
| `tools/generos.py` | Preenche o gênero (`estilo`) de bandas e transcritas pelo MusicBrainz, uma consulta por artista; o que ele não classifica vai em `MANUAL` |
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

A saída é uma só, comandada pelo **número de flybacks** (1 a 6), e a separação dura vale para o que aciona flyback. Já foram dois modos, estéreo e ESP; o dono do projeto notou que o estéreo era o ESP com dois flybacks por outro caminho, e virou um só:

- **1 ou 2 flybacks** — o áudio do computador sai com separação dura, canal 1 no esquerdo e canal 2 no direito: é o P2, como o site sempre foi. Presets e configuração são os clássicos de dois lados, inclusive os `.json` do acervo.
- **3 a 6** — o áudio do computador vira **monitor**, com os canais somados nos dois lados (ganho dividido por √N para a soma não saturar). O monitor não aciona flyback nenhum, então a soma ali não fere a regra.
- **A serial vale sempre** que houver ESP32 conectado, com qualquer número de flybacks.

Quem usava o modo estéreo da versão anterior começa com dois flybacks (`modoAntigo` em `index.html`).

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

**Origem: quem transcreveu.** `gerar_acervo.py` grava `origem` no índice a partir do crédito: `muscriptor` quando a transcrição foi rodada aqui, na GPU (o crédito diz "rodado localmente"), `mirelo` quando veio do Mirelo, pela interface ou pela API; sem o campo, é MIDI nativo, escrito por uma pessoa. O site mostra isso em cada linha — "MIDI · nativo", "MIDI · MuScriptor", "MIDI · Mirelo" — e a busca acha pelas três palavras. É campo, não pasta, de propósito: pasta serve para achar (artista, compositor), origem é uma característica, e a mesma música pode existir nas versões. A montagem fixa vale para todas — numa amostra de 40 transcrições de fã, a melodia caiu no flyback 1 em 39, o baixo no 2 em 35, a guitarra no 3 em 34 e a bateria no 4 em 38, porque ela lê o programa General MIDI, que essas transcrições trazem. O que difere é a densidade: as de fã têm 9,7 faixas em média (uma de Queen tem cinco guitarras), e 46% delas ficam sem flyback; as da IA têm de 4 a 6.

**Montagem fixa (3 a 6 flybacks).** Cada família de instrumento cai sempre no mesmo flyback, em toda música: 1 voz, 2 baixo, 3 guitarra, 4 bateria, 5 teclado, 6 extra (`PAPEIS`, `familia()`). Pedido do dono do projeto: duas músicas de rock têm de sair com os mesmos instrumentos nos mesmos arcos. A ordem é a de importância — com 4 flybacks ficam voz, baixo, guitarra e bateria. Na família, a faixa que mais ocupa a música é a dona; as outras entram nas brechas (6% e 30%). O 1 é da melodia principal pela detecção de canto; numa instrumental pode ser a guitarra solo. Os flybacks que sobram vazios — o 6 quase sempre, o 5 quando não há teclado, o 3 quando não há guitarra — vão para instrumento de verdade ou para a segunda voz, nunca para pedaço de acorde (ver **Arcos vazios**, abaixo).

**Quem manda quando a família tem mais de uma faixa: mais ataques** (instantes de começo de nota, acorde contando como um, `ataques()`). Nem mais notas — acorde de três conta três, e uma guitarra abafada tinha 1.132 notas e 412 ataques — nem mais tempo, que escolhe o bordão: em Borboletas ganhava o pad, de notas de 1,7 s em acorde, sobre o piano. Mais ataques é a parte que mais se mexe, a mais reconhecível numa nota por vez. Medido em 77 conflitos de família em 73 músicas: "mais tempo" e "mais ataques" discordam em 13. E o nome dado à faixa vale antes do programa GM (`familia()`): "Vocals" com programa de guitarra é voz.

**Repartir.** Os arcos com a opção "repartir" em "Acorde" que recebem a mesma faixa dividem as notas dela como as vozes de um teclado polifônico (`repartir()`, `notasPara()`): cada nota nova vai para um arco livre, o de altura mais próxima primeiro, e se nenhum estiver livre rouba o que soa há mais tempo. O arco principal é o do papel da faixa (o 1 para a melodia) e fica com a nota de ponta — a de cima na melodia, a de baixo no resto —, cedendo a vez só a uma nota mais de ponta que a dele: o coro que entra abaixo do canto não corta o canto. Nota que termina até 80 ms depois da seguinte começar conta como terminada (`LEGATO`), senão o legato da transcrição jogava a melodia de um arco para o outro. Nos arcos extras de uma faixa que não é a melodia só entra nota uma quarta abaixo da média da melodia (o teto), para não mascarar o canto.

**Arcos vazios.** Vêm de uma auditoria (`tools/auditar_montagem.py`), pedida pelo dono do projeto com medo de baixar música e ela sair "faltando" num canal sem ele ver — o site mostra uma nota por arco, e a nota que ficou para trás só aparece num editor de MIDI. Os vazios vão, em degraus, e dentro de cada um para quem soa mais tempo:

1. **a faixa que não toca em arco nenhum**, se soar em 5% da música, com a nota de baixo (a de cima, se for voz). Em Sweet Home Alabama, os solos da guitarra distorcida, 36% da música; em So Far Away, uma guitarra presente em 69% dela;
2. **a segunda voz do canto**, se soar em 5% da música, contando só trechos de mais de 0,3 s (`vozesJuntas`), repartindo com o arco 1. Sobreposição curta é resto de transcrição: Rock N Roll Train tinha 7,7% de duas notas juntas e 2,7% em trecho longo. Victor & Leo são uma dupla, e o canto tocava 62% num arco só; repartido, 98%;
3. **a faixa que já soa nas brechas de outra da mesma família**, que ganha arco próprio: a guitarra distorcida de Still Loving You dividia o arco da limpa. Abaixo da segunda voz porque já soa — o pad de Borboletas tirava o arco da dupla;
4. **sobrando arco, a segunda voz com bem menos (1%) e a terceira** — o coro em terças de So Far Away, as vozes empilhadas de We Will Rock You. Arco livre não custa nada a ninguém.

O que ainda sobra fica calado. **Já houve pedaço de acorde nos vazios, e saiu.** A guitarra ia repartida em três arcos, com as outras notas do acorde nos extras, e o dono do projeto ouviu "os tons nos lugares errados" em Scorpions, Breaking the Law, Symphony of Destruction e na "guitarra extra" de Simple Man — depois de já ter achado o recurso "pouco elegante". A razão: com um arco, só a nota de baixo de cada acorde soava, e o erro da transcrição nas notas de dentro ficava escondido; espalhado, cada nota interna errada virava um arco tocando fora do lugar. Quem quiser o acorde inteiro põe a faixa em mais arcos com "repartir", à mão.

Depois disso, nas 47 transcritas, 42 sem aviso; nas 5 restantes os seis arcos estão ocupados por instrumentos de verdade e o aviso descreve uma troca (em Sweet Home Alabama, os solos ou o backing vocal do refrão), não um erro.

**Juntar faixas de outra versão.** Cada modelo acerta uma parte: em La Grange o `medium` achou mais voz que o `large`; em Deja Vu o `large` achou o synth pad que o `medium` não achou; o Mirelo pega a segunda voz. O dono do projeto pediu para tirar a faixa de uma e pôr na outra, imaginando um editor de MIDI. Não precisou: o seletor "Juntar faixas de outra versão" no painel de Faixas lista as outras versões da mesma música no acervo (mesmo título, tirado o sufixo de versão, `VERSAO`) ou abre um arquivo do computador, e as faixas dela entram na lista **desligadas**, com o nome da versão ("voice · medium") e **alinhadas no tempo** (`alinhar`: o desvio, de −3 a +3 s, que mais casa ataques da bateria, senão do baixo — o áudio do Mirelo de Livin' On A Prayer está 0,84 s deslocado, e o site acha). Escolher a voz de uma e a guitarra de outra é rotear, no seletor de flyback de cada faixa. A configuração da música guarda de onde vieram (`juntar`: arquivo, rótulo e desvio), e ela reabre com as mesmas. Os presets não mexem nas faixas juntadas (`t.junta`): são escolha de quem ouve. **"Baixar MIDI"** grava só as faixas que estão em algum flyback (`midiDe`, SMF formato 1 a 120 bpm, 960 tiques por segundo), com o nome sem o sufixo quando não repete — é a versão combinada, pronta para ir ao acervo.

Por isso as versões alternativas ficam no acervo, com o modelo no fim do nome — "ZZ Top - La Grange (large)", "Dave Rodgers - Deja Vu (large)" —, como a do Mirelo fica com "(Mirelo)". A principal é a sem sufixo.

**O agudo máx também mexe na oitava, e agora avisa.** O dono do projeto desconfiou, com razão, que a oitava saía do lugar pela interface e não pela transcrição. Eram dois caminhos: a oitava de um arco, que até esta mudança valia para todas as músicas (agora é por música), e o agudo máx, que desce de oitava, nota a nota, o que passa do limite — com o limite baixo na voz, só as notas altas caem e a melodia pula no meio da frase. O módulo do canal agora diz quantas notas o agudo máx desceu.

**O arco do baixo toca a nota mais grave que soa**, de qualquer ataque, em vez de "a última que entrou ganha" (`grave` em `buildSegs`). Baixo de verdade quase nunca tem duas notas; o que aparece por cima é acorde de synth que a transcrição pôs na faixa de baixo — em Never Gonna Give You Up, três notas juntas em média —, e com a regra comum o arco saía da linha do baixo a cada ataque.

**O som segue o instrumento, não o arco nem a música.** Com 3 ou mais flybacks, agudo, envelope e dinâmica são de cada instrumento — voz, baixo, guitarra, bateria, teclado, extra (`sons`, `flyback:sons` no navegador) —, ajustados uma vez para todas as músicas, e cada arco toca com o som do instrumento que manda nele (`familiaDoArco`: a faixa de maior prioridade, e no empate a de mais notas). Mexer no envelope de um arco muda o do instrumento dele, em todo arco que o toca. O ganho fica por arco (`ganhoArco`), porque é o volume de cada flyback, que é físico. Já foi por arco (`montagem`, que migra sozinha para `sons` pela ordem dos papéis), e o dono do projeto notou o problema quando os arcos vazios passaram a receber coisas diferentes em cada música: o 6 com a segunda voz tocava com o envelope de corda, que apaga. Agora soa como voz, e o mixer mostra "6 · extra · som de voz". O que é da música é o roteamento, qual nota do acorde cada arco toca e **a oitava** (`cfgmont:`): ela depende do cantor, não do instrumento. A voz de Sweet Child O' Mine está na altura certa no MIDI (94% das notas batem com o pYIN do canto separado), mas em onda quadrada soa mais grave que a voz rasgada do Axl, e o dono do projeto a quis uma oitava acima — o que, valendo para toda voz, subiria também a de Back In Black, que já é aguda. Padrões: voz no médio, bateria em batida, e **"corda"** no resto. O envelope "corda" (`tau` 0,9 s, sem patamar) faz a nota apagar até a próxima; veio de ouvido, na introdução de Iron Man, onde cada nota dura ~1,8 s e os outros envelopes ou caíam num patamar de 10% ou ficavam retos em 70%. Com dois flybacks tudo continua por música, como sempre foi.

**Bateria.** A transcrição escreve cada batida como nota de 10 ms na tecla do mapa de percussão do GM. `notasDe()` troca cada uma por um estouro de tom pela peça (`BATIDA`): bumbo A1 de 120 ms, caixa G3 de 90 ms, palma, tons. Bumbo e caixa (prioridade 3) ganham dos tons (2). Chimbal e pratos ficaram de fora: mapeados como estouros agudos, eram o que mais se ouvia no canal, estridentes em onda quadrada.

**Agudo máx no lugar do passa-baixa.** O passa-baixa era um filtro no áudio do computador: não chegava aos flybacks do ESP (a serial manda a frequência da nota), cortava só 12 dB por oitava e deformava o topo da onda quadrada. O limite age na nota: o que passa dele desce de oitava até caber, no P2 e na serial. Os `.json` do acervo tinham todos passa-baixa em 20 kHz, desligado, e o campo novo é `agudo`.

A troca no `best()` de `buildSegs` para aceitar "do meio" foi verificada contra a versão anterior: em 91 MIDIs do acervo, aguda e grave dão linhas idênticas, com e sem prioridade.

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

O acervo tem 1.934 músicas em cinco pastas de primeiro nível:

| Pasta | Quantas | O que é |
|---|---|---|
| `bandas` | 1.239 | transcrições de fã, **uma pasta por artista** (122 deles) |
| `classicos` | 590 | Mutopia, em `<região>/<compositor>/` |
| `folk russo` | 45 | tradicional e soviético, pasta plana |
| `transcritas` | 50 | geradas do áudio pelo MuScriptor, aqui ou no Mirelo, sempre "Artista - Música"; a versão do Mirelo de uma música que também foi feita aqui leva "(Mirelo)" no fim, para as duas ficarem juntas na lista. O grupo é o artista, do crédito |
| `exemplos` | 10 | arranjos do projeto para dois flybacks, mais casos de teste |

Eram 4.867 só em `classicos`, todos numa pasta por compositor, o que tornava o filtro inútil: a lista era um balaio só. `tools/curar_acervo.py` resolveu as duas coisas ao mesmo tempo.

**Por que artista, e não nível de popularidade.** As bandas já estiveram em `mais ouvidas` / `conhecidas` / `para fãs`, e foi pior: 554 caíam no último nível, que virava uma parede, e não havia como pedir "me mostra o AC/DC". Pior ainda, o nível de uma música **muda quando o número de escutas muda** — ela trocaria de pasta sozinha, e o link dela (`?m=caminho`) quebraria. Artista é coisa estável. A popularidade continua medida e gravada em `posicao`, e virou filtro na interface.

**A descoberta que guia a curadoria:** o sufixo " - NN" do título do Mutopia **não é número de movimento**. Em `Air (BWV 1068)` os cinco arquivos têm a mesma duração e são a partitura inteira (4 faixas, 516 notas) mais cada parte de instrumento sozinha; já em `French Suite no. 3` os 14 arquivos são 7 movimentos, cada um gravado duas vezes. O que separa um caso do outro é a **duração**. Por isso a ferramenta agrupa pela chave `mutopia` do `creditos.json`, separa movimentos pela duração (com folga de 1,5 s ou 2%), e de cada movimento fica com o arquivo de mais faixas — a partitura inteira, a única que serve para repartir entre dois canais. Só isso tirou 1.722 arquivos.

### Navegação do acervo

O dono do projeto achou o menu "poluidíssimo": seis botões de filtro sempre à mostra (só as mais ouvidas, só com vocal, cabe em 2, pede 6, só IA, sortear) mais um botão por pasta. Ficou assim:

- **Três vistas** (`VISTAS`, `naVista()`): **tudo**, **antigas** (tudo que não é `transcritas`) e **transcritas**; "meus" aparece quando há arquivo aberto do computador guardado. É a separação legado × modelo que o dono pediu, por campo de pasta e não por mudança de pasta.
- **Grupo e gênero**, dois seletores (`montarFiltro()`). Nas transcritas o grupo é o **artista** do crédito (valor `a:` + nome dobrado), porque a pasta é uma só; no resto é a **pasta mais funda** (`p:`), com a de cima como `<optgroup>` — os 122 artistas de `bandas`, os 139 compositores de `classicos` pelas 9 regiões. O gênero sai de `estilo`, traduzido por `ESTILO_PT` (o Mutopia escreve em inglês), e se esconde quando a vista tem menos de dois; aí a busca ocupa o lugar dele.
- **Filtros**, um menu que abre e fecha (`#libPop`; fecha com Esc ou clique fora): **com voz**, **2 canais** (`cabe2`, aproveitamento em 2 ≥ `APROV_MIN`), **+ de 2 canais** (`precisaMais`: não cabe em 2 e aproveitamento em 6 ≥ `APROV6_MIN`), **mais ouvidas** (`posicao <= TOPO`, só se o acervo tiver o campo) e **sortear uma**. O botão mostra quantos estão ligados.

"Pede 6" saiu por pedido: muita música que não cabe em dois fica boa com quatro, e o nome mentia. "+ de 2 canais" diz o que o número mede.

A busca cobre título, pasta, autor, artista, instrumentos, estilo, "vocal" e a origem. Continuam valendo: vista lembrada no aparelho, no máximo `LIMITE` (200) botões por vez e "Guardar para usar sem internet" dentro do filtro atual.

**Gênero.** Bandas e transcritas não tinham `estilo`; `tools/generos.py` consulta o MusicBrainz por artista (`artista_mb` em `lote.py`, que o lote também usa ao creditar) e agrupa os gêneros em poucos nomes (`GENEROS`): Rock, Metal, Pop, Soul... Duas armadilhas: nome sozinho é ambíguo ("Coda" achava um produtor de eletrônica), então primeiro procura a gravação com o artista e exige o mesmo nome; e o MusicBrainz responde 503 por limite de taxa mesmo a uma consulta por segundo — na primeira rodada isso deixou AC/DC, Black Sabbath, KISS e Scorpions sem gênero, e `_mb()` agora tenta de novo. Sobram 4 músicas sem gênero.

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
  "canais": [{ "ganho": 70, "agudo": 20000, "oitava": 1, "acorde": "agudo" }, { … }] }
```

`acorde` é `agudo`, `meio`, `grave` ou `repartir` (`ACORDE` no `index.html`): qual nota do acorde o flyback toca, ou, em `repartir`, a parte dele nas notas que os arcos com a mesma faixa dividem.

Internamente o roteamento de cada faixa é uma **máscara de bits**, um bit por canal (`assign[k]`): no estéreo 0, 1, 2 e 3 são exatamente o desligada, esquerdo, direito e ambos de antes; no ESP qualquer combinação dos seis vale, e uma faixa pode ir para mais de um flyback.

`saidas` é a lista de canais, contando de 1. `canal` (`desligada`, `esquerdo`, `direito` ou `ambos`) continua sendo escrito no modo estéreo, e é lido quando `saidas` falta — é assim que os `.json` da versão 1 que estão no acervo continuam valendo. Faixas casam pelo nome; se nenhuma casar, a configuração é ignorada.

**Uma configuração por modo**, em chaves separadas: `cfg:` para dois flybacks (a de sempre) e `cfgmont:` para qualquer outro número. O roteamento para dois flybacks no P2 e para seis no ESP não têm nada a ver um com o outro, e trocar de modo não pode apagar o ajuste do outro. Prioridade ao abrir: ajuste salvo no navegador para o modo atual; depois o `.json` do acervo, que descreve dois canais e por isso só vale no estéreo ou no ESP com dois flybacks; depois o preset padrão do modo. Mudar o número de flybacks redistribui pelo preset se a música não tem ajuste salvo, e só corta as rotas para canais que deixaram de existir se tem.

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
- **Embaixo — a doca**, três painéis lado a lado: **Acervo**, **Canais** (um módulo de mixer por flyback, com M e S, ganho, agudo máx, oitava, acorde, envelope e dinâmica) e **Saída** (o painel do modo: no estéreo, a explicação do P2; no ESP, a conexão e os pinos; nos dois, WAV e configuração).

A divisória entre as duas metades arrasta (e anda com as setas), e o tamanho fica lembrado; duplo clique volta ao padrão. O padrão dá à doca uma altura estável (`clamp(200px, 100vh − 480px, 70vh)` para a metade de cima), porque é a doca que precisa de altura para o acervo e o mixer caberem — com a metade de cima proporcional à tela, a 1366×768 o acervo mostrava uma música só. A pista esconde a linha de faixas quando fica baixa demais, por container query.

Não há barra no topo. O nome da música abre o painel de faixas; o número de flybacks, a placa, a conexão e o botão **Gerador de tom** (que leva ao `tom.html`, onde há o "voltar para MIDI") ficam no painel de saída. Mudar o número de flybacks pausa; entrar ou sair de dois troca o espaço de configuração (`cfg:` / `cfgmont:`) e carrega a daquele espaço.

**Tudo numa janela.** O dono do projeto reclamou de ter de rolar cada painel. Os painéis não têm barra de título — o conteúdo diz o que são —, e em Faixas e no Acervo os controles ficam parados no topo (`.fixo`) e só a lista rola. O estado da serial fica na linha do Conectar; os pinos, em duas colunas; áudio e configuração, numa linha cada; nos módulos de canal, rótulo e seletor dividem a linha. Medido a 1920×945 (Chrome maximizado em tela 1080p), no modo ESP com seis flybacks e Borboletas aberta, nenhum painel rola além da lista do acervo. A janela de tempo das pistas foi para o fim do transporte.

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

**O `large` não dispensa a lista.** Mesma música, mesma comparação:

| Borboletas contra o Mirelo | voz | baixo | violão | todas as notas | tempo (RTX 2060) |
|---|---|---|---|---|---|
| `medium` sem lista | 22% | 80% | 84% | 77% | ~4 min |
| `large` sem lista | 30% | 89% | 81% | 70% | ~12 min |
| `medium` com a lista | 60% | 92% | 85% | 80% | ~4 min |
| `large` com a lista | **67%** | 91% | 83% | 79% | ~9 min |

Sem lista, o `large` também põe o canto no violão, e ainda inventa uma faixa inteira de guitarra
limpa. Então o Mirelo não roda simplesmente o modelo grande: muito provavelmente condiciona pela
escolha de instrumentos que o usuário faz na interface dele ("divididos em quantos instrumentos eu
quiser"). Com a lista, o `large` ganha 7 pontos na voz e empata no resto, levando mais que o dobro
do tempo. O `medium` com a lista certa é o padrão razoável; o `large` vale quando a voz importa
muito e a máquina está livre.

**Orientação (`cfg_coef`): por que não é padrão.** Medido em Borboletas contra o Mirelo, com a lista dele (voz, violão, baixo, piano, pad, bateria) e o `medium`:

| orientação | voz | pad | piano | todas |
|---|---|---|---|---|
| 1 (padrão) | 60% | 25 notas | 0 | 80% |
| 2 | 61% | **200 notas** (Mirelo: 223) | 0 | 77% |
| 3 | 2% — desanda | | | 8% |

Com 2, instrumento listado que o modelo deixaria de fora aparece. Mas com instrumento **errado** na lista ele inventa e o canto vai junto: Borboletas com órgão e metais listados (não tem nenhum dos dois) saiu com 473 notas de "metais" — o canto — e a voz caiu de 524 para 88 notas. Como o detector automático erra justamente o "resto" (em BLOODY STREAM viu órgão no lugar da guitarra), 2 só vale com lista conhecida: `--orientacao 2 --instrumentos ...` no `transcrever.py`. Com a lista certa de Livin' On A Prayer, o synth apareceu com 332 notas (Mirelo: 962) e a voz ficou igual. O piano de Borboletas não aparece em orientação nenhuma: é o limite do modelo local.

**Thunderstruck: orientação 2 com a lista certa trouxe a voz que faltava.** O dono do projeto
ouviu "quase metade" das vozes faltando, e `tools/conferir_voz.py` confirmou: a faixa de voz cobria
45% do canto da gravação. O que faltava eram os gritos "Thunder!" e o "ah-ah-ah" do coro da
introdução (0:20–0:52) — no stem de voz, ataques a cada 3,6 s com probabilidade de altura 0,01: não
há nota ali para o pYIN, e o modelo também não escrevia. A primeira versão saiu com a lista
automática, que incluía um violão que a música não tem. Refeita:

| Thunderstruck | voz cobre do canto |
|---|---|
| `large`, lista automática (com violão) | 45% |
| `large`, voz + guitarra distorcida + baixo + bateria | 38% |
| `large`, a mesma lista, orientação 2 | **65%** |
| `medium`, a mesma lista, orientação 2 | 38% |

Com orientação 2 o `large` passou a escrever os gritos (B4) e o coro grave (D3–F#3), e guitarra,
baixo e bateria ficaram com o mesmo número de notas — não inventou nada. Por isso o `lote.py` usa
orientação 2 quando a música tem lista própria (`--orientacao-com-lista`) e 1 com a automática, que
erra o "resto" e com 2 inventaria em cima do erro. Tentado e descartado: completar os buracos da voz
com o pYIN do stem (45% → 50%) e transformar grito sem altura em estouro curto, como a bateria
(65% → 67% sobre a versão boa) — não pagam a complexidade.

**O site da Kyutai (muscriptor.kyutai.org) roda o `medium`.** É o `muscriptor serve` do próprio
pacote — a mesma versão 0.3.0 instalada aqui, com a página em `web_dist`: `POST /transcribe` com
o áudio e a lista, resposta em fluxo, um trecho de 5 s por vez. DEJA VU com a lista que o dono do
projeto marcou lá (voz, synth pad, electric piano, baixo, bateria): o `medium` daqui em float32
saiu **nota por nota igual** ao do site (F1 100% em todas as faixas), em 3min21 contra 4min25 lá;
o `large` daqui concordou 42%. O site não acrescenta nada à GPU daqui além de poupá-la. Três
coisas que a interface sugere e não são:

- a música de exemplo não tem detecção: os instrumentos dela estão fixos no código da página;
- "not detected" é só "ainda sem nota": o modelo escreve de 5 em 5 s, e a voz de Kickstart My
  Heart "apareceu" perto de 1 min porque é ali que o canto entra;
- o resultado não varia a cada rodada. A decodificação é gulosa, sem sorteio: o mesmo modelo, na
  mesma precisão, com o mesmo áudio e a mesma lista, dá o mesmo MIDI. O que muda o resultado é
  o modelo (`medium` × `large`), a precisão (float32 × float16) e a lista.

**O Mirelo não é nenhum dos dois.** Kickstart My Heart, voz, guitarra distorcida, baixo e
bateria: Mirelo × site da Kyutai concordam em 75% das notas, Mirelo × `large` daqui em 76%,
`large` × Kyutai em 82%. Onde o Mirelo se destaca, de ouvido e na medida: a segunda voz (23 s de
duas vozes juntas em Kickstart, contra 13 s no `medium`) e os acordes de metais em BLOODY STREAM
(715 notas, três por ataque, contra 481 e 1,6 no `large` daqui, que também chamou a guitarra de
órgão — erro do detector automático, não do modelo).

**Memória do `large`.** O `load_model` monta o modelo inteiro em float32 **na placa** e carrega
outra cópia float32 dos pesos antes de converter para float16 — pico de ~11 GB num lugar que tem 6.
No Windows o driver transborda para a RAM compartilhada: numa máquina de 16 GB a RAM livre bateu
0,1 GB no carregamento, e a primeira tentativa foi derrubada por isso. `carregar_muscriptor()`
resolve: monta o modelo já em float16 e copia os pesos tensor a tensor para dentro dele, e só no
fim vai para a placa (pico ~2,8 GB). Verificado contra o carregador oficial: mesma saída.

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

### Baixar músicas: a janela e o servidor

Pedido do dono do projeto para fechar o processo: da página, mandar uma playlist, uma música ou
só um nome, escolher e mandar transcrever, vendo o andamento, e a música aparecer no acervo
sozinha. O site é estático, então a janela (`#dlgBaixar` em `index.html`) só conversa com um
servidor que roda no computador da GPU: `tools/servidor.py`.

- **Biblioteca padrão só** (`ThreadingHTTPServer`), porta 8790. A primeira execução cria
  `~/.flyback-servidor.json` com uma chave aleatória e a imprime; todo pedido, menos `/ping`, exige
  a chave no cabeçalho `X-Chave`. Sem ela, qualquer página aberta no navegador poderia usar a GPU e
  o push para o GitHub. CORS aberto e `Access-Control-Allow-Private-Network`, porque o site vem do
  GitHub Pages e o servidor é `localhost`. De fora de casa: túnel (`cloudflared tunnel --url ...`).
- **Rotas**: `GET /estado` (tem chave do Mirelo?), `POST /buscar` (link de playlist ou música, ou
  texto, que vira `ytsearch10:`; marca o que já está no acervo), `POST /fila` com os itens e o
  motor (`local` ou `mirelo`), `GET /fila`, `DELETE /fila/<id>` e `GET /arquivo?nome=`, que
  devolve o MIDI pronto para o botão "abrir" tocar sem esperar o GitHub Pages.
- **Um trabalho por vez**, numa thread: metadados, download, transcrição (`large` com instrumentos
  automáticos, duas tentativas, como no lote) ou Mirelo, crédito (`creditar` do `lote.py`, que
  também busca o gênero), `.lote.json` e `git add/commit/push` só dos arquivos daquela música, com
  `pull --rebase --autostash` antes. O andamento de cada etapa (as porcentagens do yt-dlp, do
  Demucs e do MuScriptor, lidas da saída) vira uma porcentagem só por `PESO`.
- **`--sem-publicar`** deixa tudo local; é como se testa sem encher o repositório.

**Mirelo pela API** (`tools/mirelo.py`): o mp3 sobe como asset (`POST /v3/assets`, multipart com o
arquivo por último), a detecção de instrumentos do próprio Mirelo escolhe a lista (grátis até 10
por dia) e o job roda até `succeeded`; o MIDI vem de um link temporário. 2,5 créditos por segundo
de áudio pela API, segundo a documentação; a interface web cobrou o dobro (1.420 por 4:44). A chave fica no `~/.flyback-servidor.json` (campo `"mirelo"`) ou em `MIRELO_API_KEY`,
**nunca no site**; sem ela a janela esconde o botão. Escrito pela documentação pública e
**testado só até a autenticação** (chave inválida devolve 401 "Invalid API key"): o resto do
fluxo só se confirma com uma chave de verdade.

Testado de ponta a ponta com a GPU: busca, fila, Highway to Hell transcrita em 4min21s com o
andamento na janela, e "abrir" tocando o MIDI do servidor.

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
