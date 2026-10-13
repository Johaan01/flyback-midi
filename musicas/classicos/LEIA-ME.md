# Clássicos orquestrais

Esta pasta guarda só obras conhecidas com **6 partes ou mais**, para que os seis flybacks tenham
o que tocar. Até outubro de 2026 eram 590 peças do Mutopia, quase todas de piano ou de um
instrumento solo (218 com duas partes, 127 com uma), e o dono do projeto pediu para tirá-las:
ficavam simples demais para seis canais, e a maior parte nunca foi usada. Saíram 569.

Ficaram duas fontes:

| Fonte | Peças | Licença |
|---|---|---|
| [Mutopia Project](https://www.mutopiaproject.org) — partituras em LilyPond, MIDI gerado delas | 21: Brandemburgo 1, 2 e 5, 5ª de Beethoven, Coriolano, Aleluia, Flauta Mágica, Dies Irae, Anitra, Novo Mundo, concerto para violino de Tchaikovsky | domínio público, CC BY ou CC BY-SA |
| [PDMX](https://zenodo.org/records/15571083) (Long et al., 2024) — partituras do MuseScore marcadas pelo autor como domínio público | 44: Ode à Alegria, 9ª, 7ª e 6ª de Beethoven, 40ª de Mozart, Pequena Serenata, Lacrimosa, Bodas de Fígaro, Vivaldi, Quebra-Nozes, Lago dos Cisnes, Guilherme Tell, Danúbio Azul, Os Planetas, Carmen, Boléro, Cânone, Verdi, Puccini e outras | domínio público ou CC0; o dataset é CC BY 4.0 |

O crédito de cada arquivo (compositor, instrumentos, licença, quem fez a partitura e o endereço
dela no Mutopia ou no MuseScore) está em `creditos.json` e aparece no site, logo abaixo de
"Faixas encontradas", quando a música é aberta.

- `tools/baixar_pdmx.py` traz a seleção do PDMX; a lista de obras está nele, escolhida à mão
  (a partitura de mais favoritos de cada obra que seja para orquestra, e não banda marcial ou
  coro de clarinetes). Para acrescentar uma obra, acrescente uma linha em `SELECAO`.
- `tools/baixar_mutopia.py` baixa o Mutopia inteiro. **Não rode sem querer:** ele traria de volta
  as 569 peças de piano e solo que saíram.

No Mutopia, uma obra com vários movimentos vira um arquivo por movimento, numerado (`- 01`,
`- 02`…).
