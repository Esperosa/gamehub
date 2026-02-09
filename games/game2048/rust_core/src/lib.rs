use once_cell::sync::Lazy;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::HashMap;
use std::time::{Duration, Instant};

const DIR_UP: i32 = 0;
const DIR_DOWN: i32 = 1;
const DIR_LEFT: i32 = 2;
const DIR_RIGHT: i32 = 3;

const MAX_EXP: u8 = 15;
const WEIGHT_COUNT: usize = 15;
const CHANCE_FULL_ENUM_EMPTY_THRESHOLD: usize = 6;

const W_GRADIENT: usize = 0;
const W_CORNER_BONUS: usize = 1;
const W_CORNER_DIST_PENALTY: usize = 2;
const W_EMPTY: usize = 3;
const W_MONOTONICITY: usize = 4;
const W_SMOOTHNESS: usize = 5;
const W_MERGE: usize = 6;
const W_NEAR_2048: usize = 7;
const W_LEFT_BIAS: usize = 8;
const W_UP_BIAS: usize = 9;
const W_RIGHT_PENALTY: usize = 10;
const W_DOWN_PENALTY: usize = 11;
const W_CORNER_BREAK_PENALTY: usize = 12;
const W_MOVE_SCORE_SCALE: usize = 13;
const W_TERMINAL_PENALTY: usize = 14;

const FLAT_GRADIENT: [f64; 16] = [
    1.0,
    0.5,
    0.25,
    0.125,
    0.007_812_5,
    0.015_625,
    0.031_25,
    0.062_5,
    0.003_906_25,
    0.001_953_125,
    0.000_976_562_5,
    0.000_488_281_25,
    0.000_030_517_578_125,
    0.000_061_035_156_25,
    0.000_122_070_312_5,
    0.000_244_140_625,
];

struct Tables {
    row_left: Vec<u16>,
    row_right: Vec<u16>,
    row_left_gain: Vec<u32>,
    row_right_gain: Vec<u32>,
    row_empty_count: Vec<u8>,
    row_empty_mask: Vec<u8>,
    row_smooth: Vec<f64>,
    row_merge: Vec<f64>,
    row_mono: Vec<f64>,
    row_max_exp: Vec<u8>,
    row_max_col: Vec<u8>,
    row_gradient_0: Vec<f64>,
    row_gradient_1: Vec<f64>,
    row_gradient_2: Vec<f64>,
    row_gradient_3: Vec<f64>,
}

fn reverse_row(row: u16) -> u16 {
    ((row & 0x000F) << 12)
        | ((row & 0x00F0) << 4)
        | ((row & 0x0F00) >> 4)
        | ((row & 0xF000) >> 12)
}

fn line_monotonicity_penalty_nonzero(v0: u8, v1: u8, v2: u8, v3: u8) -> f64 {
    let mut compressed = [0u8; 4];
    let mut count = 0usize;
    for &v in &[v0, v1, v2, v3] {
        if v > 0 {
            compressed[count] = v;
            count += 1;
        }
    }
    if count <= 1 {
        return 0.0;
    }
    let mut inc = 0.0;
    let mut dec = 0.0;
    for i in 0..(count - 1) {
        let a = compressed[i] as f64;
        let b = compressed[i + 1] as f64;
        if a > b {
            inc += a - b;
        } else {
            dec += b - a;
        }
    }
    inc.min(dec)
}

fn slide_row_left(row: u16) -> (u16, u32) {
    let exps = [
        (row & 0xF) as u8,
        ((row >> 4) & 0xF) as u8,
        ((row >> 8) & 0xF) as u8,
        ((row >> 12) & 0xF) as u8,
    ];

    let mut vals = [0u8; 4];
    let mut vals_count = 0usize;
    for &e in &exps {
        if e != 0 {
            vals[vals_count] = e;
            vals_count += 1;
        }
    }

    let mut merged = [0u8; 4];
    let mut merged_count = 0usize;
    let mut gain = 0u32;
    let mut i = 0usize;
    while i < vals_count {
        if i + 1 < vals_count && vals[i] == vals[i + 1] {
            let mut exp = vals[i] + 1;
            if exp > MAX_EXP {
                exp = MAX_EXP;
            }
            merged[merged_count] = exp;
            merged_count += 1;
            gain += 1u32 << exp;
            i += 2;
        } else {
            merged[merged_count] = vals[i];
            merged_count += 1;
            i += 1;
        }
    }

    let out = (merged[0] as u16)
        | ((merged[1] as u16) << 4)
        | ((merged[2] as u16) << 8)
        | ((merged[3] as u16) << 12);
    (out, gain)
}

