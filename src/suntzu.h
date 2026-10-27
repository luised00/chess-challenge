/*
  SunTzu — "Arte da Guerra" Opponent Model, 3-1-0 Draw Aversion & Tactical Root Selection (Phases 4-5)
  Based on Stockfish, a UCI chess playing engine derived from Glaurung 2.1
  SPDX-License-Identifier: GPL-3.0-or-later
*/

#ifndef SUNTZU_H_INCLUDED
#define SUNTZU_H_INCLUDED

#include <string>
#include <string_view>
#include <vector>

#include "position.h"
#include "types.h"

namespace Stockfish {

class OptionsMap;
class TimeManagement;

namespace Search {
struct LimitsType;
}

namespace SunTzu {

enum class Profile {
    Strong,
    Medium,
    Weak
};

enum class Mode {
    None,
    Pressure,  // "Ataque onde ele não está preparado"
    Swindle,   // "Quando fraco, pareça forte" (Virada)
    Convert    // "Não encurrale um inimigo desesperado" (Conversão)
};

std::string_view profile_to_string(Profile p);
std::string_view mode_to_string(Mode m);

struct CandidateMetrics {
    Move   move            = Move::none();
    usize  rootIdx         = 0;
    int    evalCp          = 0;      // Candidate's MultiPV evaluation (cp)
    int    replyBestCp     = 0;      // Our eval (cp) after opponent's best reply
    int    replySecondCp   = 0;      // Our eval (cp) after opponent's 2nd best reply
    int    uniquenessGapCp = 0;      // max(0, replySecondCp - replyBestCp)
    int    blunders100     = 0;      // Natural replies losing >= 100 cp
    int    mistakes50      = 0;      // Natural replies losing 50..99 cp
    double trapScore       = 0.0;    // Medida de armadilha (cp)
    int    tradedNonPawnCp = 0;      // Non-pawn material traded off (cp)
    int    nonPawnAfterCp  = 0;      // Total non-pawn material remaining (cp)
    int    oppChecks       = 0;      // Number of legal checks opponent has after move
    int    oppPieceThreats = 0;      // Number of captures of our non-pawn pieces
    bool   givesCheck      = false;  // Whether our move gives check
    bool   keepsOurQueen   = false;  // Whether our queen remains on board
    bool   advances50Move  = false;  // Resets 50-move counter (capture or pawn move)
    bool   immediateDraw   = false;  // True if move enters repetition/50-move/stalemate
    bool   immediateMate   = false;  // True if move delivers immediate mate
    double finalScore      = 0.0;    // Mode-combined tactical score
};

int non_pawn_material_cp(const Position& pos);
int material_balance_cp(const Position& pos, Color us);

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

    // Phase 5: Determines which tactical root mode (if any) should be active
    Mode determine_mode(const Position&           rootPos,
                        int                       evalCp,
                        const Search::LimitsType& limits,
                        const TimeManagement&     tm,
                        const OptionsMap&         options) const;

    // Phase 5: Returns maximum accepted centipawn margin below best move for `mode`
    int mode_margin_cp(Mode mode, const OptionsMap& options) const;

    // Phase 5: Computes trap score and mode-specific score for each candidate and returns
    // the chosen index into `candidates` (0 = keep Stockfish's best move).
    usize select_root_move(Mode                           mode,
                           int                            maxMarginCp,
                           std::vector<CandidateMetrics>& candidates,
                           const Position&                rootPos,
                           const OptionsMap&              options);

    void record_mode_status(Mode mode, std::string_view reason);

    double ema_loss_cp() const { return emaLossCp; }
    int    sample_count() const { return samples; }
    int    last_eval_cp() const { return lastEvalCp; }
    Mode   last_mode() const { return lastMode; }

    // Formats status string for UCI `info string`
    std::string status_info_string(const OptionsMap& options) const;

   private:
    bool        hasPrevEval     = false;
    Color       prevSide        = WHITE;
    int         prevPly         = 0;
    int         prevEvalCp      = 0;
    int         lastEvalCp      = 0;
    double      emaLossCp       = 25.0;  // Starts neutral ("medio")
    int         samples         = 0;
    Profile     detectedProfile = Profile::Medium;
    Mode        lastMode        = Mode::None;
    std::string lastReason      = "padrao";

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
