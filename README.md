# Flyback MIDI

Fonte de áudio para alto-falantes de plasma: arcos elétricos de transformadores flyback que
reproduzem som. Duas páginas, cada uma um arquivo único, sem build.

| Arquivo | O que faz |
|---|---|
| `index.html` | Abre MIDI ou Guitar Pro, roteia cada faixa de instrumento para um canal, sintetiza onda quadrada |
| `stems.html` | Carrega dois arquivos de áudio separados e toca um em cada canal |

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

A pasta `musicas/exemplos` tem três arquivos de teste: Korobeiniki (chiptune em MIDI formato 0),
Ode à Alegria (arranjo de banda com 7 faixas e configuração pronta) e um riff em Guitar Pro.
Apague quando tiver as suas.

## Testar no computador antes de publicar

    python tools/servir.py

Abre em `http://localhost:8000`. O script mostra também um endereço para abrir no celular, na
mesma rede Wi-Fi. Abrir o `index.html` com duplo clique funciona, mas sem o acervo.

## Documentação

`CLAUDE.md` tem o contexto de projeto e as decisões de implementação.
`docs/` tem o registro de decisões do hardware e o protocolo serial.