fn build_tables() -> Tables {
    let mut row_left = vec![0u16; 65536];
    let mut row_right = vec![0u16; 65536];
    let mut row_left_gain = vec![0u32; 65536];
    let mut row_right_gain = vec![0u32; 65536];
    let mut row_empty_count = vec![0u8; 65536];
    let mut row_empty_mask = vec![0u8; 65536];
    let mut row_smooth = vec![0.0f64; 65536];
    let mut row_merge = vec![0.0f64; 65536];
    let mut row_mono = vec![0.0f64; 65536];
    let mut row_max_exp = vec![0u8; 65536];
    let mut row_max_col = vec![0u8; 65536];
    let mut row_gradient_0 = vec![0.0f64; 65536];
    let mut row_gradient_1 = vec![0.0f64; 65536];
    let mut row_gradient_2 = vec![0.0f64; 65536];
    let mut row_gradient_3 = vec![0.0f64; 65536];

    for row in 0u32..65536u32 {
        let r = row as u16;
        let a = (r & 0xF) as u8;
        let b = ((r >> 4) & 0xF) as u8;
        let c = ((r >> 8) & 0xF) as u8;
        let d = ((r >> 12) & 0xF) as u8;
        let exps = [a, b, c, d];

        let mut empty_count = 0u8;
        let mut empty_mask = 0u8;
        for (idx, &v) in exps.iter().enumerate() {
            if v == 0 {
                empty_count += 1;
                empty_mask |= 1u8 << idx;
            }
        }
        row_empty_count[row as usize] = empty_count;
        row_empty_mask[row as usize] = empty_mask;
        row_mono[row as usize] = line_monotonicity_penalty_nonzero(a, b, c, d);

        let mut smooth = 0.0;
        let mut merge = 0.0;
        for i in 0..3usize {
            let x = exps[i];
            let y = exps[i + 1];
            if x > 0 && y > 0 {
                let diff = (x as f64 - y as f64).abs();
                smooth += diff * diff;
                if x == y {
                    merge += x as f64;
                }
            }
        }
        row_smooth[row as usize] = smooth;
        row_merge[row as usize] = merge;

        let mut max_exp = 0u8;
        let mut max_col = 0u8;
        for i in 0..4usize {
            if exps[i] > max_exp {
                max_exp = exps[i];
                max_col = i as u8;
            }
        }
        row_max_exp[row as usize] = max_exp;
        row_max_col[row as usize] = max_col;

        row_gradient_0[row as usize] = (a as f64) * FLAT_GRADIENT[0]
            + (b as f64) * FLAT_GRADIENT[1]
            + (c as f64) * FLAT_GRADIENT[2]
            + (d as f64) * FLAT_GRADIENT[3];
        row_gradient_1[row as usize] = (a as f64) * FLAT_GRADIENT[4]
            + (b as f64) * FLAT_GRADIENT[5]
            + (c as f64) * FLAT_GRADIENT[6]
            + (d as f64) * FLAT_GRADIENT[7];
        row_gradient_2[row as usize] = (a as f64) * FLAT_GRADIENT[8]
            + (b as f64) * FLAT_GRADIENT[9]
            + (c as f64) * FLAT_GRADIENT[10]
            + (d as f64) * FLAT_GRADIENT[11];
        row_gradient_3[row as usize] = (a as f64) * FLAT_GRADIENT[12]
            + (b as f64) * FLAT_GRADIENT[13]
            + (c as f64) * FLAT_GRADIENT[14]
            + (d as f64) * FLAT_GRADIENT[15];

        let (left_row, left_gain) = slide_row_left(r);
        row_left[row as usize] = left_row;
        row_left_gain[row as usize] = left_gain;

        let reversed = reverse_row(r);
        let (rev_moved, right_gain) = slide_row_left(reversed);
        let right_row = reverse_row(rev_moved);
        row_right[row as usize] = right_row;
        row_right_gain[row as usize] = right_gain;
    }

    Tables {
        row_left,
        row_right,
        row_left_gain,
        row_right_gain,
        row_empty_count,
        row_empty_mask,
        row_smooth,
        row_merge,
        row_mono,
        row_max_exp,
        row_max_col,
        row_gradient_0,
        row_gradient_1,
        row_gradient_2,
        row_gradient_3,
    }
}

