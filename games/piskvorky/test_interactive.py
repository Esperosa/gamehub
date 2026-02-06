"""
Interactive AI Evaluation Test

I will play against each AI level on 8×8 and 13×13 boards
to evaluate:
1. Playability - Is it fun to play against?
2. Realism - Does it feel like playing against different skill levels?
3. Correct behavior - Does it follow the rules properly?
"""
import time
from engine import GameState, check_winner_fast, find_winning_move
from ai import best_move_easy, best_move_medium, best_move_hard, warmup, evaluate

def display_board(state: GameState):
    """Display the board with coordinates."""
    n = state.n
    
    # Column headers
    print("\n   ", end="")
    for c in range(n):
        print(f" {c:2}", end="")
    print()
    print("   " + "---" * n)
    
    for r in range(n):
        print(f"{r:2} |", end="")
        for c in range(n):
            idx = r * n + c
            cell = state.board[idx]
            if cell == 1:
                symbol = " X "
            elif cell == -1:
                symbol = " O "
            else:
                symbol = " . "
            print(symbol, end="")
        print(f"| {r}")
    
    print("   " + "---" * n)
    print("   ", end="")
    for c in range(n):
        print(f" {c:2}", end="")
    print()


def get_my_move(state: GameState) -> int:
    """I (the tester AI) will make a strategic move."""
    n = state.n
    me = state.to_move
    opp = -me
    
    # 1. Take win if available
    win = find_winning_move(state, me)
    if win is not None:
        return win
    
    # 2. Block opponent win
    block = find_winning_move(state, opp)
    if block is not None:
        return block
    
    # 3. Strategic move - prefer center and connected positions
    moves = state.smart_moves(radius=2)
    if not moves:
        center = n // 2
        return center * n + center
    
    # Score each move
    best_move = moves[0]
    best_score = -float('inf')
    
    for m in moves:
        r, c = m // n, m % n
        center = n // 2
        
        # Center preference
        dist = abs(r - center) + abs(c - center)
        score = (n - dist) * 10
        
        # Check if creates threat
        state.apply(m)
        my_eval = evaluate(state, me)
        state.undo(m)
        
        score += my_eval / 1000
        
        if score > best_score:
            best_score = score
            best_move = m
    
    return best_move


def play_test_game(n: int, ai_level: str, i_start: bool) -> dict:
    """
    Play a test game against AI.
    
    Returns analysis of the game.
    """
    state = GameState.new(n)
    game_log = []
    my_player = 1 if i_start else -1
    ai_player = -my_player
    
    print(f"\n{'='*60}")
    print(f"GAME: {n}×{n} board, Me ({'X' if my_player == 1 else 'O'}) vs {ai_level.upper()} AI ({'O' if my_player == 1 else 'X'})")
    print(f"Win condition: {state.win_len} in a row")
    print("="*60)
    
    move_count = 0
    ai_times = []
    ai_took_wins = 0
    ai_blocked_threats = 0
    ai_missed_blocks = 0
    ai_made_threats = 0
    
    while not state.is_full():
        winner = check_winner_fast(state)
        if winner is not None and winner != 0:
            break
        
        current = state.to_move
        
        if current == my_player:
            # My move
            move = get_my_move(state)
            r, c = move // n, move % n
            game_log.append(f"ME ({move_count+1}): ({r},{c})")
        else:
            # AI's move
            # Check if there's a winning move I'm leaving open
            my_threat = find_winning_move(state, my_player)
            ai_win = find_winning_move(state, ai_player)
            
            start = time.perf_counter()
            if ai_level == "easy":
                move = best_move_easy(state)
            elif ai_level == "medium":
                move = best_move_medium(state, ai_player)
            else:
                result = best_move_hard(state, ai_player, time_limit=0.3)
                move = result.move
            elapsed = time.perf_counter() - start
            ai_times.append(elapsed)
            
            r, c = move // n, move % n
            game_log.append(f"AI-{ai_level.upper()} ({move_count+1}): ({r},{c}) [{elapsed*1000:.0f}ms]")
            
            # Analyze AI's decision
            if ai_win is not None and move == ai_win:
                ai_took_wins += 1
            if my_threat is not None:
                if move == my_threat:
                    ai_blocked_threats += 1
                else:
                    ai_missed_blocks += 1
                    game_log[-1] += " [MISSED BLOCK!]"
            
            # Check if AI created a threat
            state.apply(move)
            new_threat = find_winning_move(state, ai_player)
            state.undo(move)
            if new_threat is not None:
                ai_made_threats += 1
        
        state.apply(move)
        move_count += 1
        
        # Display every few moves for longer games
        if n <= 8 or move_count <= 6 or move_count % 5 == 0:
            display_board(state)
            print(f"Move {move_count}: {'Me' if current == my_player else ai_level.upper()} -> ({r},{c})")
    
    # Final result
    display_board(state)
    winner = check_winner_fast(state)
    
    result = {
        "ai_level": ai_level,
        "board_size": n,
        "moves": move_count,
        "winner": "ME" if winner == my_player else ("AI" if winner == ai_player else "DRAW"),
        "ai_avg_time_ms": sum(ai_times) / len(ai_times) * 1000 if ai_times else 0,
        "ai_max_time_ms": max(ai_times) * 1000 if ai_times else 0,
        "ai_took_wins": ai_took_wins,
        "ai_blocked_threats": ai_blocked_threats,
        "ai_missed_blocks": ai_missed_blocks,
        "ai_made_threats": ai_made_threats,
        "game_log": game_log
    }
    
    print(f"\n--- RESULT: {result['winner']} wins in {move_count} moves ---")
    print(f"AI stats: {ai_blocked_threats} blocks, {ai_missed_blocks} missed, {ai_made_threats} threats created")
    print(f"AI timing: avg {result['ai_avg_time_ms']:.1f}ms, max {result['ai_max_time_ms']:.1f}ms")
    
    return result


