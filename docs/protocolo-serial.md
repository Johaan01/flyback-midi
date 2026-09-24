# Protocolo serial para o ESP32

O `index.html` envia pela Web Serial API os segmentos monofônicos de cada canal, os
mesmos `ch[i].segs` que alimentam a síntese. O firmware só precisa enfileirar e
executar no instante certo. Não há firmware escrito ainda; este é o contrato que o
lado do navegador já cumpre.

## Transporte

- Web Serial, 8N1, sem controle de fluxo. Velocidade escolhida na página:
  115200 (padrão), 230400, 460800 ou 921600.
- Texto ASCII, uma mensagem por linha, terminada em `\n`.
- Funciona em Chrome e Edge no computador. Safari e Firefox não têm Web Serial; no
  celular depende do navegador, e a página avisa quando não há suporte.

## Mensagens

| Linha | Significado |
|---|---|
| `R` | Zera o relógio: o instante em que a linha chega é t = 0. Esvazia as filas. |
| `N c t f` | No instante `t` ms, o canal `c` passa a tocar `f` Hz. |
| `F c t` | No instante `t` ms, o canal `c` silencia. |
| `X` | Silencia todos os canais agora e esvazia as filas. |

- `c` é o índice do canal: `0` esquerdo, `1` direito. O formato já comporta até 6.
- `t` é inteiro, em milissegundos desde o último `R`.
- `f` tem duas casas decimais, por exemplo `440.00`. A oitava escolhida na página
  já vem aplicada.
- Duas notas seguidas no mesmo canal chegam como dois `N` sem `F` entre eles.
  O `F` só aparece quando há silêncio de verdade.

## Tempo

- A página manda cada evento cerca de 100 ms antes do instante `t`. O firmware
  deve manter uma fila por canal, ordenada por `t`.
- Evento com `t` já passado executa na hora.
- Tocar, pular para outro ponto ou retomar depois de pausar gera `R` e recomeça a
  contagem. Pausar ou parar gera `X`.
- Com a aba em segundo plano o navegador atrasa os temporizadores e os eventos
  podem chegar tarde. Deixe a página visível enquanto toca.

## Exemplo

Início do Korobeiniki no acervo, canal esquerdo no baixo e direito na melodia:

```
X
R
N 0 49 82.41
N 1 49 659.26
F 0 239
N 0 249 164.81
F 0 439
F 1 439
```

## Recepção no firmware, em esboço

```c
// uma linha por vez, já sem o '\n'
switch (linha[0]) {
  case 'R': t0 = millis(); limpa_filas(); break;
  case 'X': silencia_todos(); limpa_filas(); break;
  case 'N': sscanf(linha + 2, "%d %lu %f", &c, &t, &f); enfileira(c, t0 + t, f); break;
  case 'F': sscanf(linha + 2, "%d %lu", &c, &t);        enfileira(c, t0 + t, 0); break;
}
```

A seção 3.16 de `hardware-decisoes.md` explica por que a geração da nota no ESP
deve habilitar o gerador do MCPWM, ou contar pulsos, em vez de alternar o GPIO.