static TABLES: Lazy<Tables> = Lazy::new(build_tables);

fn transpose_board(board: u64) -> u64 {
    let mut result = 0u64;
    for r in 0..4u64 {
        for c in 0..4u64 {
            let src_shift = 4 * (r * 4 + c);
            let dst_shift = 4 * (c * 4 + r);
            result |= ((board >> src_shift) & 0xF) << dst_shift;
        }
    }
    result
}

fn move_left_board(board: u64) -> (u64, u32, bool) {
    let t = &*TABLES;
    let r0 = (board & 0xFFFF) as usize;
    let r1 = ((board >> 16) & 0xFFFF) as usize;
    let r2 = ((board >> 32) & 0xFFFF) as usize;
    let r3 = ((board >> 48) & 0xFFFF) as usize;

    let n0 = t.row_left[r0] as u64;
    let n1 = t.row_left[r1] as u64;
    let n2 = t.row_left[r2] as u64;
    let n3 = t.row_left[r3] as u64;
    let new_board = n0 | (n1 << 16) | (n2 << 32) | (n3 << 48);
    let gain = t.row_left_gain[r0] + t.row_left_gain[r1] + t.row_left_gain[r2] + t.row_left_gain[r3];
    (new_board, gain, new_board != board)
}

fn move_right_board(board: u64) -> (u64, u32, bool) {
    let t = &*TABLES;
    let r0 = (board & 0xFFFF) as usize;
    let r1 = ((board >> 16) & 0xFFFF) as usize;
    let r2 = ((board >> 32) & 0xFFFF) as usize;
    let r3 = ((board >> 48) & 0xFFFF) as usize;

    let n0 = t.row_right[r0] as u64;
    let n1 = t.row_right[r1] as u64;
    let n2 = t.row_right[r2] as u64;
    let n3 = t.row_right[r3] as u64;
    let new_board = n0 | (n1 << 16) | (n2 << 32) | (n3 << 48);
    let gain = t.row_right_gain[r0] + t.row_right_gain[r1] + t.row_right_gain[r2] + t.row_right_gain[r3];
    (new_board, gain, new_board != board)
}

fn move_up_board(board: u64) -> (u64, u32, bool) {
    let tr = transpose_board(board);
    let (moved, gain, _) = move_left_board(tr);
    let new_board = transpose_board(moved);
    (new_board, gain, new_board != board)
}

fn move_down_board(board: u64) -> (u64, u32, bool) {
    let tr = transpose_board(board);
    let (moved, gain, _) = move_right_board(tr);
    let new_board = transpose_board(moved);
    (new_board, gain, new_board != board)
}

fn simulate_move(board: u64, direction: i32) -> (u64, u32, bool) {
    match direction {
        DIR_LEFT => move_left_board(board),
        DIR_RIGHT => move_right_board(board),
        DIR_UP => move_up_board(board),
        _ => move_down_board(board),
    }
}

fn get_cell_exp(board: u64, idx: usize) -> u8 {
    ((board >> (idx * 4)) & 0xF) as u8
}

fn max_exp_idx(board: u64) -> (u8, usize) {
    let mut max_exp = 0u8;
    let mut max_idx = 0usize;
    for idx in 0..16usize {
        let e = get_cell_exp(board, idx);
        if e > max_exp {
            max_exp = e;
            max_idx = idx;
        }
    }
    (max_exp, max_idx)
}

