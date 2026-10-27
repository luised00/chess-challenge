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
- **Resultados:** *(preencher após o teste de sanidade da Fase 1)*

### 2.2 Fase 2 — Gestão de Tempo Físico e Ponder
- **Problema:** Descontar de 5 a 8 s por lance de operação humana no tabuleiro físico sem estourar os 25 min *sudden death*.
- **Solução:** Modelo `PhysicalBoardOverhead` + `PanicReserve` + extensão de lances forçados.
- **Arquivos:** `src/timeman.cpp`, `src/timeman.h`, `src/search.cpp`, `tests/lag_proxy.py`.
- **Resultados:** *(preencher na Fase 2)*

### 2.3 Fase 3 — Livro Polyglot com Pesos 3-1-0
- **Problema:** Responder instantaneamente na abertura escolhendo linhas que maximizam $3V + E$.
- **Solução:** Leitor Polyglot nativo em `src/book.cpp` validado contra `python-chess`.
- **Arquivos:** `src/book.h`, `src/book.cpp`, `tools/book_builder.py`, `tests/book_keys_test.py`.
- **Resultados:** *(preencher na Fase 3)*

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

*(Nesta seção serão registrados os ajustes ou heurísticas testados durante a semana que não demonstraram ganho estatístico em SPRT / pontos 3-1-0 e por isso foram descartados ou mantidos desligados por padrão.)*
