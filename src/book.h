/*
  SunTzu — Polyglot Opening Book Module (Phase 3)
  Based on Stockfish, a UCI chess playing engine derived from Glaurung 2.1
  SPDX-License-Identifier: GPL-3.0-or-later
*/

#ifndef BOOK_H_INCLUDED
#define BOOK_H_INCLUDED

#include <string>
#include <vector>

#include "position.h"
#include "types.h"

namespace Stockfish {

class OptionsMap;

namespace PolyglotBook {

struct Entry {
    u64 key;
    u16 move;
    u16 weight;
    u32 learn;
};

// Computes the official 64-bit Polyglot Zobrist hash for a Position.
Key compute_key(const Position& pos);

// Converts a 16-bit Polyglot move into an internal Stockfish Move and validates legality.
Move polyglot_to_sf_move(const Position& pos, u16 pgMove);

class Book {
   public:
    Book() = default;

    // Loads or reloads the .bin file into memory if needed. Never throws or crashes.
    bool ensure_loaded(const std::string& filename);

    // Probes the loaded Polyglot book for a legal move in the current position.
    // Returns Move::none() if OwnBook is false, out of BookDepth, file missing/corrupt, or no legal move matches.
    Move probe(const Position& pos, const OptionsMap& options);

   private:
    std::string        loadedPath;
    bool               loadAttempted = false;
    bool               loadSuccess   = false;
    std::vector<Entry> entries;
};

// Global book instance used by the main search thread
Book& global_book();

}  // namespace PolyglotBook

}  // namespace Stockfish

#endif  // #ifndef BOOK_H_INCLUDED
