/*
  SunTzu — "Arte da Guerra" Opponent Model & 3-1-0 Draw Aversion Module (Phase 4)
  Based on Stockfish, a UCI chess playing engine derived from Glaurung 2.1
  SPDX-License-Identifier: GPL-3.0-or-later
*/

#ifndef SUNTZU_H_INCLUDED
#define SUNTZU_H_INCLUDED

#include <string>
#include <string_view>

#include "position.h"
#include "types.h"

namespace Stockfish {

class OptionsMap;

namespace SunTzu {

enum class Profile {
    Strong,
    Medium,
    Weak
};

std::string_view profile_to_string(Profile p);

class State {
   public:
    State() = default;

    // Resets opponent modeling state at the start of a new game ('ucinewgame')
    void reset();

    // Called at the end of our main-thread search (after iterative_deepening)
    // to record S1/S2, update the opponent centipawn loss EMA, and compute the
    // draw value offset for the next search.
    void on_search_finished(const Position&   rootPos,
                            Depth             completedDepth,
                            Value             bestValue,
                            const OptionsMap& options);

    // Computes the draw value from the perspective of `stm` (side to move at the node)
    // when our root side is `rootSide`.
    Value draw_value(Color rootSide, Color stm, usize nodes, const OptionsMap& options) const;

    // Returns current effective profile (respecting OpponentProfile = auto/forte/medio/fraco)
    Profile effective_profile(const OptionsMap& options) const;

    // Returns current active draw aversion in centipawns (for info string / debugging)
    int current_draw_aversion_cp(const OptionsMap& options) const;

    double ema_loss_cp() const { return emaLossCp; }
    int    sample_count() const { return samples; }

    // Formats status string for UCI `info string`
    std::string status_info_string(const OptionsMap& options) const;

   private:
    bool    hasPrevEval     = false;
    Color   prevSide        = WHITE;
    int     prevPly         = 0;
    int     prevEvalCp      = 0;
    int     lastEvalCp      = 0;
    double  emaLossCp       = 25.0;  // Starts neutral ("medio")
    int     samples         = 0;
    Profile detectedProfile = Profile::Medium;

    // Cached internal-unit draw penalty D and root side for our side during search
    Color cachedRootSide    = WHITE;
    Value cachedDrawPenalty = VALUE_ZERO;

   public:
    void  update_search_cache(const Position& rootPos, const OptionsMap& options);
    Value cached_draw_penalty() const { return cachedDrawPenalty; }
};

State& global_state();

}  // namespace SunTzu

}  // namespace Stockfish

#endif  // #ifndef SUNTZU_H_INCLUDED
