/*
  SunTzu — "Arte da Guerra" Opponent Model & 3-1-0 Draw Aversion Module (Phase 4)
  Based on Stockfish, a UCI chess playing engine derived from Glaurung 2.1
  SPDX-License-Identifier: GPL-3.0-or-later
*/

#include "suntzu.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>

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

void State::reset() {
    hasPrevEval       = false;
    prevSide          = WHITE;
    prevPly           = 0;
    prevEvalCp        = 0;
    lastEvalCp        = 0;
    emaLossCp         = 25.0;
    samples           = 0;
    detectedProfile   = Profile::Medium;
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

std::string State::status_info_string(const OptionsMap& options) const {
    std::ostringstream ss;
    Profile            eff = effective_profile(options);
    ss << "SunTzu: perfil=" << profile_to_string(eff) << " (detectado="
       << profile_to_string(detectedProfile) << ", perda_ema=" << std::fixed << std::setprecision(1)
       << emaLossCp << "cp, amostras=" << samples
       << ", DrawAversion=" << current_draw_aversion_cp(options) << "cp)";
    return ss.str();
}

State& global_state() {
    static State instance;
    return instance;
}

}  // namespace Stockfish::SunTzu
