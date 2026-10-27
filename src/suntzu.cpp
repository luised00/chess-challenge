/*
  SunTzu — "Arte da Guerra" Opponent Model, 3-1-0 Draw Aversion & Tactical Root Selection (Phases 4-5)
  Based on Stockfish, a UCI chess playing engine derived from Glaurung 2.1
  SPDX-License-Identifier: GPL-3.0-or-later
*/

#include "suntzu.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>

#include "search.h"
#include "timeman.h"
#include "uci.h"
#include "ucioption.h"

namespace Stockfish::SunTzu {

namespace {

// Stockfish WDL model parameters (same polynomial fit as uci.cpp)
struct WinRateParams {
    double a;
    double b;
};

WinRateParams win_rate_params(const Position& pos) {
    int material = pos.count<PAWN>() + 3 * pos.count<KNIGHT>() + 3 * pos.count<BISHOP>()
                 + 5 * pos.count<ROOK>() + 9 * pos.count<QUEEN>();

    double m = std::clamp(material, 17, 78) / 58.0;

    constexpr double as[] = {-142.72052667, 372.35176398, -340.71073572, 415.23490212};
    constexpr double bs[] = {5.93832785, 15.61267078, -30.57816876, 69.63866711};

    double a = (((as[0] * m + as[1]) * m + as[2]) * m) + as[3];
    double b = (((bs[0] * m + bs[1]) * m + bs[2]) * m) + bs[3];

    return {a, b};
}

// Returns expected 3-1-0 points in [0.0, 3.0]: E[pts] = 3 * P(win) + 1 * P(draw)
double expected_310_points(int evalCp, const Position& pos, Profile prof) {
    auto [a, b] = win_rate_params(pos);
    // Against weaker opponents, a given evaluation converts to wins at a higher rate
    double skillShiftCp = (prof == Profile::Weak) ? 45.0 : (prof == Profile::Medium) ? 18.0 : 0.0;
    double v            = (double(evalCp) + skillShiftCp) * a / 100.0;

    double pWin  = 1.0 / (1.0 + std::exp((a - v) / b));
    double pLoss = 1.0 / (1.0 + std::exp((a + v) / b));
    double pDraw = std::max(0.0, 1.0 - pWin - pLoss);

    return 3.0 * pWin + 1.0 * pDraw;
}

}  // namespace

int non_pawn_material_cp(const Position& pos) {
    return 300 * pos.count<KNIGHT>() + 315 * pos.count<BISHOP>() + 500 * pos.count<ROOK>()
         + 900 * pos.count<QUEEN>();
}

int material_balance_cp(const Position& pos, Color us) {
    Color them     = ~us;
    int   ourMat   = 100 * pos.count<PAWN>(us) + 300 * pos.count<KNIGHT>(us)
                   + 315 * pos.count<BISHOP>(us) + 500 * pos.count<ROOK>(us)
                   + 900 * pos.count<QUEEN>(us);
    int   theirMat = 100 * pos.count<PAWN>(them) + 300 * pos.count<KNIGHT>(them)
                   + 315 * pos.count<BISHOP>(them) + 500 * pos.count<ROOK>(them)
                   + 900 * pos.count<QUEEN>(them);
    return ourMat - theirMat;
}

std::string_view profile_to_string(Profile p) {
    switch (p)
    {
    case Profile::Strong :
        return "forte";
    case Profile::Medium :
        return "medio";
    case Profile::Weak :
        return "fraco";
    }
    return "medio";
}

std::string_view mode_to_string(Mode m) {
    switch (m)
    {
    case Mode::None :
        return "nenhum";
    case Mode::Pressure :
        return "pressao";
    case Mode::Swindle :
        return "virada";
    case Mode::Convert :
        return "conversao";
    }
    return "nenhum";
}

void State::reset() {
    hasPrevEval       = false;
    prevSide          = WHITE;
    prevPly           = 0;
    prevEvalCp        = 0;
    lastEvalCp        = 0;
    emaLossCp         = 25.0;
    samples           = 0;
    detectedProfile   = Profile::Medium;
    lastMode          = Mode::None;
    lastReason        = "padrao";
    cachedDrawPenalty = VALUE_ZERO;
}

Profile State::effective_profile(const OptionsMap& options) const {
    if (options["OpponentProfile"] == "forte")
        return Profile::Strong;
    if (options["OpponentProfile"] == "medio")
        return Profile::Medium;
    if (options["OpponentProfile"] == "fraco")
        return Profile::Weak;
    return detectedProfile;
}

int State::current_draw_aversion_cp(const OptionsMap& options) const {
    if (!int(options["SunTzu"]))
        return 0;

    // When losing by more than 50 cp, a draw is welcome (D = 0)
    if (lastEvalCp < -50)
        return 0;

    int     baseCp = int(options["DrawAversion"]);
    Profile prof   = effective_profile(options);

    // Dynamic scaling based on opponent profile:
    // default baseCp = 25 -> Strong = 10 cp, Medium = 25 cp, Weak = 50 cp
    int targetCp = 0;
    switch (prof)
    {
    case Profile::Strong :
        targetCp = (baseCp * 10) / 25;
        break;
    case Profile::Medium :
        targetCp = baseCp;
        break;
    case Profile::Weak :
        targetCp = (baseCp * 50) / 25;
        break;
    }

    // Taper smoothly between -50 cp and 0 cp so there is no discontinuity
    if (lastEvalCp < 0)
        targetCp = (targetCp * (lastEvalCp + 50)) / 50;

    return std::clamp(targetCp, 0, 150);
}

void State::update_search_cache(const Position& rootPos, const OptionsMap& options) {
    cachedRootSide = rootPos.side_to_move();

    // If starting from a fresh position or non-consecutive ply, seed lastEvalCp from material
    if (!hasPrevEval || prevSide != cachedRootSide || std::abs(rootPos.game_ply() - prevPly) > 4)
        lastEvalCp = material_balance_cp(rootPos, cachedRootSide);

    if (!int(options["SunTzu"]))
    {
        cachedDrawPenalty = VALUE_ZERO;
        return;
    }

    Profile prof = effective_profile(options);

    // Check 3-1-0 expected points criterion: 3 * P(win) + P(draw) > 1.0
    if (lastEvalCp < -50 || expected_310_points(lastEvalCp, rootPos, prof) <= 1.0)
    {
        cachedDrawPenalty = VALUE_ZERO;
        return;
    }

    int cpPenalty = current_draw_aversion_cp(options);
    if (cpPenalty <= 0)
    {
        cachedDrawPenalty = VALUE_ZERO;
        return;
    }

    auto [a, b]       = win_rate_params(rootPos);
    cachedDrawPenalty = Value(std::round(cpPenalty * a / 100.0));
}

void State::on_search_finished(const Position&   rootPos,
                               Depth             completedDepth,
                               Value             bestValue,
                               const OptionsMap& options) {
    if (!int(options["SunTzu"]))
        return;

    Color us  = rootPos.side_to_move();
    int   ply = rootPos.game_ply();

    int currentCp = is_decisive(bestValue) ? (bestValue > 0 ? 1000 : -1000)
                                           : UCIEngine::to_cp(bestValue, rootPos);
    lastEvalCp    = currentCp;

    // Update opponent loss model when:
    // - We have a previous evaluation from our side
    // - Current search reached at least depth 6
    // - Position was not already completely decided (|S1| <= 850 cp)
    if (hasPrevEval && prevSide == us && ply > prevPly && ply <= prevPly + 4 && completedDepth >= 6
        && std::abs(prevEvalCp) <= 850)
    {
        // Subtract an 8 cp horizon-noise deadband and allow small negative corrections (-12 cp)
        // when the opponent's move improves upon our previous shallow evaluation
        int rawDiff = currentCp - prevEvalCp;
        int lossCp  = (rawDiff > 8) ? std::min(rawDiff - 8, 250) : std::max(rawDiff, -12);

        if (samples == 0)
            emaLossCp = std::clamp(0.35 * double(lossCp) + 0.65 * 12.0, 0.0, 300.0);
        else
            emaLossCp = std::clamp(0.25 * double(lossCp) + 0.75 * emaLossCp, 0.0, 300.0);

        samples++;

        if (emaLossCp < 15.0)
            detectedProfile = Profile::Strong;
        else if (emaLossCp <= 50.0)
            detectedProfile = Profile::Medium;
        else
            detectedProfile = Profile::Weak;
    }

    if (completedDepth >= 6 && !is_decisive(bestValue))
    {
        hasPrevEval = true;
        prevSide    = us;
        prevPly     = ply;
        prevEvalCp  = currentCp;
    }

    update_search_cache(rootPos, options);
}

Value State::draw_value([[maybe_unused]] Color rootSide,
                        Color                  stm,
                        [[maybe_unused]] usize nodes,
                        const OptionsMap&      options) const {
    if (!int(options["SunTzu"]) || cachedDrawPenalty == VALUE_ZERO)
        return VALUE_ZERO;

    // From our root side's perspective, a draw is worth -D; from the opponent's perspective, +D
    return (stm == cachedRootSide) ? -cachedDrawPenalty : cachedDrawPenalty;
}

Mode State::determine_mode(const Position&           rootPos,
                           int                       evalCp,
                           const Search::LimitsType& limits,
                           const TimeManagement&     tm,
                           const OptionsMap&         options) const {
    if (!int(options["SunTzu"]))
        return Mode::None;

    if (tm.in_critical_panic() || tm.in_extreme_panic())
        return Mode::None;

    Color us = rootPos.side_to_move();

    // Check low clock time when playing with time management
    if (limits.use_time_management())
    {
        TimePoint physOverhead = TimePoint(options["PhysicalBoardOverhead"]);
        if (physOverhead >= 5000)
        {
            // Real 25-min physical board game: require > 5 minutes (300,000 ms) for tactical modes
            if (limits.time[us] < 180000)
                return Mode::None;
        }
        else if (limits.time[us] < 400)
        {
            return Mode::None;
        }
    }

    // 1. Convert Mode ("Não encurrale um inimigo desesperado"): winning > +300 cp
    if (int(options["ConvertMode"]) && evalCp >= 300 && evalCp <= 2500)
        return Mode::Convert;

    Profile prof = effective_profile(options);

    // 2. Swindle Mode / Virada ("Quando fraco, pareça forte"): losing < -150 cp (but not hopeless).
    //    Against Strong opponents, only trigger when deeply losing (<= -350 cp) to avoid giving up
    //    centipawns in slightly worse UHO openings.
    int swindleThreshold = (prof == Profile::Strong) ? -350 : -150;
    if (int(options["SwindleMode"]) && evalCp <= swindleThreshold && evalCp >= -1200)
        return Mode::Swindle;

    // 3. Pressure Mode ("Ataque onde ele não está preparado"):
    //    Opponent profile is Weak or Medium, evaluation in [-150, +300] cp, and > 5 min on clock
    int pressMargin = int(options["PressureMargin"]);
    if (pressMargin > 0 && evalCp > -150 && evalCp < 300)
    {
        if (limits.use_time_management() && TimePoint(options["PhysicalBoardOverhead"]) >= 5000
            && limits.time[us] <= 300000)
            return Mode::None;

        if (prof == Profile::Weak || prof == Profile::Medium)
        {
            // In auto profile mode during a game, wait for at least 1 opponent sample
            // before assuming the opponent is not Strong
            if (options["OpponentProfile"] == "auto" && samples == 0
                && (limits.use_time_management() || rootPos.game_ply() < 4))
                return Mode::None;

            return Mode::Pressure;
        }
    }

    return Mode::None;
}

int State::mode_margin_cp(Mode mode, const OptionsMap& options) const {
    Profile prof = effective_profile(options);
    switch (mode)
    {
    case Mode::Pressure : {
        int m = int(options["PressureMargin"]);
        return std::clamp(m, 0, 50);
    }
    case Mode::Swindle :
        // 30-50 cp margin against Weak/Medium opponents; conservative 10 cp against Strong
        return (prof == Profile::Weak) ? 45 : (prof == Profile::Medium) ? 35 : 10;
    case Mode::Convert :
        // 15 cp margin when clearly winning
        return 15;
    case Mode::None :
        return 0;
    }
    return 0;
}

void State::record_mode_status(Mode mode, std::string_view reason) {
    lastMode   = mode;
    lastReason = std::string(reason);
}

usize State::select_root_move(Mode                           mode,
                              int                            maxMarginCp,
                              std::vector<CandidateMetrics>& candidates,
                              const Position&                rootPos,
                              const OptionsMap&              options) {
    lastMode = mode;
    if (mode == Mode::None || candidates.empty())
    {
        lastReason = "padrao";
        return 0;
    }

    if (candidates.size() == 1)
    {
        lastReason = "unico_na_margem";
        return 0;
    }

    Profile prof         = effective_profile(options);
    int     bestEvalCp   = candidates[0].evalCp;
    int     bestReplyCp  = candidates[0].replyBestCp;
    bool    highRule50   = (rootPos.rule50_count() >= 30);

    for (usize i = 0; i < candidates.size(); ++i)
    {
        auto& c               = candidates[i];
        c.uniquenessGapCp     = std::clamp(c.replySecondCp - c.replyBestCp, 0, 140);

        // Medida de armadilha (trap score):
        // Combines uniqueness of opponent's best reply (gap between 1st and 2nd best reply)
        // with count of natural replies that lose >= 100 cp (blunders) or 50-99 cp (mistakes)
        double rawTrap = 0.25 * double(c.uniquenessGapCp) + 9.0 * double(c.blunders100)
                       + 3.5 * double(c.mistakes50) + (c.givesCheck ? 2.5 : 0.0);
        c.trapScore = std::clamp(rawTrap, 0.0, 45.0);

        // Hard safety check for non-primary candidates:
        // Never select a candidate whose MultiPV eval OR post-reply eval drops beyond margin
        if (i > 0)
        {
            if (bestEvalCp - c.evalCp > maxMarginCp
                || bestReplyCp - c.replyBestCp > maxMarginCp + 8)
            {
                c.finalScore = -1.0e6;
                continue;
            }
        }

        if (c.immediateMate)
        {
            c.finalScore = 1.0e6;
            continue;
        }

        if (mode == Mode::Pressure)
        {
            // Never pick an immediate draw/repetition when pressing for a win
            if (c.immediateDraw)
            {
                c.finalScore = -5000.0 + double(c.evalCp);
                continue;
            }

            double lambda = (prof == Profile::Weak) ? 0.55 : 0.42;
            c.finalScore  = double(c.evalCp) + lambda * c.trapScore;
        }
        else if (mode == Mode::Swindle)
        {
            // When losing <= -150 cp, an immediate draw (stalemate or repetition) is a huge save!
            if (c.immediateDraw)
            {
                c.finalScore = 5000.0;
                continue;
            }

            // Penalize piece exchanges and entering simple lost endgames
            double exchangePenalty   = 0.045 * double(std::max(0, c.tradedNonPawnCp));
            double simpleEndgamePen  = (c.nonPawnAfterCp <= 1200) ? 15.0 : 0.0;
            double complicationBonus = (c.givesCheck ? 6.0 : 0.0) + (c.keepsOurQueen ? 8.0 : 0.0);

            c.finalScore = double(c.evalCp) + 0.65 * c.trapScore - exchangePenalty
                         - simpleEndgamePen + complicationBonus;
        }
        else if (mode == Mode::Convert)
        {
            // When winning >= +300 cp, strictly avoid stalemate, repetition, or 50-move draw
            if (c.immediateDraw)
            {
                c.finalScore = -10000.0;
                continue;
            }

            // Reward safe piece trades (simplification) and reducing opponent counterplay
            double simplifyBonus      = 0.025 * double(std::max(0, c.tradedNonPawnCp))
                                      + ((highRule50 && c.advances50Move) ? 8.0 : 0.0);
            double counterplayPenalty = 5.0 * double(c.oppChecks) + 3.0 * double(c.oppPieceThreats);

            c.finalScore = double(c.evalCp) + simplifyBonus - counterplayPenalty;
        }
    }

    usize bestIdx = 0;
    for (usize i = 1; i < candidates.size(); ++i)
    {
        // Require a meaningful margin improvement (>= 1.5 points) to switch away from candidate 0
        if (candidates[i].finalScore > candidates[bestIdx].finalScore + 1.5)
            bestIdx = i;
    }

    const auto& chosen = candidates[bestIdx];
    const auto& orig   = candidates[0];
    std::ostringstream rs;
    rs << std::fixed << std::setprecision(1);

    if (bestIdx == 0)
    {
        rs << "mantido " << UCIEngine::move(chosen.move, rootPos.is_chess960()) << " [armadilha="
           << chosen.trapScore << "cp, gap=" << chosen.uniquenessGapCp
           << "cp, erros=" << chosen.blunders100 << "]";
    }
    else
    {
        rs << "trocado " << UCIEngine::move(orig.move, rootPos.is_chess960()) << "->"
           << UCIEngine::move(chosen.move, rootPos.is_chess960()) << " [eval="
           << (chosen.evalCp - orig.evalCp) << "cp";
        if (mode == Mode::Pressure)
            rs << ", armadilha=" << chosen.trapScore << "cp, gap=" << chosen.uniquenessGapCp
               << "cp, erros=" << chosen.blunders100;
        else if (mode == Mode::Swindle)
            rs << ", troca=" << chosen.tradedNonPawnCp << "cp, armadilha=" << chosen.trapScore
               << "cp";
        else if (mode == Mode::Convert)
            rs << ", troca=" << chosen.tradedNonPawnCp << "cp, xeques_opp=" << chosen.oppChecks
               << ", ameacas_opp=" << chosen.oppPieceThreats;
        rs << "]";
    }

    lastReason = rs.str();
    return bestIdx;
}

std::string State::status_info_string(const OptionsMap& options) const {
    std::ostringstream ss;
    Profile            eff = effective_profile(options);
    ss << "SunTzu: perfil=" << profile_to_string(eff) << " (detectado="
       << profile_to_string(detectedProfile) << ", perda_ema=" << std::fixed << std::setprecision(1)
       << emaLossCp << "cp, amostras=" << samples
       << ", DrawAversion=" << current_draw_aversion_cp(options)
       << "cp, modo=" << mode_to_string(lastMode) << ", motivo=" << lastReason << ")";
    return ss.str();
}

State& global_state() {
    static State instance;
    return instance;
}

}  // namespace Stockfish::SunTzu
