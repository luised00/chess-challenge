# Protocolo de Operação em Trio — Dia do Evento (06/11/2026)

## 1. Divisão de Papéis na Mesa

1. **Operador A (Leitor):**
   - Observa atentamente o tabuleiro físico e o relógio.
   - Assim que o adversário soltar a peça e acionar o relógio, dita o lance em voz alta de forma clara (ex.: *"Cavalo f6"* ou *"e7 para e5"*).
   - Confere se o lance executado por **C** no tabuleiro físico corresponde ao anunciado.

2. **Operador B (Digitador / Console):**
   - Digita o lance no console web (`tools/operator_console/`, abre sozinho no navegador) **ou** clica/arrasta a peça no tabuleiro da tela, confere a seta laranja e o quadro "Confirmar lance do adversário?" e pressiona `Enter` para confirmar.
   - Monitora o `info string` do módulo **SunTzu** (perfil detectado do oponente e modo ativo) e os alertas de repetição tripla / regra dos 50 lances.
   - Sincroniza o tempo do console a cada 10 lances clicando no relógio da tela e digitando `mm:ss`.

3. **Operador C (Executor):**
   - Lê em voz alta o lance retornado pelo motor no quadro verde "Execute no tabuleiro" (com bipe quando fica pronto) (atenção especial a avisos de **CAPTURA**, **ROQUE**, **EN PASSANT** e **PROMOÇÃO**).
   - Executa o lance no tabuleiro físico e aciona imediatamente o relógio físico.
   - A cada 10 lances, informa a leitura exata do nosso relógio físico para **B**.

> **Regra de ouro:** Errar devagar custa segundos; errar rápido custa a partida. Em qualquer dúvida de sincronia, pare e compare o FEN da tela com o tabuleiro físico.

---

## 2. Como Iniciar e Operar o Console

### Inicialização da Partida

O console abre automaticamente no navegador em `http://127.0.0.1:8765/` (somente local, 100% offline).

```bash
# Jogando de Brancas (padrão 25 min sudden death, Ponder ligado)
python3 tools/operator_console/console.py --color brancas

# Jogando de Pretas
python3 tools/operator_console/console.py --color pretas

# Retomada de emergência em menos de 1 segundo após queda de energia/fechamento
python3 tools/operator_console/console.py --resume partidas/ultima.fen

# Modo econômico de bateria (metade das threads, Hash <= 256 MB, sem Ponder)
python3 tools/operator_console/console.py --color brancas --eco

# Fallback de emergência sem navegador: modo texto no terminal (mesmos comandos antigos: u, t mm:ss, fen...)
python3 tools/operator_console/console.py --color brancas --text
```

Se o navegador for fechado ou recarregado (`F5`), nada se perde: basta reabrir o endereço. Se aparecer a faixa vermelha **SERVIDOR DESCONECTADO**, reinicie com `--resume partidas/ultima.fen` — a página reconecta sozinha.

### Ações na Tela do Console Web

| Ação | Como fazer |
| --- | --- |
| Registrar lance do adversário | Digite `e4` / `Cf3` / `Cxf7` / `0-0` / `e8=D` / `e7e5` e `Enter` (revisão) → `Enter` (confirma). Ou clique na peça e na casa de destino (ou arraste); a promoção abre um seletor |
| Cancelar lance em revisão | `Esc` ou botão **Cancelar** |
| Desfazer (lance confirmado errado) | `Ctrl+Z` ou botão **Desfazer** (reverte o lance do adversário + nossa resposta) |
| Ler o nosso lance | Quadro verde no topo: peça, origem → destino, SAN e avisos de **CAPTURA / ROQUE / EN PASSANT / PROMOÇÃO / XEQUE**; seta verde no tabuleiro |
| Motor demorando | Botão **Jogar agora** (envia `stop`; o motor joga o melhor lance encontrado) |
| Sincronizar relógios | Clique em **Nosso relógio** ou **Adversário**, digite `mm:ss`, `Enter` |
| Perfil do oponente | Seletor **Perfil do oponente** (auto / forte / médio / fraco) |
| `TimeProfile` | Botões **Normal / Rápido** (use Rápido quando o operador demorar mais de 8 s por lance) |
| Tempo fixo por lance | Campo **Tempo fixo por lance** (segundos) → **Aplicar**; **Auto** volta à gestão pelo relógio |
| FEN / PGN | Botões **Copiar FEN** e **Baixar PGN** |
| Nova partida | Botão **Nova partida** → escolher a cor |
| Alertas de regra | Repetição tripla e 50 lances aparecem em destaque abaixo dos relógios |

---

## 3. Checklist Pré-Rodada

- [ ] Notebook conectado à tomada (extensão ligada) + bateria 100% carregada
- [ ] Suspensão, hibernação, protetor de tela e atualizações automáticas desativados
- [ ] **Wi-Fi e Bluetooth desligados** (conformidade total com a regra offline)
- [ ] Assinatura `./bin/suntzu-native bench` conferida
- [ ] Opções UCI verificadas: `Threads`, `Hash`, `PhysicalBoardOverhead`, `PanicReserve`, `OwnBook`, `SyzygyPath`
- [ ] Notebook reserva ligado e pronto com a mesma build e arquivos
