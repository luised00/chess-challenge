/*
  Stockfish, a UCI chess playing engine derived from Glaurung 2.1
  Copyright (C) 2004-2026 The Stockfish developers (see AUTHORS file)

  Stockfish is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  Stockfish is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

#include "timeman.h"

#include <algorithm>
#include <cassert>
#include <cmath>

#include "search.h"
#include "ucioption.h"

namespace Stockfish {

TimePoint TimeManagement::optimum() const { return optimumTime; }
TimePoint TimeManagement::maximum() const { return maximumTime; }

void TimeManagement::clear() {
    availableNodes = -1;  // When in 'nodes as time' mode
}

void TimeManagement::advance_nodes_time(i64 nodes) {
    assert(useNodesTime);
    availableNodes = std::max(i64(0), availableNodes - nodes);
}

// Called at the beginning of the search and calculates
// the bounds of time allowed for the current game ply. We currently support:
//      1) x basetime (+ z increment)
//      2) x moves in y seconds (+ z increment)
void TimeManagement::init(Search::LimitsType& limits,
                          Color               us,
                          int                 ply,
                          const OptionsMap&   options,
                          double&             originalTimeAdjust,
                          int                 pieceCount) {
    TimePoint npmsec = TimePoint(options["nodestime"]);

    // If we have no time, we don't need to fully initialize TM.
    // startTime is used by movetime and useNodesTime is used in elapsed calls.
    startTime     = limits.startTime;
    useNodesTime  = npmsec != 0;
    criticalPanic = false;
    extremePanic  = false;

    if (useNodesTime)
        limits.movetime *= npmsec;

    if (limits.time[us] == 0)
    {
        optimumTime = maximumTime = NoBound;
        return;
    }

    TimePoint moveOverhead          = TimePoint(options["Move Overhead"]);
    TimePoint physicalBoardOverhead = TimePoint(options["PhysicalBoardOverhead"]);
    TimePoint panicReserveSec       = TimePoint(options["PanicReserve"]);
    bool      fastProfile           = (options["TimeProfile"] == "rapido");

    // optScale is a percentage of available time to use for the current move.
    // maxScale is a multiplier applied to optimumTime.
    double optScale, maxScale;

    // If we have to play in 'nodes as time' mode, then convert from time
    // to nodes, and use resulting values in time management formulas.
    // WARNING: to avoid time losses, the given npmsec (nodes per millisecond)
    // must be much lower than the real engine speed.
    if (useNodesTime)
    {
        if (availableNodes == -1)                       // Only once at game start
            availableNodes = npmsec * limits.time[us];  // Time is in msec

        // Convert from milliseconds to nodes
        limits.time[us] = TimePoint(availableNodes);
        limits.inc[us] *= npmsec;
        limits.npmsec = npmsec;
        moveOverhead *= npmsec;
        physicalBoardOverhead *= npmsec;
    }

    // These numbers are used where multiplications, divisions,
    // or comparisons with constants are involved.
    const i64       scaleFactor = useNodesTime ? npmsec : 1;
    const TimePoint scaledTime  = std::max(TimePoint(1), limits.time[us] / scaleFactor);

    // Dynamic remaining moves horizon N estimated from board material and game ply.
    // In sudden death with physical board overhead, games can stretch to 80-120 moves,
    // so we keep a conservative floor of 32 moves remaining to protect the clock.
    int moveNum        = 1 + ply / 2;
    int clampedPieces  = std::clamp(pieceCount, 2, 32);
    int dynamicHorizon = 30 + (clampedPieces * 24) / 32 - std::min(8, moveNum / 12);
    if (fastProfile)
        dynamicHorizon = std::max(24, dynamicHorizon * 4 / 5);
    dynamicHorizon = std::clamp(dynamicHorizon, 28, 52);

    // Maximum move horizon
    int mtg = limits.movestogo ? std::min(limits.movestogo, 50) : dynamicHorizon;

    // If less than one second, gradually reduce mtg.
    // In cyclic time controls we keep the actual movestogo as horizon.
    if (scaledTime < 1000 && limits.movestogo == 0)
        mtg = std::max(1, int(scaledTime * 0.05));

    // Scale panic reserve if playing a shorter time control than standard 25 min
    TimePoint reserveMs = panicReserveSec * 1000 * scaleFactor;
    if (fastProfile)
        reserveMs = reserveMs * 2 / 3;
    reserveMs = std::min(reserveMs, limits.time[us] / 5);

    TimePoint totalOverhead = moveOverhead + physicalBoardOverhead;

    // Make sure timeLeft is > 0 since we may use it as a divisor
    TimePoint timeLeft = std::max(TimePoint(1), limits.time[us] + limits.inc[us] * (mtg - 1)
                                                  - reserveMs - totalOverhead * (2 + mtg));

    // x basetime (+ z increment)
    // If there is a healthy increment, timeLeft can exceed the actual available
    // game time for the current move, so also cap to a percentage of available game time.
    if (limits.movestogo == 0)
    {
        // Extra time according to timeLeft
        if (originalTimeAdjust < 0)
            originalTimeAdjust = 0.3272 * std::log10(timeLeft) - 0.4141;

        // Calculate time constants based on current time left.
        double logTimeInSec = std::log10(scaledTime / 1000.0);
        double optConstant  = std::min(0.0029869 + 0.00033554 * logTimeInSec, 0.004905);
        double maxConstant  = std::max(3.3744 + 3.0608 * logTimeInSec, 3.1441);

        optScale = std::min(0.012112 + std::pow(ply + 3.22713, 0.46866) * optConstant,
                            0.19404 * limits.time[us] / timeLeft)
                 * originalTimeAdjust;

        maxScale = std::min(6.873, maxConstant + ply / 12.352);
    }

    // x moves in y seconds (+ z increment)
    else
    {
        optScale = std::min((0.88 + ply / 116.4) / mtg, 0.88 * limits.time[us] / timeLeft);
        maxScale = 1.3 + 0.11 * mtg;
    }

    // Limit the maximum possible time for this move
    optimumTime = TimePoint(std::max(1.0, optScale * timeLeft));
    maximumTime =
      TimePoint(std::max(double(optimumTime), std::min(0.8097 * limits.time[us] - totalOverhead,
                                                       maxScale * optimumTime)));

    // SunTzu Physical Board & Sudden Death budget model:
    // t_base = (T - R - N * H) / N
    if (physicalBoardOverhead > 0 || fastProfile)
    {
        TimePoint usableForThink =
          limits.time[us] + limits.inc[us] * (mtg - 1) - reserveMs - totalOverhead * mtg;

        if (usableForThink > 0)
        {
            TimePoint tBase = std::max(TimePoint(5 * scaleFactor), usableForThink / mtg);
            optimumTime     = std::min(optimumTime, TimePoint(tBase * 0.90));
            maximumTime     = std::min(maximumTime, TimePoint(tBase * 2.20));
        }
        else
        {
            // Clock is eating into PanicReserve or overhead budget: play nearly instant
            criticalPanic = true;
            optimumTime   = std::min(optimumTime, TimePoint(4 * scaleFactor));
            maximumTime   = std::min(maximumTime, TimePoint(15 * scaleFactor));
        }

        // Panic thresholds on physical clock:
        // Below 3 min (180s, or 36 * H), cut budget in half.
        // Below 60s (or 22 * H), enter critical panic (< 1s response, depth limited).
        // Below 15 * H, enter extreme panic (stop after depth 1-2, ~1ms think time).
        TimePoint overheadScaled = totalOverhead / scaleFactor;
        TimePoint panicWarnMs =
          std::max(TimePoint(1), std::max((reserveMs / scaleFactor) * 3 / 2, overheadScaled * 36));
        TimePoint panicCritMs =
          std::max(TimePoint(1), std::max((reserveMs / scaleFactor) / 2, overheadScaled * 22));
        TimePoint panicExtremeMs = std::max(TimePoint(1), overheadScaled * 15);

        if (scaledTime < panicExtremeMs)
        {
            criticalPanic = true;
            extremePanic  = true;
            optimumTime   = TimePoint(1 * scaleFactor);
            maximumTime   = TimePoint(5 * scaleFactor);
        }
        else if (scaledTime < panicCritMs)
        {
            criticalPanic   = true;
            TimePoint capMs = std::min(TimePoint(400 * scaleFactor),
                                       std::max(TimePoint(5 * scaleFactor),
                                                (limits.time[us] - totalOverhead * 12) / 20));
            optimumTime     = std::min(optimumTime, std::max(TimePoint(2 * scaleFactor), capMs / 3));
            maximumTime     = std::min(maximumTime, capMs);
        }
        else if (scaledTime < panicWarnMs)
        {
            optimumTime = std::max(TimePoint(5 * scaleFactor), optimumTime / 2);
            maximumTime = std::max(optimumTime, maximumTime / 2);
        }
    }

    if (options["Ponder"])
        optimumTime += optimumTime / 4;
}

}  // namespace Stockfish
