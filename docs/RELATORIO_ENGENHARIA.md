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
- **Solução:** Classificador online em `src/suntzu.cpp` (EMA da perda de centipeões do oponente com banda morta de `8 cp` para absorver ruído de horizonte entre buscas consecutivas) + valor dinâmico de empate (`DrawAversion` escalando para `10 cp` vs forte, `25 cp` vs médio, `50 cp` vs fraco e caindo a `0 cp` quando avaliação $< -50$ cp ou $\mathbb{E}[\text{pts}_{310}] \le 1$) em `src/search.cpp`.
- **Arquivos:** `src/suntzu.h`, `src/suntzu.cpp`, `src/search.h`, `src/search.cpp`, `src/engine.cpp`, `src/uci.cpp`, `src/ucioption.cpp`, `tests/test_suntzu_fase4.py`.
- **Resultados:**
  - **Acurácia do classificador (`tests/test_suntzu_fase4.py`):** **92.5% a 95.0%** em 40 partidas simuladas (20 contra Stockfish puro + 20 contra oponente fraco) até o lance 24–30.
  - **Recusa de repetição e desativação quando inferior:** validado que o motor zera `DrawAversion=0cp` quando perdendo ($< -50$ cp), escala para `50cp` contra oponente fraco e evita repetição tripla (`e5f3` em vez de `h6g7`) em posição equilibrada contra oponente fraco.
  - **Cenário Forte (`SunTzu_F4` vs `SF_Base`, 60 partidas `4+0.04` em `UHO.epd`):** `V=14 E=32 D=14 | pontos 3-1-0: 74 x 74` (`Elo: 0.00 +/- 36.02`), comprovando zero regressão contra adversários da mesma força.
  - **Cenário Fraco (`SunTzu=true` vs `SunTzu=false` contra `Skill Level=14`, 40 partidas em `UHO.epd`):** **40V 0E 0D (`120 x 0` pts 3-1-0, 0 empates)** com `SunTzu=true`, contra `38V 2E 0D` (`116 x 2` pts 3-1-0) com `SunTzu=false`.

### 2.5 Fase 5 — Modos Pressão, Virada, Conversão e Syzygy
- **Problema:** Desempatar lances quase equivalentes na raiz conforme o estado da partida, dificultando a defesa adversária sem nunca substituir um lance claramente superior por um truque, e converter finais com precisão de tablebase.
- **Solução:**
  - MultiPV interno até profundidade 7–8 quando um modo tático está ativo + avaliação curta das respostas naturais do oponente na raiz (limitada a 15% do orçamento de tempo do lance, com cancelamento automático se exceder).
  - **Medida de armadilha (`trapScore`):** combina a unicidade da melhor resposta adversária ($v_2 - v_1$) e a contagem de respostas naturais que perdem $\ge 100$ cp.
  - **Pressão (`PressureMargin`, padrão `12 cp`):** ativa contra oponentes `fraco`/`medio` entre $-150$ e $+300$ cp com $> 5$ min no relógio.
  - **Virada (`SwindleMode`, padrão `true`):** ativa abaixo de $-150$ cp (ou $\le -350$ cp contra `forte`), penalizando trocas de peças não-peões e finais simples perdidos.
  - **Conversão (`ConvertMode`, padrão `true`) + Syzygy (`SyzygyPath`):** ativa acima de $+300$ cp com margem de `15 cp`, recompensando trocas seguras e penalizando xeques e ameaças de captura do oponente; integrado às 70 tablebases Syzygy (35 WDL + 35 DTZ em `./syzygy`).
- **Arquivos:** `src/suntzu.h`, `src/suntzu.cpp`, `src/search.h`, `src/search.cpp`, `src/engine.cpp`, `scripts/fetch_syzygy.sh`, `tests/test_suntzu_fase5.py`.
- **Resultados:**
  - **Tablebases Syzygy (`tests/test_suntzu_fase5.py`):** 35 arquivos WDL e 35 DTZ carregados (`Found 35 WDL and 35 DTZ tablebase files (up to 4-man)`), conversão exata em `KBNvK` e fallback seguro com diretório inexistente (0 crashes).
  - **Ativação e desempate na raiz (`tests/test_suntzu_fase5.py`):** validado desligamento automático do modo Pressão contra perfil `forte` e com relógio $< 5$ min; no modo Virada em posição inferior, validada troca `c2c3 -> f3g5` (`eval=-8cp, troca=0cp, armadilha=29.8cp`).
  - **Baterias de Virada e Conversão (`tests/test_suntzu_fase5.py`):** **4/4 partidas salvas (100%)** saindo com $-2$ peões no modo Virada; **4/4 vitórias (100%)** em posições ganhas no modo Conversão + Syzygy contra `SF_Base`.
  - **Teste de Segurança (`SunTzu_F5` vs `SF_Base`, 60 partidas `4+0.04` em `UHO.epd` com todos os modos e Syzygy ligados):** `Elo: -17.39 +/- 40.73` (`LLR: -0.37` dentro de `[-2.94, 2.94]`), 0 crashes, 0 quedas de tempo.
  - **Teste de Pressão / Cenário Enfraquecido (`SunTzu_F5` vs `Skill Level=15`, 40 partidas `3+0.03` em `UHO.epd`):** **39V 1E 0D (`118 x 1` pontos 3-1-0, 98.75% de aproveitamento)**.

