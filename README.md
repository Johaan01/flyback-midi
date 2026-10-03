# Flyback MIDI

Fonte de áudio para alto-falantes de plasma: arcos elétricos de transformadores flyback que
reproduzem som. Duas páginas, cada uma um arquivo único, sem build.

| Arquivo | O que faz |
|---|---|
| `index.html` | Abre MIDI ou Guitar Pro, roteia cada faixa de instrumento para um flyback, sintetiza onda quadrada. Dois flybacks pelo P2 ou até seis por um ESP32 |
| `tom.html` | Gerador de tom: frequência livre no slider, forma de onda à escolha e varredura, um tom por canal |

Cada canal de saída corresponde a um flyback. Como o arco é monofônico, acordes são reduzidos
a uma nota por vez, e a separação entre os canais é dura.

A página é feita para o computador, como uma interface de editor: as faixas da música em cima à
esquerda, uma pista por flyback tocando em cima à direita, e embaixo, lado a lado, o acervo, um
mixer com um módulo por canal e o painel da saída.

## O que o site faz

- **Duas saídas.** **Estéreo · P2**: dois flybacks pelo cabo de áudio, esquerdo e direito.
  **ESP32 · serial**: de 1 a 6 flybacks, um por pino de um ESP32 — escolha quantos, a placa e o
  pino de cada canal, e use "testar" para achar qual flyback é qual. Cada modo guarda seu próprio
  roteamento.
- **Um instrumento por flyback.** No modo ESP, o preset padrão põe a voz no canal 1, o baixo no
  2 e os outros instrumentos um por canal, deixando a bateria de fora. É feito para os MIDIs
  separados por instrumento que o MuScriptor gera.
- **Acervo online.** Tudo que estiver na pasta `musicas/` aparece como lista no site, pronto
  para tocar. Subpastas viram grupos.
- **MIDI e Guitar Pro.** `.mid`, `.gp3`, `.gp4`, `.gp5`, `.gpx`, `.gp` e MusicXML abrem direto,
  do acervo ou do aparelho. MIDI formato 0 é separado por canal.
- **Configuração por música.** O roteamento e os ajustes de cada canal ficam salvos no aparelho.
  "Baixar configuração" gera um `.json` que, enviado junto com a música, deixa ela pronta para
  qualquer aparelho.
- **WAV.** Renderiza a música com um canal do arquivo por flyback — estéreo para o P2, ou N
  canais para uma interface de áudio multicanal —, para tocar sem navegador.
- **Meus arquivos.** "Adicionar MIDI deste aparelho" guarda os arquivos no navegador e os mostra
  no acervo como uma pasta à parte, tocando pelo mesmo player e com os mesmos presets. Ficam só
  neste aparelho: não sobem para o repositório nem para lugar nenhum.
- **Gerador de tom.** Um tom contínuo por canal, com slider logarítmico de 20 Hz a 20 kHz que
  desliza sem degrau, senoide/quadrada/triangular/dente de serra, varredura automática entre
  dois limites e intervalos prontos entre os dois flybacks (uníssono, oitava, quinta, batimento
  de 1 Hz). Serve para achar a ressonância do arco e casar o par.
- **Saída serial para ESP32.** Chrome ou Edge. Protocolo em `docs/protocolo-serial.md`. O painel
  "Linhas enviadas" mostra o que vai para a porta, também sem ESP ligado.
- **Mixer.** Cada canal tem silenciar e solo, ganho, passa-baixa, oitava, que nota tirar do
  acorde, envelope e dinâmica.
- **Atalhos.** Espaço toca e pausa, setas andam 5 s, Home volta ao início. Arrastar um arquivo
  para a janela abre.
- **Sem internet.** Funciona sem conexão depois da primeira visita. Em tela pequena os painéis
  empilham.
- **Link direto.** Ao abrir uma música do acervo, o endereço muda para `?m=...`; esse link abre a
  mesma música em outro aparelho.

## Publicar no GitHub Pages

Precisa de Git e GitHub CLI (`winget install Git.Git` e `winget install GitHub.cli`). Na pasta do
projeto:

    tools\publicar.cmd

Na primeira vez o navegador abre para você entrar no GitHub. O script cria o repositório público
`flyback-midi`, envia os arquivos, liga o Pages pelo GitHub Actions e mostra o endereço:
`https://SEU-USUARIO.github.io/flyback-midi/`. Rodar de novo envia as mudanças.

Sem o script, pelo site do GitHub: crie o repositório, envie os arquivos e, em
Settings → Pages → Source, escolha **GitHub Actions**.

## Adicionar músicas

