# Origem e Licença do Livro de Aberturas (`books/suntzu_310.bin`)

## 1. Formato e Geração Reprodutível

O arquivo `books/suntzu_310.bin` está no formato padrão **Polyglot (`.bin`)** (entradas de 16 bytes big-endian ordenadas por chave Zobrist de 64 bits) e é gerado de forma 100% reprodutível pelo script da equipe:

```bash
python3 tools/book_builder.py --out books/suntzu_310.bin --avoid books/evitar.txt
```

## 2. Metodologia de Pesos 3-1-0

Diferente de livros tradicionais que atribuem pesos por frequência ou por pontuação clássica ($1\text{–}\frac{1}{2}\text{–}0$), o `tools/book_builder.py` calcula o peso de cada lance pela pontuação esperada do regulamento do **Chess Challenge III ICEV 2026** (Vitória = 3 pts, Empate = 1 pt, Derrota = 0 pt):

$$\text{peso} = 3 \cdot \text{vitórias} + \text{empates}$$

Além disso, variantes conhecidas por produzir empates teóricos simétricos (como o final da Parede de Berlim, Petroff simétrica e Francesa das Trocas simétrica) são filtradas via `books/evitar.txt`.

## 3. Fonte dos Dados e Licença

- **Repertório Teórico 3-1-0 (`tools/book_builder.py`):** Sequências de aberturas de domínio público da teoria enxadrística (ECO A–E: Siciliana Najdorf/Sveshnikov, Ruy Lopez, Giuoco Piano, Francesa Winawer, Caro-Kann Avanço, Índia do Rei, Grünfeld, Nimzo-Índia, Gambito da Dama e Inglesa), ponderadas pelas estatísticas de vitórias/empates na regra 3-1-0.
- **Suite de Teste de Aberturas (`books/UHO.epd`, ignorada no Git):** Extraída do repositório oficial de testes do Stockfish ([`official-stockfish/books`](https://github.com/official-stockfish/books), domínio público / CC0), usada exclusivamente nos matches automatizados com `fastchess`.
- **Licença de distribuição do livro (`suntzu_310.bin`):** **CC0 1.0 Universal (Domínio Público) / GPL-3.0**, livre para uso, auditoria e redistribuição offline.
