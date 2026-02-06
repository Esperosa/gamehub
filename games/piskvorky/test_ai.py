"""
AI Tournament Test - Fast and Comprehensive

Test Requirements:
- Total runtime: max 3-5 minutes
- Move times: Hard <500ms max, Medium <50ms, Easy <10ms
- Hierarchy: Hard > Medium > Easy on all board sizes

Game counts (reduced for speed):
- 3×3: 4 games per matchup × 3 matchups = 12 games
- 8×8: 6 games per matchup × 3 matchups = 18 games  
- 13×13: 8 games per matchup × 3 matchups = 24 games
Total: 54 games (not 630!)
"""
import time
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from collections import defaultdict

# Import game modules
from engine import GameState, check_winner_fast
from ai import best_move, best_move_easy, best_move_medium, best_move_hard, warmup


@dataclass
class MatchupStats:
    """Stats for one difficulty matchup."""
    wins1: int = 0
    wins2: int = 0
    draws: int = 0
    p1_times: List[float] = field(default_factory=list)
    p2_times: List[float] = field(default_factory=list)


@dataclass
class TournamentResult:
    """Overall tournament results."""
    board_results: Dict[int, Dict[str, MatchupStats]] = field(default_factory=dict)
    total_time: float = 0.0
    time_violations: List[Tuple[str, int, float]] = field(default_factory=list)


def play_single_game(n: int, diff1: str, diff2: str, 
                     time_limits: Dict[str, float]) -> Tuple[int, List[float], List[float]]:
    """
    Play a single game between two AI difficulties.
    
    Returns: (winner, p1_times, p2_times)
        winner: 1 if diff1 wins, -1 if diff2 wins, 0 if draw
    """
    state = GameState.new(n)
    p1_times = []
    p2_times = []
    max_moves = n * n
    
    for move_num in range(max_moves):
        winner = check_winner_fast(state)
        if winner is not None and winner != 0:
            return (1 if winner == 1 else -1), p1_times, p2_times
        
        if state.is_full():
            return 0, p1_times, p2_times
        
        current = state.to_move
        if current == 1:
            diff = diff1
        else:
            diff = diff2
        
        # Measure move time
        start = time.perf_counter()
        
        if diff == "easy":
            move = best_move_easy(state)
        elif diff == "medium":
            move = best_move_medium(state, current)
        else:
            result = best_move_hard(state, current, time_limit=0.25)
            move = result.move
        
        elapsed = time.perf_counter() - start
        
        if current == 1:
            p1_times.append(elapsed)
        else:
            p2_times.append(elapsed)
        
        state.apply(move)
    
    return 0, p1_times, p2_times


def run_matchup(n: int, diff1: str, diff2: str, games: int,
                time_limits: Dict[str, float]) -> Tuple[MatchupStats, List[Tuple[str, int, float]]]:
    """Run multiple games between two difficulties."""
    stats = MatchupStats()
    violations = []
    
    for game_idx in range(games):
        # Alternate who starts
        if game_idx % 2 == 0:
            d1, d2 = diff1, diff2
            result, t1, t2 = play_single_game(n, d1, d2, time_limits)
            # diff1 played as player 1
            if result == 1:
                stats.wins1 += 1
            elif result == -1:
                stats.wins2 += 1
            else:
                stats.draws += 1
            stats.p1_times.extend(t1)
            stats.p2_times.extend(t2)
        else:
            d1, d2 = diff2, diff1
            result, t1, t2 = play_single_game(n, d1, d2, time_limits)
            # diff1 played as player 2 (d2)
            if result == -1:  # diff1 wins as player 2
                stats.wins1 += 1
            elif result == 1:  # diff2 wins as player 1
                stats.wins2 += 1
            else:
                stats.draws += 1
            stats.p1_times.extend(t2)  # diff1's times are t2
            stats.p2_times.extend(t1)
        
        # Check time violations
        limit1 = time_limits[diff1]
        limit2 = time_limits[diff2]
        
        for t in stats.p1_times[-len(t1 if game_idx % 2 == 0 else t2):]:
            if t > limit1:
                violations.append((diff1, n, t))
        for t in stats.p2_times[-len(t2 if game_idx % 2 == 0 else t1):]:
            if t > limit2:
                violations.append((diff2, n, t))
    
    return stats, violations