Pelo celular ou pelo computador, sem instalar nada:

1. No site publicado, toque em **Enviar música para o acervo**. Abre a página de envio do GitHub
   já na pasta `musicas`.
2. Escolha os arquivos `.mid` ou `.gp` e confirme em **Commit changes**.
3. Em cerca de um minuto o GitHub Actions republica e a música aparece no acervo.

Para deixar uma música já roteada, ajuste no site, toque em **Baixar configuração** e envie o
`.json` para a mesma pasta, com o mesmo nome da música. No acervo ela aparece como "pronta".

Pelo computador, também dá para copiar os arquivos para `musicas/` e rodar `tools\publicar.cmd`.

## O que já vem no acervo

1.889 músicas em cinco acervos:

| Pasta | Conteúdo |
|---|---|
| `bandas` | 718 transcrições de rock, metal e pop, **uma pasta por artista** — 110 deles, de AC/DC a ZZ Top. Obras protegidas: leia `USO-EDUCACIONAL.md` |
| `classicos` | 590 peças do [Mutopia Project](https://www.mutopiaproject.org), em domínio público ou Creative Commons, por região de origem do compositor: Alemanha e Áustria (217), Itália (82), França (74), Rússia e Leste Europeu (67), Américas (41), Tradicional e anônimo (31), Ibéria e América Latina (31), Nórdicos e Países Baixos (24) e Ilhas Britânicas (23) |
| `folk russo` | 45 canções tradicionais e soviéticas — Kalinka, Katyusha, Korobeiniki, Ochi Chornye, Troika, Kamarinskaya, Kazachok, Podmoskovnye Vechera. Quase todas em domínio público; as de autor conhecido e ainda protegido estão marcadas uma a uma |
| `transcritas` | 5 MIDIs gerados do áudio pelo MuScriptor, com uma faixa por instrumento — voz, guitarra, baixo, teclas e bateria em faixas separadas. Obras protegidas, transcritor automático: leia `USO-EDUCACIONAL.md` |
| `exemplos` | 10 arranjos de temas em domínio público feitos para os dois flybacks (Grieg, Bach, Beethoven, Pachelbel, Greensleeves, Korobeiniki), mais Ode à Alegria e um riff em Guitar Pro |

A navegação no site é em duas peças: **botões** escolhem o acervo e um **seletor** mostra o que
há dentro dele — o artista, ou o compositor agrupado por região. Chegar no AC/DC são dois
toques. Há ainda busca por título, artista, compositor, instrumento ou estilo, um botão
**só as mais ouvidas** que reduz o acervo às 60 músicas mais conhecidas, e um para sortear.
O crédito exigido pelas licenças aparece ao abrir cada peça.

### A linha de canto

Transcrição de rock sem vocal soa pobre no flyback: toca só o acompanhamento, e falta o que a
pessoa reconhece. Como não dá para ouvir centenas de arquivos um a um, o acervo mede isso
sozinho — `tools/curar_acervo.py` acha a faixa que se comporta como linha de canto (uma voz só,
registro de voz, presente ao longo da música, nome e instrumento compatíveis) e grava o veredito
no `creditos.json`.

No site, cada linha da lista ganha o marcador **· vocal**, e o botão **só com vocal** reduz o
acervo ao que tem canto. Ao abrir a música, o crédito diz qual faixa é a voz.

Isso também decide qual transcrição fica: o acervo Lakh costuma ter três ou quatro versões da
mesma música e normalmente só uma traz o vocal. Em *Highway to Hell*, por exemplo, a versão de
13 faixas parece mais completa mas não tem canto nenhum, e perde para a de 5 faixas que tem.

### As ferramentas que mantêm o acervo

| Ferramenta | O que faz |
|---|---|
| `tools/compor_rock.py` | Gera os arranjos de `musicas/exemplos` |
| `tools/baixar_mutopia.py` | Baixa os clássicos do Mutopia; rodado de novo, traz só as peças novas |
| `tools/curar_acervo.py` | Enxuga e reorganiza `classicos` por região e compositor. O download bruto traz 4.867 arquivos, a maior parte método, estudo e parte de instrumento solta; a ferramenta mede quanto de cada peça sobrevive à redução a dois canais monofônicos e deixa o repertório que se reconhece |
| `tools/baixar_bandas.py` | Baixa transcrições de midiworld, zeppelinmidi, maidenmidi, do acervo Lakh (via rawl.rocks) e do folk russo do FreeSheetMusic |
| `tools/organizar_bandas.py` | Identifica, tira repetidas, mede a linha de canto e ordena `bandas` pelo quanto a música é conhecida, com Wikipedia e ListenBrainz |
| `tools/transcrever.py` | Gera MIDI a partir de uma gravação, em faixas separadas por instrumento. Opcional, e a única ferramenta que precisa de pacotes além da biblioteca padrão |

O caminho completo para acrescentar músicas de banda é:

    python tools/baixar_bandas.py --baixar
    python tools/organizar_bandas.py --aplicar
    python tools/gerar_acervo.py

Para largar arquivos à mão em vez de baixar, aponte a origem:

    python tools/organizar_bandas.py --origem "musicas/unsorted" --aplicar

Para buscar versões melhores — com vocal — de artistas específicos no acervo Lakh:

    python tools/baixar_bandas.py --fonte lakh --destino "musicas/lakh (unsorted)" \
        --busca journey "bon jovi" eagles --baixar
    python tools/organizar_bandas.py --origem "musicas/lakh (unsorted)" --aplicar

Todas as versões de cada música são baixadas com sufixo `(vN)`; o organizador junta as versões,
pontua a linha de canto e guarda só a melhor.

E o acervo de folk russo, que é plano e sem artista:

    python tools/baixar_bandas.py --fonte folkrusso --destino "musicas/folk russo (unsorted)" --baixar
    python tools/organizar_bandas.py --origem "musicas/folk russo (unsorted)" \
        --destino "musicas/folk russo" --plano --artista "Tradicional russo" --aplicar

Nenhuma delas mexe em nada sem `--baixar` / `--aplicar`: sem a opção, só mostram o que fariam.
`musicas/pastas.txt` define a ordem das pastas.

### Gerar MIDI de uma gravação

Quando não existe transcrição boa de uma música, dá para fazer uma a partir do áudio:

    python tools/transcrever.py --url "https://..." --instrumentos seis --saida "musicas/transcritas"

Sai um MIDI com uma faixa por instrumento — voz, guitarra, violão, piano, baixo e bateria — que
é o que o site precisa para mandar cada instrumento a um flyback. `--instrumentos` escolhe quais
grupos decodificar; sem ele o modelo decide.

Isso usa o [MuScriptor](https://github.com/muscriptor/muscriptor), da Kyutai com a Mirelo. O
código é MIT, mas **os pesos são CC BY-NC 4.0 e pedem licença aceita numa conta do HuggingFace**:

1. Aceite em [huggingface.co/MuScriptor/muscriptor-medium](https://huggingface.co/MuScriptor/muscriptor-medium)
   (o acesso é liberado na hora).
2. `hf auth login`, ou exporte `HF_TOKEN`.

Sem isso, `--motor stems` faz o mesmo por outro caminho — separa a gravação em voz, baixo e
harmonia e rastreia a altura de cada um — com três faixas em vez de seis e sem depender de pesos
sob licença. `--guardar` deixa os stems em disco e `--stems` retoma deles, porque a separação é a
parte lenta e a única que precisa de GPU.

Baixar do YouTube contraria os termos de uso do serviço; quem roda responde pelo uso.

### Direito autoral

`classicos`, `exemplos` e quase todo o `folk russo` são domínio público, licença livre ou arranjo
do próprio projeto: use à vontade, mantida a atribuição.

`bandas` e `transcritas` são diferentes — são transcrições de obras ainda protegidas, mantidas aqui
com atribuição ao artista e ao transcritor, para estudo e demonstração do princípio físico, sem fins
lucrativos. Em `transcritas` o transcritor é um modelo, não uma pessoa, e o crédito diz isso.
Algumas poucas do `folk russo` também são (Katyusha, de Blanter, é de 1938), e estão marcadas
individualmente no `creditos.json` da pasta.
**Leia [`USO-EDUCACIONAL.md`](USO-EDUCACIONAL.md)** antes de reaproveitar essa pasta: ele explica a
finalidade, o que a atribuição cobre e o que ela não cobre, e como pedir a remoção de uma obra.

## Testar no computador antes de publicar

    python tools/servir.py

Abre em `http://localhost:8000`. O script mostra também um endereço para abrir no celular, na
mesma rede Wi-Fi. Abrir o `index.html` com duplo clique funciona, mas sem o acervo.

Para conferir o player inteiro sem clicar à mão — os dois modos de saída, o roteamento, o WAV e
a serial com uma porta simulada — num Chrome ou Edge de verdade:

    pip install playwright
    python tools/testar_site.py --telas

## Documentação

`CLAUDE.md` tem o contexto de projeto e as decisões de implementação.
`docs/` tem o registro de decisões do hardware e o protocolo serial.