fn empty_mask_board(board: u64) -> u16 {
    let t = &*TABLES;
    let r0 = (board & 0xFFFF) as usize;
    let r1 = ((board >> 16) & 0xFFFF) as usize;
    let r2 = ((board >> 32) & 0xFFFF) as usize;
    let r3 = ((board >> 48) & 0xFFFF) as usize;
    (t.row_empty_mask[r0] as u16)
        | ((t.row_empty_mask[r1] as u16) << 4)
        | ((t.row_empty_mask[r2] as u16) << 8)
        | ((t.row_empty_mask[r3] as u16) << 12)
}

fn board_sampling_seed(board: u64, ply: usize) -> u64 {
    let mut x = board;
    x ^= ((ply as u64).wrapping_add(1)).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    x ^= x >> 33;
    x = x.wrapping_mul(0xFF51_AFD7_ED55_8CCD);
    x ^= x >> 33;
    x = x.wrapping_mul(0xC4CE_B9FE_1A85_EC53);
    x ^= x >> 33;
    x
}

fn pick_bit_by_rank(mask: u16, rank: usize) -> u16 {
    let mut m = mask;
    let mut r = rank;
    while m != 0 {
        let lsb = m & m.wrapping_neg();
        if r == 0 {
            return lsb;
        }
        r -= 1;
        m ^= lsb;
    }
    0
}

fn sample_empty_mask(mask: u16, sample_count: usize, seed: u64) -> u16 {
    let total = mask.count_ones() as usize;
    if sample_count >= total {
        return mask;
    }
    let mut out = 0u16;
    let mut remaining_mask = mask;
    let mut remaining = total;
    let mut state = (seed | 1) as u64;
    for _ in 0..sample_count {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        let pick_rank = (state % (remaining.max(1) as u64)) as usize;
        let chosen = pick_bit_by_rank(remaining_mask, pick_rank);
        if chosen == 0 {
            break;
        }
        out |= chosen;
        remaining_mask ^= chosen;
        remaining = remaining.saturating_sub(1);
    }
    out
}

fn positions_stats(positions: &[(i32, i32)]) -> (bool, i32) {
    if positions.len() < 2 {
        return (false, 99);
    }
    let mut has_adjacent = false;
    let mut min_dist = 99i32;
    for i in 0..positions.len() {
        for j in (i + 1)..positions.len() {
            let (r1, c1) = positions[i];
            let (r2, c2) = positions[j];
            let dist = (r1 - r2).abs() + (c1 - c2).abs();
            if dist == 1 {
                has_adjacent = true;
            }
            if dist < min_dist {
                min_dist = dist;
            }
        }
    }
    (has_adjacent, min_dist)
}

fn near_2048_potential(board: u64, max_exp: u8, max_idx: usize, empty_count: usize) -> f64 {
    if max_exp < 9 {
        return 0.0;
    }
    let mut p512: Vec<(i32, i32)> = Vec::new();
    let mut p1024: Vec<(i32, i32)> = Vec::new();
    for idx in 0..16usize {
        let exp = get_cell_exp(board, idx);
        if exp == 9 {
            p512.push(((idx / 4) as i32, (idx % 4) as i32));
        } else if exp == 10 {
            p1024.push(((idx / 4) as i32, (idx % 4) as i32));
        }
    }

    let (adj1024, dist1024) = positions_stats(&p1024);
    let (adj512, dist512) = positions_stats(&p512);
    let count1024 = p1024.len() as f64;
    let count512 = p512.len() as f64;

    let mut score = 0.0;
    if max_exp >= 10 {
        score += count1024 * 520.0;
        if adj1024 {
            score += 4600.0;
        } else if p1024.len() >= 2 {
            score += (2600.0 - (dist1024 as f64) * 420.0).max(0.0);
        }
        score += count512 * 140.0;
        if p1024.len() == 1 && p512.len() >= 2 {
            score += 900.0;
        }
    } else {
        score += count512 * 220.0;
        if adj512 {
            score += 1700.0;
        } else if p512.len() >= 2 {
            score += (1200.0 - (dist512 as f64) * 180.0).max(0.0);
        }
    }

    if max_idx == 0 {
        score += 350.0;
    } else if max_exp >= 10 {
        score -= 450.0;
    }

    let mut safety = (empty_count as f64) / 8.0;
    if safety > 1.0 {
        safety = 1.0;
    }
    if safety < 0.15 {
        safety = 0.15;
    }
    score * safety
}

