# Flyback MIDI

Fonte de áudio para alto-falantes de plasma: arcos elétricos de transformadores flyback que
reproduzem som. Três páginas, cada uma um arquivo único, sem build.

| Arquivo | O que faz |
|---|---|
| `index.html` | Abre MIDI ou Guitar Pro, roteia cada faixa de instrumento para um canal, sintetiza onda quadrada |
| `stems.html` | Carrega dois arquivos de áudio separados e toca um em cada canal |
| `tom.html` | Gerador de tom: frequência livre no slider, forma de onda à escolha e varredura, um tom por canal |

Cada canal de saída corresponde a um flyback. Como o arco é monofônico, acordes são reduzidos
a uma nota por vez, e a separação entre os canais é dura.

## O que o site faz

- **Acervo online.** Tudo que estiver na pasta `musicas/` aparece como lista no site, pronto
  para tocar. Subpastas viram grupos.
- **MIDI e Guitar Pro.** `.mid`, `.gp3`, `.gp4`, `.gp5`, `.gpx`, `.gp` e MusicXML abrem direto,
  do acervo ou do aparelho. MIDI formato 0 é separado por canal.
- **Configuração por música.** O roteamento e os ajustes de cada canal ficam salvos no aparelho.
  "Baixar configuração" gera um `.json` que, enviado junto com a música, deixa ela pronta para
  qualquer aparelho.
- **WAV estéreo.** Renderiza a música com os dois canais separados, para tocar em qualquer player
  pelo cabo P2, sem navegador. A página de stems também exporta.
- **Gerador de tom.** Um tom contínuo por canal, com slider logarítmico de 20 Hz a 20 kHz que
  desliza sem degrau, senoide/quadrada/triangular/dente de serra, varredura automática entre
  dois limites e intervalos prontos entre os dois flybacks (uníssono, oitava, quinta, batimento
  de 1 Hz). Serve para achar a ressonância do arco e casar o par.
- **Saída serial para ESP32.** Chrome ou Edge no computador. Protocolo em `docs/protocolo-serial.md`.
- **Celular.** Controles grandes, barra de reprodução fixa, tela acesa enquanto toca, funciona sem
  internet depois da primeira visita e pode ser instalado na tela inicial.
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

| Pasta | Conteúdo |
|---|---|
| `bandas` | 711 transcrições de rock, metal e pop, em três níveis pelo quanto a música é conhecida: `mais ouvidas` (50), `conhecidas` (107) e `para fãs` (554). Obras protegidas — leia `USO-EDUCACIONAL.md` |
| `rock e metal` | 17 músicas prontas para os dois flybacks: 10 composições próprias (hard rock, thrash, heavy metal com guitarras gêmeas, punk, doom, prog em 7/8, death metal, power ballad, synthwave, chiptune) e 7 arranjos de temas em domínio público (Grieg, Bach, Beethoven, Pachelbel, Greensleeves, Korobeiniki) |
| `exemplos` | Korobeiniki (MIDI formato 0), Ode à Alegria (banda de 7 faixas) e um riff em Guitar Pro |
| `classicos` | 590 peças do [Mutopia Project](https://www.mutopiaproject.org), em domínio público ou Creative Commons, por região de origem do compositor: Alemanha e Áustria (217), Itália (82), França (74), Rússia e Leste Europeu (67), Américas (41), Tradicional e anônimo (31), Ibéria e América Latina (31), Nórdicos e Países Baixos (24) e Ilhas Britânicas (23) |

No site, o acervo tem filtro por pasta em dois níveis — dá para escolher só os russos, ou só as
mais ouvidas —, busca por título, compositor, instrumento ou estilo, e um botão para sortear uma
música. O crédito exigido pelas licenças aparece ao abrir cada peça.

### As ferramentas que mantêm o acervo

| Ferramenta | O que faz |
|---|---|
| `tools/compor_rock.py` | Gera `musicas/rock e metal` |
| `tools/baixar_mutopia.py` | Baixa os clássicos do Mutopia; rodado de novo, traz só as peças novas |
| `tools/curar_acervo.py` | Enxuga e reorganiza `classicos` por região e compositor. O download bruto traz 4.867 arquivos, a maior parte método, estudo e parte de instrumento solta; a ferramenta mede quanto de cada peça sobrevive à redução a dois canais monofônicos e deixa o repertório que se reconhece |
| `tools/baixar_bandas.py` | Baixa transcrições de midiworld, zeppelinmidi e maidenmidi para a pasta de entrada |
| `tools/organizar_bandas.py` | Identifica, tira repetidas e ordena `bandas` pelo quanto a música é conhecida, com Wikipedia e ListenBrainz |

O caminho completo para acrescentar músicas de banda é:

    python tools/baixar_bandas.py --baixar
    python tools/organizar_bandas.py --aplicar
    python tools/gerar_acervo.py

As duas primeiras não mexem em nada sem `--baixar` / `--aplicar`: sem a opção, só mostram o que
fariam. `musicas/pastas.txt` define a ordem das pastas.

### Direito autoral

`classicos` e `rock e metal` são domínio público, licença livre ou composição do próprio projeto:
use à vontade, mantida a atribuição.

`bandas` é diferente — são transcrições de obras ainda protegidas, mantidas aqui com atribuição ao
artista e ao transcritor, para estudo e demonstração do princípio físico, sem fins lucrativos.
**Leia [`USO-EDUCACIONAL.md`](USO-EDUCACIONAL.md)** antes de reaproveitar essa pasta: ele explica a
finalidade, o que a atribuição cobre e o que ela não cobre, e como pedir a remoção de uma obra.

## Testar no computador antes de publicar

    python tools/servir.py

Abre em `http://localhost:8000`. O script mostra também um endereço para abrir no celular, na
mesma rede Wi-Fi. Abrir o `index.html` com duplo clique funciona, mas sem o acervo.

## Documentação

`CLAUDE.md` tem o contexto de projeto e as decisões de implementação.
`docs/` tem o registro de decisões do hardware e o protocolo serial.