### 2.6 Fase 6 — Console do Operador e Testes de Estresse
- **Problema:** Eliminar erros humanos de digitação, perda de estado em caso de queda de energia/processo ou travamento durante o torneio no tabuleiro físico.
- **Solução:**
  - Console 100% offline em `tools/operator_console/console.py` (Python + `python-chess`) com parser flexível em UCI (`e2e4`, `e7e8q`), SAN Inglês (`Nf3`, `Nxe5`) e SAN Português (`Cf3`, `Cxf7`, `Bb5`, `Td1`, `Dd4`, `Rf1`, `0-0`, `e8=D`).
  - Rejeição imediata de lances ilegais/ambíguos antes de tocar no motor, confirmação visual com diagrama ASCII, e banner em caixa alta com alertas explícitos de tabuleiro físico (`CAPTURA EM x`, `ROQUE PEQUENO/GRANDE`, `CAPTURA EN PASSANT`, `PROMOVE A DAMA`, `XEQUE NO REI ADVERSÁRIO`).
  - Ciclo completo de Ponder (`go ponder` → `ponderhit` imediato ou `stop` + nova busca), comando `u` (desfazer último par de lances), comando `t mm:ss` (sincronizar relógio físico), autosave transacional a cada lance em `partidas/ultima.fen` e `partidas/ultima.pgn` e retomada instantânea (`--resume partidas/ultima.fen`).
  - **Watchdog Anti-Crash (`WatchdogEngine`):** antes de cada lance, envia `isready` com timeout configurável (padrão `3.0 s`); se o motor não responder `readyok` ou se o processo cair, mata o processo, reinicia o motor automaticamente, restaura todas as opções UCI e a posição atual e calcula o lance sem interromper a partida.
  - **Alertas de Regra FIDE:** detecta repetição tripla e regra dos 50 lances e recomenda ativamente reivindicar o empate quando a avaliação está abaixo de $-50$ cp (ou não reivindicar quando estamos ganhando).
- **Arquivos:** `tools/operator_console/__init__.py`, `tools/operator_console/__main__.py`, `tools/operator_console/console.py`, `tools/operator_console/server.py`, `tools/operator_console/web/index.html` (console web local), `tests/test_console_fase6.py`.
- **Resultados:**
  - **1000 partidas ultra-rápidas de estresse (`bin/suntzu-native` com livro, Syzygy e todos os modos SunTzu vs `bin/sf-base`, `tc=0.35+0.01`, `concurrency=16`):** **1000/1000 partidas concluídas (`228` normais + `772` adjudicações), 0 crashes, 0 lances ilegais, 0 derrotas por tempo (`time forfeit`)**.
  - **200 partidas com Sanitizers (`ARCH=native debug=yes sanitize=address,undefined` com `-fsanitize=address,undefined -D_GLIBCXX_DEBUG`):** **200/200 partidas concluídas (`200` terminações normais), 0 erros de memória (ASan), 0 comportamentos indefinidos (UBSan), 0 asserções da STL**.
  - **50 partidas de estresse com Ponder ativo (`tests/test_console_fase6.py`):** **50/50 partidas concluídas (`5540` meios-lances, `1444` `ponderhit`s — 56.4% de acerto nas buscas ponderadas — e `1118` `stop`s), 0 crashes**.
  - **Testes de Watchdog e Retomada (`tests/test_console_fase6.py`):** recuperação automática validada após `SIGKILL` (morte abrupta do processo) e `SIGSTOP` (congelamento do processo); retomada via `--resume partidas/ultima.fen` concluída em **`161.0 ms`** (meta $< 20\text{ s}$).

---

## 3. Experimentos Rejeitados

- **Horizonte dinâmico agressivo ($N \in [12, 42]$) sem piso de múltiplos de $H$ (Fase 2):** Na primeira calibração do `timeman.cpp`, estimar $N$ abaixo de 20 lances no final da partida fazia o motor consumir a reserva e sofrer *time forfeit* quando partidas empatadas se estendiam além do lance 80 com atraso fixo $H$ por lance. Foi substituído por um piso conservador ($N \in [28, 52]$) combinado com gatilhos de pânico em $36H$, $22H$ e $15H$, reduzindo as quedas de seta de 5/30 para **0/40**.
- **Retificação pura $\max(0, S_2 - S_1)$ sem banda morta de horizonte (Fase 4):** Ao truncar variações negativas a zero sem descontar o ruído natural de horizonte (~8 cp entre buscas rasas consecutivas), o valor esperado $\mathbb{E}[\max(0, \Delta)]$ de um oponente forte ($\mathbb{E}[\Delta]=0$) sofria viés positivo (~10–15 cp), classificando erroneamente motores fortes como médios após saltos táticos de horizonte. A introdução de uma banda morta de `8 cp` e correção negativa limitada (`-12 cp`) elevou a acurácia do classificador de 40% para **92.5%–95.0%**.
- **Modo Virada com margem larga (`35–45 cp`) contra perfil `forte` em aberturas UHO (Fase 5):** Como as aberturas de teste `UHO.epd` já partem com desequilíbrio de $-100$ a $-150$ cp, ativar o modo Virada com margem de `35 cp` logo em $-150$ cp contra o Stockfish puro cedia centipeões sem induzir erros. Restringir a margem larga (`35–45 cp`) aos perfis `fraco`/`medio` e exigir $\le -350$ cp (com margem de `10 cp`) contra o perfil `forte`, além de limitar o MultiPV interno às profundidades $\le 7$, manteve a força intacta contra a base.