fn evaluate_board(board: u64, weights: &[f64; WEIGHT_COUNT]) -> f64 {
    let t = &*TABLES;
    let r0 = (board & 0xFFFF) as usize;
    let r1 = ((board >> 16) & 0xFFFF) as usize;
    let r2 = ((board >> 32) & 0xFFFF) as usize;
    let r3 = ((board >> 48) & 0xFFFF) as usize;
    let rows = [r0, r1, r2, r3];

    let empty_count =
        (t.row_empty_count[r0] + t.row_empty_count[r1] + t.row_empty_count[r2] + t.row_empty_count[r3]) as usize;
    let gradient_score =
        t.row_gradient_0[r0] + t.row_gradient_1[r1] + t.row_gradient_2[r2] + t.row_gradient_3[r3];
    let mut smoothness_penalty = t.row_smooth[r0] + t.row_smooth[r1] + t.row_smooth[r2] + t.row_smooth[r3];
    let mut merge_score = t.row_merge[r0] + t.row_merge[r1] + t.row_merge[r2] + t.row_merge[r3];
    let mut mono_penalty = t.row_mono[r0] + t.row_mono[r1] + t.row_mono[r2] + t.row_mono[r3];

    let tr = transpose_board(board);
    let c0 = (tr & 0xFFFF) as usize;
    let c1 = ((tr >> 16) & 0xFFFF) as usize;
    let c2 = ((tr >> 32) & 0xFFFF) as usize;
    let c3 = ((tr >> 48) & 0xFFFF) as usize;
    smoothness_penalty += t.row_smooth[c0] + t.row_smooth[c1] + t.row_smooth[c2] + t.row_smooth[c3];
    merge_score += t.row_merge[c0] + t.row_merge[c1] + t.row_merge[c2] + t.row_merge[c3];
    mono_penalty += t.row_mono[c0] + t.row_mono[c1] + t.row_mono[c2] + t.row_mono[c3];

    let mut max_exp = 0u8;
    let mut max_idx = 0usize;
    for (row_i, row_bits) in rows.iter().enumerate() {
        let row_exp = t.row_max_exp[*row_bits];
        if row_exp > max_exp {
            max_exp = row_exp;
            max_idx = row_i * 4 + t.row_max_col[*row_bits] as usize;
        }
    }
    let max_r = (max_idx / 4) as f64;
    let max_c = (max_idx % 4) as f64;

    let mut score = 0.0;
    score += weights[W_GRADIENT] * gradient_score;
    if max_idx == 0 {
        score += weights[W_CORNER_BONUS];
    } else {
        score -= (max_r + max_c) * weights[W_CORNER_DIST_PENALTY];
    }
    score += weights[W_EMPTY] * ((empty_count * empty_count) as f64);
    score -= weights[W_MONOTONICITY] * mono_penalty;
    score -= weights[W_SMOOTHNESS] * smoothness_penalty;
    score += weights[W_MERGE] * merge_score;
    score += weights[W_NEAR_2048] * near_2048_potential(board, max_exp, max_idx, empty_count);
    score
}

fn direction_bias(board: u64, direction: i32, weights: &[f64; WEIGHT_COUNT]) -> f64 {
    let mut bias = 0.0;
    if direction == DIR_LEFT {
        bias += weights[W_LEFT_BIAS];
    } else if direction == DIR_UP {
        bias += weights[W_UP_BIAS];
    } else if direction == DIR_RIGHT {
        bias -= weights[W_RIGHT_PENALTY];
    } else {
        bias -= weights[W_DOWN_PENALTY];
    }

    let (max_exp, max_idx) = max_exp_idx(board);
    if max_idx == 0 {
        let below_exp = get_cell_exp(board, 4);
        let right_exp = get_cell_exp(board, 1);
        if direction == DIR_DOWN && below_exp < max_exp {
            bias -= weights[W_CORNER_BREAK_PENALTY];
        }
        if direction == DIR_RIGHT && right_exp < max_exp {
            bias -= weights[W_CORNER_BREAK_PENALTY];
        }
    }
    bias
}