def evaluate_ai_personality(results: list):
    """Evaluate AI behavior patterns."""
    print("\n" + "="*70)
    print("AI PERSONALITY ANALYSIS")
    print("="*70)
    
    for level in ["easy", "medium", "hard"]:
        level_results = [r for r in results if r["ai_level"] == level]
        if not level_results:
            continue
        
        total_blocks = sum(r["ai_blocked_threats"] for r in level_results)
        total_missed = sum(r["ai_missed_blocks"] for r in level_results)
        total_threats = sum(r["ai_made_threats"] for r in level_results)
        wins = sum(1 for r in level_results if r["winner"] == "AI")
        losses = sum(1 for r in level_results if r["winner"] == "ME")
        
        block_rate = total_blocks / max(1, total_blocks + total_missed) * 100
        
        print(f"\n{level.upper()} AI:")
        print(f"  Record: {wins}W - {losses}L")
        print(f"  Block rate: {block_rate:.0f}% ({total_blocks}/{total_blocks + total_missed})")
        print(f"  Threats created: {total_threats}")
        print(f"  Avg time: {sum(r['ai_avg_time_ms'] for r in level_results) / len(level_results):.1f}ms")
        
        # Personality assessment
        if level == "easy":
            if block_rate < 60:
                print("  ✓ Personality: Careless beginner - misses obvious threats")
            else:
                print("  ⚠ Personality: Too careful for Easy")
        elif level == "medium":
            if 50 < block_rate < 85:
                print("  ✓ Personality: Casual player - blocks most threats but not all")
            else:
                print("  ⚠ Personality: Block rate outside expected range")
        else:  # hard
            if block_rate > 90:
                print("  ✓ Personality: Expert player - rarely misses anything")
            else:
                print("  ⚠ Personality: Should block more threats")


def main():
    print("INTERACTIVE AI EVALUATION")
    print("Testing each AI level for playability and realism\n")
    
    print("Warming up Numba JIT...")
    warmup()
    print("Ready!\n")
    
    all_results = []
    
    # Test configurations
    tests = [
        # (board_size, ai_level, i_start_first)
        (8, "easy", True),
        (8, "easy", False),
        (8, "medium", True),
        (8, "medium", False),
        (8, "hard", True),
        (8, "hard", False),
        (13, "easy", True),
        (13, "easy", False),
        (13, "medium", True),
        (13, "medium", False),
        (13, "hard", True),
        (13, "hard", False),
    ]
    
    for n, level, i_start in tests:
        result = play_test_game(n, level, i_start)
        all_results.append(result)
        print("\n" + "-"*60)
        input_prompt = "Press Enter to continue to next game..."
        # Auto-continue for automated testing
        # In real interactive mode, uncomment: input(input_prompt)
    
    # Final evaluation
    evaluate_ai_personality(all_results)
    
    # Summary
    print("\n" + "="*70)
    print("FINAL EVALUATION SUMMARY")
    print("="*70)
    
    for level in ["easy", "medium", "hard"]:
        level_results = [r for r in all_results if r["ai_level"] == level]
        wins = sum(1 for r in level_results if r["winner"] == "AI")
        print(f"{level.upper()}: {wins}/{len(level_results)} games won against me")
    
    print("\n✓ Evaluation complete!")


if __name__ == "__main__":
    main()
