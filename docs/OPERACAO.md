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

## 2. Comandos Rápidos do Console

| Comando | Ação |
| --- | --- |
| `e2e4` ou `e4` / `Cxf7` | Registra lance do adversário (pede confirmação antes de enviar ao motor) |
| `u` | Desfaz o último lance digitado errado |
| `t 12:34` | Corrige o nosso tempo restante no motor para 12 min e 34 s |
| `--resume partidas/ultima.fen` | Recupera a partida em menos de 20 s após reinício |

---

## 3. Checklist Pré-Rodada

- [ ] Notebook conectado à tomada (extensão ligada) + bateria 100% carregada
- [ ] Suspensão, hibernação, protetor de tela e atualizações automáticas desativados
- [ ] **Wi-Fi e Bluetooth desligados** (conformidade total com a regra offline)
- [ ] Assinatura `./bin/suntzu-native bench` conferida
- [ ] Opções UCI verificadas: `Threads`, `Hash`, `PhysicalBoardOverhead`, `PanicReserve`, `OwnBook`, `SyzygyPath`
- [ ] Notebook reserva ligado e pronto com a mesma build e arquivos
