# CLAUDE.md

Contexto do projeto para quem for continuar o desenvolvimento.

## O que é

Duas páginas web que geram áudio para alimentar **alto-falantes de plasma** — arcos elétricos de transformadores flyback que reproduzem som. O hardware é um projeto de eletrônica de potência separado; estas páginas são apenas a fonte de áudio.

- `index.html` — abre MIDI ou Guitar Pro (do acervo ou do aparelho), roteia cada faixa de instrumento para o canal esquerdo ou direito, e sintetiza onda quadrada.
- `stems.html` — carrega dois arquivos de áudio já separados (stems) e toca um em cada canal.

Ambas são **arquivo único, sem build, sem dependência de pacote**. Fontes do Google Fonts via CDN; o leitor de Guitar Pro vem do jsDelivr, carregado só quando um arquivo que não é MIDI é aberto. Devem funcionar abertas direto do disco e servidas pelo GitHub Pages.

Arquivos de apoio, fora das páginas:

| Arquivo | Papel |
|---|---|
| `sw.js` | Service worker: uso sem internet. Rede primeiro para o próprio site, cópia guardada primeiro para CDN |
| `manifest.webmanifest`, `icones/` | Instalação na tela inicial do celular |
| `musicas/` | Acervo. Tudo que estiver aqui aparece no site |
| `tools/gerar_acervo.py` | Gera `musicas/index.json`, a lista do acervo. Só biblioteca padrão |
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
| Faixas que não se atropelam | força bruta sobre 3^n atribuições, minimizando sobreposição temporal |
| Grave e agudo | ordena por nota média e divide ao meio |

O preset de faixas complementares fatia o tempo em janelas de 100 ms, monta ocupação por faixa, calcula sobreposição entre pares, e testa todas as combinações de `{desligada, esquerda, direita}`. Limitado a 10 faixas (as com mais notas) para manter o tempo de execução baixo.

Métricas mostradas ao usuário: **toca X% das notas** (fração das notas atribuídas que realmente soa) e **ativo X% do tempo**. Servem para julgar rapidamente se uma música cabe em dois canais.

Linha do tempo abaixo do osciloscópio: os segmentos de cada canal, altura relativa à extensão do canal. Tocar ou arrastar nela muda a posição.

### Acervo

`musicas/index.json` não é versionado: o workflow gera a cada publicação, e `tools/servir.py` gera ao servir. Se o índice faltar (Pages publicado a partir de branch, por exemplo), a página lista a pasta pela API de árvores do GitHub, deduzindo usuário e repositório de `usuario.github.io/repositorio`.

O botão "Enviar música para o acervo" aponta para `github.com/USUARIO/REPO/upload/main/musicas`: é assim que se adiciona música pelo celular, sem ferramenta nenhuma. O push dispara o workflow.

Abrir uma música do acervo troca o endereço para `?m=caminho`; esse endereço reabre a música.

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
- Testar com MIDI real antes de considerar pronto: um arquivo de música de videogame (3 a 4 faixas) e um arranjo de banda (6 a 8 faixas) cobrem os dois extremos. `musicas/exemplos` tem os dois casos e um Guitar Pro.