fn pack_tt_key(board: u64, ply: usize, node_type: u8) -> u128 {
    ((board as u128) << 7) | (((ply as u128) & 0x3F) << 1) | ((node_type as u128) & 0x1)
}

struct Searcher {
    weights: [f64; WEIGHT_COUNT],
    chance_branch_limit: usize,
    deadline: Option<Instant>,
    time_exceeded: bool,
    time_probe_counter: u32,
    tt: HashMap<u128, f64>,
    tt_max_entries: usize,
    player_nodes: usize,
    chance_nodes: usize,
    tt_hits_player: usize,
    tt_hits_chance: usize,
    root_depth: usize,
    max_depth_reached: usize,
}

impl Searcher {
    fn new(
        weights: [f64; WEIGHT_COUNT],
        chance_branch_limit: usize,
        deadline: Option<Instant>,
        tt_max_entries: usize,
        root_depth: usize,
    ) -> Self {
        Self {
            weights,
            chance_branch_limit: chance_branch_limit.clamp(1, 16),
            deadline,
            time_exceeded: false,
            time_probe_counter: 0,
            tt: HashMap::new(),
            tt_max_entries,
            player_nodes: 0,
            chance_nodes: 0,
            tt_hits_player: 0,
            tt_hits_chance: 0,
            root_depth,
            max_depth_reached: 0,
        }
    }

    fn maybe_trim_tt(&mut self) {
        if self.tt_max_entries == 0 || self.tt.len() <= self.tt_max_entries {
            return;
        }
        let keep_target = ((self.tt_max_entries as f64) * 0.8).max(1.0) as usize;
        let remove_n = self.tt.len().saturating_sub(keep_target);
        if remove_n == 0 {
            return;
        }
        let keys: Vec<u128> = self.tt.keys().take(remove_n).copied().collect();
        for key in keys {
            self.tt.remove(&key);
        }
    }

    fn should_stop(&mut self) -> bool {
        if self.deadline.is_none() {
            return false;
        }
        self.time_probe_counter = self.time_probe_counter.wrapping_add(1);
        if (self.time_probe_counter & 0x3F) != 0 {
            return self.time_exceeded;
        }
        if let Some(deadline) = self.deadline {
            if Instant::now() >= deadline {
                self.time_exceeded = true;
            }
        }
        self.time_exceeded
    }

    fn record_depth(&mut self, ply: usize) {
        let reached = self.root_depth.saturating_sub(ply).saturating_add(1);
        if reached > self.max_depth_reached {
            self.max_depth_reached = reached;
        }
    }

    fn player(&mut self, board: u64, ply: usize) -> f64 {
        self.player_nodes += 1;
        self.record_depth(ply);

        if self.should_stop() || ply == 0 {
            return evaluate_board(board, &self.weights);
        }

        let key = pack_tt_key(board, ply, 1);
        if let Some(v) = self.tt.get(&key) {
            self.tt_hits_player += 1;
            return *v;
        }

        let mut best_score = -1e18f64;
        let mut found_move = false;
        for &direction in &[DIR_LEFT, DIR_UP, DIR_DOWN, DIR_RIGHT] {
            let (new_board, gain, moved) = simulate_move(board, direction);
            if !moved {
                continue;
            }
            found_move = true;
            let val = (gain as f64) * self.weights[W_MOVE_SCORE_SCALE]
                + direction_bias(board, direction, &self.weights)
                + self.chance(new_board, ply.saturating_sub(1));
            if val > best_score {
                best_score = val;
            }
        }

        if !found_move {
            best_score = evaluate_board(board, &self.weights) - self.weights[W_TERMINAL_PENALTY];
        }

        self.tt.insert(key, best_score);
        best_score
    }

