# Protocolo de Operação em Trio — Dia do Evento (06/11/2026)

## 1. Divisão de Papéis na Mesa

1. **Operador A (Leitor):**
   - Observa atentamente o tabuleiro físico e o relógio.
   - Assim que o adversário soltar a peça e acionar o relógio, dita o lance em voz alta de forma clara (ex.: *"Cavalo f6"* ou *"e7 para e5"*).
   - Confere se o lance executado por **C** no tabuleiro físico corresponde ao anunciado.

2. **Operador B (Digitador / Console):**
   - Digita o lance no console (`tools/operator_console/`), confere o diagrama ASCII na tela e pressiona `Enter` para confirmar.
   - Monitora o `info string` do módulo **SunTzu** (perfil detectado do oponente e modo ativo) e os alertas de repetição tripla / regra dos 50 lances.
   - Sincroniza o tempo do console a cada 10 lances com o comando `t mm:ss`.

3. **Operador C (Executor):**
   - Lê em voz alta o lance retornado pelo motor na tela (atenção especial a avisos de **CAPTURA**, **ROQUE**, **EN PASSANT** e **PROMOÇÃO**).
   - Executa o lance no tabuleiro físico e aciona imediatamente o relógio físico.
   - A cada 10 lances, informa a leitura exata do nosso relógio físico para **B**.

> **Regra de ouro:** Errar devagar custa segundos; errar rápido custa a partida. Em qualquer dúvida de sincronia, pare e compare o FEN da tela com o tabuleiro físico.

---

## 2. Como Iniciar e Operar o Console

### Inicialização da Partida

```bash
# Jogando de Brancas (padrão 25 min sudden death, 4 threads, 512 MB Hash, Ponder ligado)
python3 tools/operator_console/console.py --color brancas

# Jogando de Pretas
python3 tools/operator_console/console.py --color pretas

# Retomada de emergência em menos de 1 segundo após queda de energia/fechamento
python3 tools/operator_console/console.py --resume partidas/ultima.fen

# Modo econômico de bateria (para uso fora da tomada: 2 threads, 128 MB Hash, sem Ponder)
python3 tools/operator_console/console.py --color brancas --eco
```

### Comandos Rápidos Durante a Partida

| Comando | Ação |
| --- | --- |
| `e2e4` / `e4` / `Cf3` / `Cxf7` / `0-0` / `e8=D` | Registra lance do adversário em UCI, SAN Inglês ou SAN Português (exibe diagrama ASCII e pede `Enter` antes de enviar ao motor) |
| `u` | Desfaz o último par de lances (caso um lance errado tenha sido confirmado) |
| `t 12:34` | Sincroniza o nosso tempo restante no motor para 12 min e 34 s |
| `t opp 14:20` | Sincroniza o tempo restante do adversário para 14 min e 20 s |
| `perfil fraco` (ou `medio` / `forte` / `auto`) | Força manualmente o perfil do oponente na doutrina SunTzu |
| `rapido` / `normal` | Alterna `TimeProfile` (quando o operador estiver demorando mais de 8 s por lance, use `rapido`) |
| `fen` | Exibe o FEN atual e a lista completa de lances UCI na tela |
| `--resume partidas/ultima.fen` | Recupera a partida em menos de 1 s (meta < 20 s) após reinício |

---

## 3. Checklist Pré-Rodada

- [ ] Notebook conectado à tomada (extensão ligada) + bateria 100% carregada
- [ ] Suspensão, hibernação, protetor de tela e atualizações automáticas desativados
- [ ] **Wi-Fi e Bluetooth desligados** (conformidade total com a regra offline)
- [ ] Assinatura `./bin/suntzu-native bench` conferida
- [ ] Opções UCI verificadas: `Threads`, `Hash`, `PhysicalBoardOverhead`, `PanicReserve`, `OwnBook`, `SyzygyPath`
- [ ] Notebook reserva ligado e pronto com a mesma build e arquivos