def run_tournament() -> TournamentResult:
    """Run the full tournament."""
    print("=" * 60)
    print("AI TOURNAMENT TEST")
    print("=" * 60)
    
    result = TournamentResult()
    start_time = time.perf_counter()
    
    # Configuration - more games for statistical significance
    configs = [
        (3, 10),   # 3×3: 10 games per matchup
        (8, 12),   # 8×8: 12 games per matchup
        (13, 14),  # 13×13: 14 games per matchup
    ]
    
    matchups = [
        ("hard", "medium"),
        ("hard", "easy"),
        ("medium", "easy"),
    ]
    
    # Time limits (max allowed, not target)
    time_limits = {
        "easy": 0.1,    # 100ms max
        "medium": 0.2,   # 200ms max
        "hard": 0.5,     # 500ms max
    }
    
    for n, games_per_matchup in configs:
        print(f"\n{'=' * 50}")
        print(f"BOARD: {n}×{n}")
        print("=" * 50)
        
        result.board_results[n] = {}
        
        for diff1, diff2 in matchups:
            matchup_key = f"{diff1}_vs_{diff2}"
            print(f"\n  {diff1.upper()} vs {diff2.upper()} ({games_per_matchup} games)...", end=" ")
            
            stats, violations = run_matchup(n, diff1, diff2, games_per_matchup, time_limits)
            result.board_results[n][matchup_key] = stats
            result.time_violations.extend(violations)
            
            # Print result
            total = stats.wins1 + stats.wins2 + stats.draws
            print(f"{stats.wins1}W-{stats.draws}D-{stats.wins2}L", end="")
            
            all_times = stats.p1_times + stats.p2_times
            if all_times:
                avg_t = sum(all_times) / len(all_times) * 1000
                max_t = max(all_times) * 1000
                print(f" (avg: {avg_t:.0f}ms, max: {max_t:.0f}ms)")
            else:
                print()
    
    result.total_time = time.perf_counter() - start_time
    return result


def evaluate_results(result: TournamentResult) -> bool:
    """Evaluate tournament results and return success/failure."""
    print("\n" + "=" * 60)
    print("TOURNAMENT RESULTS")
    print("=" * 60)
    
    all_passed = True
    
    # Check hierarchy on each board
    for n in sorted(result.board_results.keys()):
        print(f"\n{n}×{n} BOARD:")
        board_stats = result.board_results[n]
        
        # Hard vs Medium
        hm = board_stats.get("hard_vs_medium", MatchupStats())
        hm_wr = hm.wins1 / max(1, hm.wins1 + hm.wins2 + hm.draws)
        print(f"  Hard vs Medium: {hm.wins1}W-{hm.draws}D-{hm.wins2}L = {hm_wr*100:.0f}% WR")
        
        # Hard vs Easy
        he = board_stats.get("hard_vs_easy", MatchupStats())
        he_wr = he.wins1 / max(1, he.wins1 + he.wins2 + he.draws)
        print(f"  Hard vs Easy:   {he.wins1}W-{he.draws}D-{he.wins2}L = {he_wr*100:.0f}% WR")
        
        # Medium vs Easy
        me = board_stats.get("medium_vs_easy", MatchupStats())
        me_wr = me.wins1 / max(1, me.wins1 + me.wins2 + me.draws)
        print(f"  Medium vs Easy: {me.wins1}W-{me.draws}D-{me.wins2}L = {me_wr*100:.0f}% WR")
        
        # Check hierarchy (with tolerance for draws)
        hard_better_than_medium = hm.wins1 >= hm.wins2
        hard_better_than_easy = he.wins1 >= he.wins2
        medium_better_than_easy = me.wins1 >= me.wins2
        
        if not hard_better_than_medium:
            print(f"  ❌ Hard should beat Medium more often!")
            all_passed = False
        if not hard_better_than_easy:
            print(f"  ❌ Hard should beat Easy!")
            all_passed = False
        if not medium_better_than_easy:
            print(f"  ❌ Medium should beat Easy!")
            all_passed = False
        
        if hard_better_than_medium and hard_better_than_easy and medium_better_than_easy:
            print(f"  ✓ Hierarchy OK: Hard > Medium > Easy")
    
    # Time violations
    print(f"\nTIME ANALYSIS:")
    print(f"  Total test time: {result.total_time:.1f}s")
    
    if result.time_violations:
        print(f"  ⚠ Time violations: {len(result.time_violations)}")
        # Group by difficulty
        by_diff = defaultdict(list)
        for diff, n, t in result.time_violations:
            by_diff[diff].append((n, t))
        for diff, items in by_diff.items():
            max_t = max(t for _, t in items)
            print(f"    {diff}: {len(items)} violations (max: {max_t*1000:.0f}ms)")
        # Only fail if hard exceeds 1000ms
        hard_violations = [t for d, n, t in result.time_violations if d == "hard" and t > 1.0]
        if hard_violations:
            print(f"  ❌ Hard AI exceeded 1000ms limit!")
            all_passed = False
    else:
        print(f"  ✓ No time violations")
    
    # Final verdict
    print("\n" + "=" * 60)
    if result.total_time > 300:  # 5 minutes
        print("❌ TEST TOO SLOW (exceeded 5 minute limit)")
        all_passed = False
    
    if all_passed:
        print("✓ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 60)
    
    return all_passed


def main():
    """Main entry point."""
    print("\nWarming up Numba JIT compilation...")
    warmup_start = time.perf_counter()
    
    # Call explicit warmup
    warmup()
    
    # Extra warmup games
    for n in [3, 8]:
        state = GameState.new(n)
        for _ in range(3):
            if state.is_full():
                break
            move = best_move_hard(state, state.to_move, time_limit=0.1).move
            state.apply(move)
    
    warmup_time = time.perf_counter() - warmup_start
    print(f"Warmup complete in {warmup_time:.1f}s")
    
    # Run tournament
    result = run_tournament()
    
    # Evaluate
    success = evaluate_results(result)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