    fn chance(&mut self, board: u64, ply: usize) -> f64 {
        self.chance_nodes += 1;
        if self.should_stop() {
            return evaluate_board(board, &self.weights);
        }

        let key = pack_tt_key(board, ply, 0);
        if let Some(v) = self.tt.get(&key) {
            self.tt_hits_chance += 1;
            return *v;
        }

        let empty_mask = empty_mask_board(board);
        let empty_count = empty_mask.count_ones() as usize;
        if empty_count == 0 {
            let value = self.player(board, ply);
            self.tt.insert(key, value);
            return value;
        }

        let (sample_mask, sample_count) = if empty_count <= CHANCE_FULL_ENUM_EMPTY_THRESHOLD {
            (empty_mask, empty_count)
        } else {
            let count = empty_count.min(self.chance_branch_limit);
            let seed = board_sampling_seed(board, ply);
            let mask = sample_empty_mask(empty_mask, count, seed);
            if mask == 0 {
                (empty_mask, empty_count)
            } else {
                (mask, count)
            }
        };

        let mut total = 0.0f64;
        let mut m = sample_mask;
        while m != 0 {
            let lsb = m & m.wrapping_neg();
            let idx = lsb.trailing_zeros() as usize;
            let shift = idx * 4;
            let b2 = board | (1u64 << shift);
            let b4 = board | (2u64 << shift);
            total += 0.9 * self.player(b2, ply);
            total += 0.1 * self.player(b4, ply);
            m ^= lsb;
        }

        let value = total / (sample_count as f64);
        self.tt.insert(key, value);
        value
    }

    fn best_move(&mut self, board: u64, ply: usize) -> i32 {
        self.maybe_trim_tt();
        if self.should_stop() {
            return -1;
        }

        let next_ply = ply.saturating_sub(1);
        let mut best_score = -1e18f64;
        let mut best_move = -1i32;
        let mut winning_move = -1i32;
        let mut winning_exp = 0u8;
        let mut winning_gain = 0u32;

        for &direction in &[DIR_LEFT, DIR_UP, DIR_DOWN, DIR_RIGHT] {
            let (new_board, gain, moved) = simulate_move(board, direction);
            if !moved {
                continue;
            }
            let (new_max_exp, _) = max_exp_idx(new_board);
            if new_max_exp >= 11 {
                if new_max_exp > winning_exp || (new_max_exp == winning_exp && gain > winning_gain) {
                    winning_move = direction;
                    winning_exp = new_max_exp;
                    winning_gain = gain;
                }
                continue;
            }

            let score = (gain as f64) * self.weights[W_MOVE_SCORE_SCALE]
                + direction_bias(board, direction, &self.weights)
                + self.chance(new_board, next_ply);
            if score > best_score {
                best_score = score;
                best_move = direction;
            }
        }

        if winning_move != -1 {
            winning_move
        } else {
            best_move
        }
    }
}

fn coerce_weights(weights: Vec<f64>) -> PyResult<[f64; WEIGHT_COUNT]> {
    if weights.len() < WEIGHT_COUNT {
        return Err(PyValueError::new_err(format!(
            "weights must provide at least {} values",
            WEIGHT_COUNT
        )));
    }
    let mut out = [0.0f64; WEIGHT_COUNT];
    for i in 0..WEIGHT_COUNT {
        out[i] = weights[i];
    }
    Ok(out)
}

#[pyfunction]
fn best_move(
    board: u64,
    ply: usize,
    chance_branch_limit: usize,
    weights: Vec<f64>,
    time_budget_ms: f64,
    tt_max_entries: usize,
) -> PyResult<(i32, usize, usize, usize, usize, bool, usize)> {
    let weight_vec = coerce_weights(weights)?;
    let deadline = if time_budget_ms > 0.0 {
        Some(Instant::now() + Duration::from_secs_f64(time_budget_ms / 1000.0))
    } else {
        None
    };
    let root_depth = ply.max(1);
    let mut searcher = Searcher::new(
        weight_vec,
        chance_branch_limit,
        deadline,
        tt_max_entries,
        root_depth,
    );
    let mv = searcher.best_move(board, root_depth);
    Ok((
        mv,
        searcher.player_nodes,
        searcher.chance_nodes,
        searcher.tt_hits_player,
        searcher.tt_hits_chance,
        searcher.time_exceeded,
        searcher.max_depth_reached,
    ))
}

#[pymodule]
fn game2048_rust_core(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(best_move, m)?)?;
    Ok(())
}
