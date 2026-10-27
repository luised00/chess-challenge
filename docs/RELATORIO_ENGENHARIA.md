# Relatório de Engenharia — Motor SunTzu

**Evento:** Chess Challenge III ICEV 2026  
**Base:** Stockfish 19 (`upstream-base`, commit `edb0d9db6731067ec50ce619ff372b463bc4dd5d`)  
**Comando de auditoria:** `git diff upstream-base..v1.0 --stat`

---

## 1. Arquitetura e Metodologia de Testes

Toda modificação no motor **SunTzu** segue três regras de engenharia:
1. **Controlável por opção UCI:** pode ser ligada/desligada em tempo de execução para isolar seu efeito.
2. **Testada estatisticamente:** validada com `fastchess` (SPRT e cálculo de pontuação 3-1-0 via `tests/score_310.py`).
3. **Fallback seguro:** qualquer falha de arquivo externo (livro ou tablebases) reverte silenciosamente para o comportamento padrão do Stockfish 19, garantindo zero crashes.

---

## 2. Registro de Contribuições e Testes

### 2.1 Fase 1 — Setup, Build PGO e Infraestrutura SPRT
- **Objetivo:** Importar base limpa (`sf_19`), configurar builds `native` (PGO) e `x86-64-avx2` e validar pipeline de testes.
- **Arquivos:** `src/misc.cpp`, `scripts/build.sh`, `tests/sprt.sh`, `tests/score_310.py`.
- **Resultados:**
  - Assinatura (`bench`) idêntica à base: `2497913` nós (~1.35 MN/s em 1 thread).
  - Teste de sanidade do pipeline (`suntzu-native` vs `sf-base`, 40 partidas rápidas em `UHO.epd`): 0 crashes, 0 lances ilegais, `score_310.py` validado (`V=13 E=19 D=8 | pontos 3-1-0: 58 x 43`, Elo dentro da margem estatística de 0).

### 2.2 Fase 2 — Gestão de Tempo Físico e Ponder
- **Problema:** Descontar de 5 a 8 s por lance de operação humana no tabuleiro físico sem estourar os 25 min *sudden death*.
- **Solução:** Modelo `PhysicalBoardOverhead` (padrão 7000 ms) + `PanicReserve` (padrão 120 s) + `TimeProfile` (`normal`/`rapido`) + horizonte dinâmico por material e número do lance + corte de tempo em lances forçados/dominantes.
- **Arquivos:** `src/timeman.cpp`, `src/timeman.h`, `src/engine.cpp`, `src/search.cpp`, `tests/lag_proxy.py`, `tests/test_timeman_ponder.py`.
- **Resultados:**
  - **Teste escalado com atraso físico (`lag_proxy.py`, `tc=15+0`, `H=70 ms`, `R=12 s`, 40 partidas):** **0 derrotas por tempo** (contra 5 quedas de seta antes da calibração dos tetos de pânico em múltiplos de $H$).
  - **Teste de força sem atraso (`suntzu-native` vs `sf-base`, 60 partidas `2+0.02`):** Elo `-29.02 +/- 49.04` (dentro da margem estatística de 0 Elo, `LLR: -0.14` em `[-2.94, 2.94]`), 0 crashes.
  - **Testes de resposta rápida e Ponder (`tests/test_timeman_ponder.py`):** `go ponder` → `ponderhit` e `stop` validados; lance legal único respondido em `51.0 ms`; reserva de pânico crítico (< 60 s) respondendo em `1.3 ms`.

### 2.3 Fase 3 — Livro Polyglot com Pesos 3-1-0
- **Problema:** Responder instantaneamente na abertura escolhendo linhas que maximizam $3V + E$ e evitando variantes conhecidas de empate rápido.
- **Solução:** Leitor Polyglot nativo em `src/book.cpp` (tabela Zobrist de 781 chaves de 64 bits + busca binária em memória + validação estrita contra `MoveList<LEGAL>`), script gerador `tools/book_builder.py` com pesos $3V + E$ e filtro `books/evitar.txt`.
- **Arquivos:** `src/book.h`, `src/book.cpp`, `src/position.h`, `src/position.cpp`, `src/search.cpp`, `src/engine.cpp`, `src/uci.cpp`, `tools/book_builder.py`, `tests/book_keys_test.py`, `books/suntzu_310.bin`, `books/evitar.txt`, `books/ORIGEM.md`.
- **Resultados:**
  - **Conferência de chaves (`tests/book_keys_test.py`):** **1000/1000 (100.0%)** posições aleatórias e especiais (incluindo peão en passant cravado) idênticas a `chess.polyglot.zobrist_hash` do `python-chess`.
  - **Tempo de resposta:** média de **0.044 ms** e máximo de **0.082 ms** por lance do livro (meta < 5 ms).
  - **Robustez:** arquivo ausente e arquivo corrompido testados — motor emite `info string` e joga normalmente sem crash.
  - **Match SPRT (`OwnBook=true` com `suntzu_310.bin` vs `sf-base`, 60 partidas `2+0.02`):** `Elo: -5.79 +/- 37.74` (`V=5 E=49 D=6 | pontos 3-1-0: 64 x 67`), economizando tempo de relógio nos primeiros 16 meios-lances com 0 crashes.

### 2.4 Fase 4 — Modelo do Oponente e Aversão ao Empate
- **Problema:** Calibrar o valor do empate para a regra 3-1-0 conforme a força estimada do oponente.
- **Solução:** Classificador online em `src/suntzu.cpp` + valor dinâmico de empate em `src/search.cpp`.
- **Resultados:** *(preencher na Fase 4)*

### 2.5 Fase 5 — Modos Pressão, Virada, Conversão e Syzygy
- **Problema:** Desempatar lances quase equivalentes na raiz conforme o estado da partida.
- **Solução:** Seleção na raiz em `src/suntzu.cpp` + integração Syzygy 3-4-5 peças.
- **Resultados:** *(preencher na Fase 5)*

### 2.6 Fase 6 — Console do Operador e Testes de Estresse
- **Problema:** Eliminar erros humanos de digitação, perda de estado ou travamento durante o torneio.
- **Solução:** Console em `tools/operator_console/` com watchdog, autosave FEN/PGN e alertas de regra (repetição tripla / 50 lances).
- **Resultados:** *(preencher na Fase 6)*

---

## 3. Experimentos Rejeitados

- **Horizonte dinâmico agressivo ($N \in [12, 42]$) sem piso de múltiplos de $H$ (Fase 2):** Na primeira calibração do `timeman.cpp`, estimar $N$ abaixo de 20 lances no final da partida fazia o motor consumir a reserva e sofrer *time forfeit* quando partidas empatadas se estendiam além do lance 80 com atraso fixo $H$ por lance. Foi substituído por um piso conservador ($N \in [28, 52]$) combinado com gatilhos de pânico em $36H$, $22H$ e $15H$, reduzindo as quedas de seta de 5/30 para **0/40**.
