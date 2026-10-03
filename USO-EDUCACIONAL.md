# Uso educacional e atribuição

Este repositório guarda o software e o acervo de um projeto de eletrônica de potência:
**alto-falantes de plasma**, em que o arco elétrico de um transformador flyback é modulado
para reproduzir som. As páginas web daqui são a fonte de áudio desse aparelho, e o acervo de
MIDI existe para alimentá-lo durante o estudo e a demonstração do princípio físico.

A finalidade é **educacional e de divulgação científica, sem fins lucrativos**. O material não
é reproduzido em rádio, em transmissão ao vivo, em evento pago nem em qualquer contexto
monetizado, e o repositório não tem publicidade, patrocínio, assinatura ou botão de doação.

## O acervo tem quatro origens, com situações diferentes

### 1. `musicas/classicos` — domínio público e licença livre

Vêm do [Mutopia Project](https://www.mutopiaproject.org/), que publica partituras de obras em
domínio público tipografadas por voluntários. Cada arquivo traz, em `creditos.json`, o
compositor, quem fez a tipografia, a licença (domínio público, CC BY ou CC BY-SA) e o endereço
de origem. O site mostra esse crédito junto da música, que é exatamente o que as licenças
Creative Commons exigem.

Aqui não há restrição nenhuma de uso além de manter a atribuição.

### 2. `musicas/rock e metal` — composições do próprio projeto

Escritas por este projeto, em `tools/compor_rock.py`, a partir de temas em domínio público ou
de material original. São livres para qualquer uso.

### 3. `musicas/bandas` — transcrições de obras protegidas

**Esta pasta é diferente das outras e merece ser lida com atenção.**

São transcrições MIDI feitas por fãs, de músicas cuja composição **continua protegida por
direito autoral**. Estão aqui porque uma demonstração de alto-falante de plasma só comunica
alguma coisa quando toca algo que a pessoa reconhece: a graça do experimento é ouvir uma
melodia conhecida saindo de um arco elétrico, e não um sinal de teste.

O que este repositório faz a respeito:

- **Atribui a autoria.** Cada arquivo registra, em `musicas/bandas/creditos.json`, o artista e
  a banda responsáveis pela composição, e o transcritor quando ele é identificável. O site
  mostra esse crédito ao abrir a música.
- **Declara a finalidade.** Estudo e demonstração do princípio físico, sem fins lucrativos.
- **Não monetiza.** Nem o repositório, nem o site publicado, nem as demonstrações.
- **Não distribui gravação.** São arquivos MIDI — listas de notas —, não fonogramas. Nenhuma
  gravação de nenhum artista é reproduzida ou distribuída aqui.

E o que ele **não** faz, para não dar margem a engano:

> Atribuir autoria **não substitui licença**. Creditar quem compôs é obrigação independente, e
> cumpri-la não torna a cópia autorizada. A lei brasileira (Lei 9.610/98) não tem uma cláusula
> geral de *fair use*: o artigo 46 permite a reprodução de **pequenos trechos**, para uso
> privado de quem copia e sem intuito de lucro, o que é mais estreito do que a redistribuição
> de uma obra inteira num repositório público. Quem usa este material assume essa avaliação.

### 4. `musicas/transcritas` — obras protegidas, transcritas por máquina

Mesma situação da pasta `bandas` quanto à composição: **a obra continua protegida**, e tudo o que
está escrito ali acima vale igual aqui, inclusive a ressalva de que atribuir autoria não substitui
licença.

A diferença é de onde vem o arquivo. Não há transcritor humano: o MIDI foi gerado a partir da
gravação por um modelo de transcrição automática, o [MuScriptor](https://github.com/muscriptor/muscriptor),
da Kyutai com a Mirelo. Então o crédito de transcrição nomeia o modelo, não uma pessoa, e isso
está escrito arquivo por arquivo em `musicas/transcritas/creditos.json`.

Duas consequências que vale deixar explícitas:

- **O resultado é derivado da gravação, não de uma partitura.** O modelo ouviu o fonograma para
  produzir a lista de notas. Nenhuma gravação é distribuída aqui — o que sai é MIDI —, mas a
  cadeia passa pelo fonograma, e não só pela composição.
- **Os pesos do modelo são CC BY-NC 4.0**, isto é, não comerciais. Isso restringe o uso do
  próprio modelo, não destes arquivos, e é compatível com a finalidade declarada aqui; mas quem
  reaproveitar a ferramenta para outro fim precisa olhar essa licença.

## Pedido de remoção

Se você detém direitos sobre alguma obra aqui e quer que ela saia, **abra uma issue ou um pull
request** neste repositório, ou escreva pelo perfil do GitHub do mantenedor. A remoção é feita
sem discussão e sem exigir formalidade nenhuma — basta identificar a obra. O mesmo vale para
transcritores que não querem seu trabalho redistribuído, ou que querem ser creditados pelo
nome.

Para apagar uma música do acervo e do site basta remover o arquivo da pasta `musicas` e enviar
a alteração: o índice é regerado a cada publicação.

## Para quem for reaproveitar este projeto

O **código** (as páginas HTML, os scripts em `tools/`) e a **documentação** são do projeto e
podem ser reaproveitados. O **acervo** não é homogêneo: `classicos` e `rock e metal` você pode
levar junto, respeitada a atribuição; `bandas` é decisão sua, feita com consciência do que está
escrito acima.

A ferramenta `tools/baixar_bandas.py` apenas automatiza o acesso a sites públicos que já
distribuem essas transcrições abertamente. Ela não quebra proteção, não burla autenticação e
não contorna limite de acesso — e trabalha devagar de propósito, com uma chamada por segundo e
identificação no `User-Agent`, porque são sites pequenos mantidos por uma pessoa só.
