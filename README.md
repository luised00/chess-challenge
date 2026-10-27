# SunTzu — Chess Challenge III ICEV 2026

**SunTzu** é um motor de xadrez UCI desenvolvido para o **Chess Challenge III ICEV 2026** (06/11/2026). Ele é baseado no **Stockfish 19** (`upstream-base`: `edb0d9db6731067ec50ce619ff372b463bc4dd5d`), mantendo intacta a avaliação NNUE e a busca principal do Stockfish e adicionando o módulo autoral **"Arte da Guerra"** voltado para as condições reais do torneio:

1. **Gestão de Tempo para Tabuleiro Físico e Ponder (`src/timeman.cpp`, `src/search.cpp`)**: modelo que desconta o overhead de operação humana (`PhysicalBoardOverhead`), mantém reserva de pânico (`PanicReserve`) para *sudden death* de 25 min e estende lances forçados.
2. **Livro de Aberturas Polyglot 3-1-0 (`src/book.cpp`, `tools/book_builder.py`)**: leitor nativo Polyglot `.bin` com pesos calibrados para o sistema de pontuação **3-1-0** ($peso = 3V + E$), priorizando posições desequilibradas e evitando linhas de empate.
3. **Modelo do Oponente e Aversão Dinâmica ao Empate (`src/suntzu.cpp`, `src/search.cpp`)**: estima em tempo real a força do adversário pela perda média de centipeões (forte/médio/fraco) e ajusta dinamicamente o valor do empate conforme a regra 3-1-0 ($3 \cdot P(V) + P(E) > 1$).
4. **Modos Táticos — Pressão, Virada e Conversão (`src/suntzu.cpp`)**: seleção final no nó raiz para induzir erros contra oponentes mais fracos, manter complicações quando em desvantagem (*swindle*) e simplificar com segurança quando ganho (+ tablebases Syzygy).
5. **Console do Operador Anti-Crash (`tools/operator_console/`)**: console web local (abre no navegador, 100% offline) para a operação em trio com validação de lances, entrada por clique/arraste ou digitação, confirmação visual, sincronização com relógio físico, autosave FEN/PGN a cada lance e recuperação instantânea (`--resume`).

---

## Auditoria e Diff contra a Base

Toda modificação da equipe pode ser inspecionada diretamente contra a tag `upstream-base` (Stockfish 19 sem alterações):

```bash
git diff upstream-base..HEAD --stat
```

Documentação detalhada para a banca:
- [`docs/ARTE_DA_GUERRA.md`](docs/ARTE_DA_GUERRA.md) — Princípios de Sun Tzu mapeados para algoritmos, arquivos, opções UCI e resultados medidos.
- [`docs/RELATORIO_ENGENHARIA.md`](docs/RELATORIO_ENGENHARIA.md) — Diffs comentados, resultados SPRT / 3-1-0 e experimentos rejeitados.
- [`docs/OPERACAO.md`](docs/OPERACAO.md) — Protocolo de operação de 3 pessoas no tabuleiro físico e checklist de competição.

---

## Como Compilar

Pré-requisitos: `g++` 11+ (ou `clang++`), `make`, `python3` 3.10+.

```bash
# Script automatizado (baixa a rede NNUE se necessário e gera bin/suntzu-native e bin/suntzu-avx2)
./scripts/build.sh
```

Ou manualmente:

```bash
cd src
make net                                # Baixa a rede NNUE oficial (apenas no setup; fica embutida no binário)
make -j profile-build ARCH=native       # Build otimizada com PGO para a máquina atual
./stockfish bench                       # Verifica a assinatura de nós (Nodes searched)
```

### Assinatura de Referência (`bench`)

- **Base (`upstream-base` / Stockfish 19):** `Nodes searched  : 2497913`
- Com `SunTzu=false` e `OwnBook=false`, o motor preserva exatamente o mesmo `bench` da base (`2497913` nós).

---

## Operação no Tabuleiro Físico (Console Anti-Crash)

```bash
# Iniciar partida jogando de Brancas (ou --color pretas)
python3 tools/operator_console/console.py --color brancas

# Retomada instantânea (< 1s) do estado salvo a cada lance
python3 tools/operator_console/console.py --resume partidas/ultima.fen

# Fallback de emergência sem navegador (modo texto no terminal)
python3 tools/operator_console/console.py --color brancas --text
```

O console web abre em `http://127.0.0.1:8765/` (`--port` para mudar, `--no-browser` para não abrir o navegador).

---

## Testes (SPRT, Pontuação 3-1-0 e Suítes de Fase)

```bash
# Rodar match SPRT contra a base e calcular pontuação 3-1-0
./tests/sprt.sh bin/suntzu-native bin/sf-base teste_base

# Suítes automatizadas de engenharia (Fases 2 a 6)
python3 tests/test_timeman_ponder.py
python3 tests/book_keys_test.py
python3 tests/test_suntzu_fase4.py
python3 tests/test_suntzu_fase5.py
python3 tests/test_console_fase6.py
```

---

## Créditos e Licença

O **SunTzu** é software livre distribuído sob a **GNU General Public License v3.0 (GPL-3.0)** — veja [`Copying.txt`](Copying.txt).

- **Motor base:** [Stockfish 19](https://stockfishchess.org/) — Copyright (C) 2004-2026 The Stockfish developers (veja [`AUTHORS`](AUTHORS)).
- **Equipe SunTzu (Chess Challenge III ICEV 2026):** listada em [`AUTHORS`](AUTHORS).
