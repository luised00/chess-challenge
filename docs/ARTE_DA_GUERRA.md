# Módulo "Arte da Guerra" — Princípios, Algoritmos e Resultados

Este documento mapeia cada princípio estratégico de *A Arte da Guerra* (Sun Tzu) para sua implementação técnica no motor **SunTzu**, as opções UCI correspondentes e os resultados medidos em testes automatizados.

---

## Resumo Geral

| Princípio Sun Tzu | Algoritmo / Componente | Arquivos | Opções UCI | Resultado Medido |
| --- | --- | --- | --- | --- |
| *"A velocidade é a essência da guerra"* | Gestão de tempo para tabuleiro físico, reserva de pânico e ponder | `src/timeman.cpp`, `src/search.cpp` | `PhysicalBoardOverhead`, `PanicReserve`, `TimeProfile` | **0 quedas de seta** (40/40 partidas com overhead simulado); lance único em 51 ms; pânico (<60s) em 1.3 ms; Elo neutro sem atraso |
| *"Escolha o terreno"* | Livro Polyglot `.bin` nativo com pesos 3-1-0 ($3V + E$) | `src/book.cpp`, `src/book.h`, `tools/book_builder.py` | `OwnBook`, `BookFile`, `BookDepth`, `BookVariety` | **1000/1000 chaves** idênticas ao `python-chess`; resposta em **0.044 ms** (< 5 ms); fallback seguro testado |
| *"Conhece o teu inimigo e conhece-te a ti mesmo"* | Modelo online do oponente por perda média de centipeões (EMA) | `src/suntzu.cpp`, `src/suntzu.h` | `SunTzu`, `OpponentProfile` | *(Fase 4)* |
| *"Na guerra, o objetivo é a vitória, não a campanha prolongada"* | Aversão dinâmica ao empate calibrada para pontuação 3-1-0 | `src/search.cpp`, `src/suntzu.cpp` | `DrawAversion` | *(Fase 4)* |
| *"Ataque onde ele não está preparado"* | Modo Pressão (medida de armadilha / unicidade da resposta adversária) | `src/suntzu.cpp`, `src/search.cpp` | `PressureMargin` | *(Fase 5)* |
| *"Quando fraco, pareça forte"* | Modo Virada (*Swindle*: evita simplificações e mantém complexidade) | `src/suntzu.cpp`, `src/search.cpp` | `SwindleMode` | *(Fase 5)* |
| *"Não encurrale um inimigo desesperado"* | Modo Conversão + Tablebases Syzygy de 3-4-5 peças | `src/suntzu.cpp`, `src/search.cpp` | `ConvertMode`, `SyzygyPath` | *(Fase 5)* |

---

## 1. "A velocidade é a essência da guerra" — Gestão de Tempo Físico (Fase 2)

- **Problema:** Em partidas de 25 min *sudden death* jogadas em tabuleiro físico, a operação humana (ler o lance adversário, digitar no console, ler a resposta, mover a peça no tabuleiro e acionar o relógio) consome de 5 a 8 segundos por lance (~9 minutos em 80 lances).
- **Algoritmo:**
  $$t_{\text{base}} = \frac{T - R - N \cdot H}{N}$$
  onde $T$ é o tempo restante, $R$ é a reserva de pânico (`PanicReserve`), $H$ é o tempo de operação física (`PhysicalBoardOverhead`) e $N$ é o número estimado de lances restantes em função do material e do número do lance.
- **Arquivos:** `src/timeman.cpp`, `src/timeman.h`, `src/search.cpp`.

---

## 2. "Escolha o terreno" — Livro de Aberturas Polyglot 3-1-0 (Fase 3)

- **Problema:** O Stockfish não possui livro de aberturas interno, gastando tempo de relógio desde o lance 1 e podendo entrar em variantes teóricas de empate.
- **Algoritmo:** Implementação nativa do hash Zobrist Polyglot (781 chaves) e busca binária em arquivo `.bin`, com pesos gerados pela fórmula:
  $$\text{peso} = 3 \cdot \text{vitórias} + \text{empates}$$
- **Arquivos:** `src/book.h`, `src/book.cpp`, `tools/book_builder.py`, `tests/book_keys_test.py`.

---

## 3. "Conhece o teu inimigo" & Regra 3-1-0 — Modelo do Oponente e Aversão ao Empate (Fase 4)

- **Problema:** Na pontuação 3-1-0, três empates (3 pts) valem o mesmo que uma única vitória e duas derrotas (3 pts). Contra motores mais fracos, aceitar empates prematuros desperdiça valor esperado.
- **Algoritmo:**
  - Calcula a perda por lance do oponente $\Delta = \max(0, S_2 - S_1)$ (limitada a 300 cp) e mantém média móvel exponencial para classificar o adversário em **forte** ($< 15$ cp), **médio** ($15\text{–}50$ cp) ou **fraco** ($> 50$ cp).
  - Ajusta o valor de empate na busca para $-D$ centipeões sempre que $3 \cdot P(\text{vitória}) + P(\text{empate}) > 1$.
- **Arquivos:** `src/suntzu.h`, `src/suntzu.cpp`, `src/search.cpp`.

---

## 4. Seleção Tática na Raiz — Pressão, Virada e Conversão (Fase 5)

- **Algoritmo:** Entre os lances candidatos na raiz dentro de uma margem segura de centipeões do melhor lance:
  - **Pressão (`PressureMargin`):** Avalia as respostas do oponente em profundidade curta para medir a nitidez/armadilha da posição e induzir erros humanos ou de motores mais fracos.
  - **Virada (`SwindleMode`):** Quando abaixo de $-150$ cp, penaliza trocas de peças e finais simplificados.
  - **Conversão (`ConvertMode`):** Quando acima de $+300$ cp, prioriza simplificação segura e redução de contrajogo (xeques/ameaças).
- **Arquivos:** `src/suntzu.h`, `src/suntzu.cpp`, `src/search.cpp`.
