//! Slitherlink Puzzle Generator
//!
//! Generates puzzles by:
//! 1. Creating a random valid loop
//! 2. Computing clues from the loop
//! 3. Removing clues while maintaining unique solution
//! 4. Outputting as JSON

use rand::prelude::*;
use serde::Serialize;
use std::collections::{HashSet, HashMap};
use std::fs;
use std::path::Path;

/// Puzzle output format
#[derive(Serialize)]
struct Puzzle {
    width: usize,
    height: usize,
    clues: Vec<Vec<Option<u8>>>,
    difficulty: String,
    solution_h: Vec<Vec<bool>>,
    solution_v: Vec<Vec<bool>>,
}

/// Edge type for internal representation
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
enum Edge {
    H(usize, usize), // Horizontal: row, col
    V(usize, usize), // Vertical: row, col
}

/// Solver state
#[derive(Clone)]
struct SolverState {
    width: usize,
    height: usize,
    h_edges: Vec<Vec<i8>>, // 0=unknown, 1=line, -1=no line
    v_edges: Vec<Vec<i8>>,
    clues: Vec<Vec<Option<u8>>>,
}

impl SolverState {
    fn new(width: usize, height: usize, clues: Vec<Vec<Option<u8>>>) -> Self {
        Self {
            width,
            height,
            h_edges: vec![vec![0; width]; height + 1],
            v_edges: vec![vec![0; width + 1]; height],
            clues,
        }
    }

    fn set_edge(&mut self, edge: Edge, value: i8) {
        match edge {
            Edge::H(r, c) => self.h_edges[r][c] = value,
            Edge::V(r, c) => self.v_edges[r][c] = value,
        }
    }

    fn get_edge(&self, edge: Edge) -> i8 {
        match edge {
            Edge::H(r, c) => self.h_edges[r][c],
            Edge::V(r, c) => self.v_edges[r][c],
        }
    }

    /// Get edges around a cell
    fn edges_around_cell(&self, r: usize, c: usize) -> [Edge; 4] {
        [
            Edge::H(r, c),     // top
            Edge::V(r, c + 1), // right
            Edge::H(r + 1, c), // bottom
            Edge::V(r, c),     // left
        ]
    }

    /// Count lines around a cell
    fn count_lines_around(&self, r: usize, c: usize) -> usize {
        self.edges_around_cell(r, c)
            .iter()
            .filter(|&&e| self.get_edge(e) == 1)
            .count()
    }

    /// Count unknowns around a cell
    fn count_unknowns_around(&self, r: usize, c: usize) -> usize {
        self.edges_around_cell(r, c)
            .iter()
            .filter(|&&e| self.get_edge(e) == 0)
            .count()
    }

    /// Get edges at a vertex
    fn edges_at_vertex(&self, vr: usize, vc: usize) -> Vec<Edge> {
        let mut edges = Vec::with_capacity(4);
        
        // Left horizontal
        if vc > 0 && vr <= self.height {
            edges.push(Edge::H(vr, vc - 1));
        }
        // Right horizontal
        if vc < self.width && vr <= self.height {
            edges.push(Edge::H(vr, vc));
        }
        // Top vertical
        if vr > 0 && vc <= self.width {
            edges.push(Edge::V(vr - 1, vc));
        }
        // Bottom vertical
        if vr < self.height && vc <= self.width {
            edges.push(Edge::V(vr, vc));
        }
        
        edges
    }

    /// Apply constraint propagation
    fn propagate(&mut self) -> Result<bool, ()> {
        let mut changed = true;
        let mut any_change = false;

        while changed {
            changed = false;

            // Cell constraints
            for r in 0..self.height {
                for c in 0..self.width {
                    if let Some(clue) = self.clues[r][c] {
                        let lines = self.count_lines_around(r, c);
                        let unknowns = self.count_unknowns_around(r, c);
                        let clue = clue as usize;

                        // Too many lines
                        if lines > clue {
                            return Err(());
                        }

                        // Can't reach clue
                        if lines + unknowns < clue {
                            return Err(());
                        }

                        // If satisfied, mark remaining as X
                        if lines == clue && unknowns > 0 {
                            for edge in self.edges_around_cell(r, c) {
                                if self.get_edge(edge) == 0 {
                                    self.set_edge(edge, -1);
                                    changed = true;
                                }
                            }
                        }

                        // If we need all remaining edges
                        if lines + unknowns == clue && unknowns > 0 {
                            for edge in self.edges_around_cell(r, c) {
                                if self.get_edge(edge) == 0 {
                                    self.set_edge(edge, 1);
                                    changed = true;
                                }
                            }
                        }
                    }
                }
            }

            // Vertex constraints (degree 0 or 2)
            for vr in 0..=self.height {
                for vc in 0..=self.width {
                    let edges = self.edges_at_vertex(vr, vc);
                    let lines: usize = edges.iter().filter(|&&e| self.get_edge(e) == 1).count();
                    let unknowns: usize = edges.iter().filter(|&&e| self.get_edge(e) == 0).count();

                    // Too many lines
                    if lines > 2 {
                        return Err(());
                    }

                    // Degree 2 reached, mark remaining as X
                    if lines == 2 && unknowns > 0 {
                        for edge in edges.iter() {
                            if self.get_edge(*edge) == 0 {
                                self.set_edge(*edge, -1);
                                changed = true;
                            }
                        }
                    }

                    // Degree 1 with only 1 unknown: must connect
                    if lines == 1 && unknowns == 1 {
                        for edge in edges.iter() {
                            if self.get_edge(*edge) == 0 {
                                self.set_edge(*edge, 1);
                                changed = true;
                            }
                        }
                    }

                    // Degree 1 with 0 unknowns: dead end (invalid)
                    if lines == 1 && unknowns == 0 {
                        return Err(());
                    }
                }
            }

            if changed {
                any_change = true;
            }
        }

        Ok(any_change)
    }

    /// Check if solved
    fn is_solved(&self) -> bool {
        // All edges determined
        for row in &self.h_edges {
            if row.iter().any(|&e| e == 0) {
                return false;
            }
        }
        for row in &self.v_edges {
            if row.iter().any(|&e| e == 0) {
                return false;
            }
        }
        
        // Check clues
        for r in 0..self.height {
            for c in 0..self.width {
                if let Some(clue) = self.clues[r][c] {
                    if self.count_lines_around(r, c) != clue as usize {
                        return false;
                    }
                }
            }
        }
        
        // Check single loop
        self.is_single_loop()
    }

    /// Check if lines form a single closed loop
    fn is_single_loop(&self) -> bool {
        // Collect all line edges
        let mut edges: HashSet<((usize, usize), (usize, usize))> = HashSet::new();
        
        for r in 0..=self.height {
            for c in 0..self.width {
                if self.h_edges[r][c] == 1 {
                    edges.insert(((r, c), (r, c + 1)));
                }
            }
        }
        for r in 0..self.height {
            for c in 0..=self.width {
                if self.v_edges[r][c] == 1 {
                    edges.insert(((r, c), (r + 1, c)));
                }
            }
        }

        if edges.is_empty() {
            return false;
        }

        // Build adjacency
        let mut adj: HashMap<(usize, usize), Vec<(usize, usize)>> = HashMap::new();
        for &(v1, v2) in &edges {
            adj.entry(v1).or_default().push(v2);
            adj.entry(v2).or_default().push(v1);
        }

        // All vertices must have degree 2
        for (_, neighbors) in &adj {
            if neighbors.len() != 2 {
                return false;
            }
        }

        // Single component
        let start = *adj.keys().next().unwrap();
        let mut visited = HashSet::new();
        let mut stack = vec![start];
        while let Some(v) = stack.pop() {
            if visited.contains(&v) {
                continue;
            }
            visited.insert(v);
            for &neighbor in adj.get(&v).unwrap_or(&vec![]) {
                if !visited.contains(&neighbor) {
                    stack.push(neighbor);
                }
            }
        }

        visited.len() == adj.len()
    }

    /// Count solutions (returns 0, 1, or 2 for "more than 1")
    fn count_solutions(&self, limit: usize) -> usize {
        let mut state = self.clone();
        
        // Propagate first
        if state.propagate().is_err() {
            return 0;
        }

        if state.is_solved() {
            return 1;
        }

        // Find first unknown edge
        let unknown_edge = 'find: {
            for r in 0..=self.height {
                for c in 0..self.width {
                    if state.h_edges[r][c] == 0 {
                        break 'find Some(Edge::H(r, c));
                    }
                }
            }
            for r in 0..self.height {
                for c in 0..=self.width {
                    if state.v_edges[r][c] == 0 {
                        break 'find Some(Edge::V(r, c));
                    }
                }
            }
            None
        };

        let Some(edge) = unknown_edge else {
            // No unknowns but not solved = invalid
            return 0;
        };

        let mut total = 0;

        // Try edge = 1
        let mut try_line = state.clone();
        try_line.set_edge(edge, 1);
        total += try_line.count_solutions(limit - total.min(limit));
        if total >= limit {
            return total;
        }

        // Try edge = -1
        let mut try_no = state.clone();
        try_no.set_edge(edge, -1);
        total += try_no.count_solutions(limit - total.min(limit));

        total.min(limit)
    }
}

/// Generate a random closed loop using random walk
fn generate_loop(width: usize, height: usize, rng: &mut impl Rng) -> Option<(Vec<Vec<bool>>, Vec<Vec<bool>>)> {
    let mut h_edges = vec![vec![false; width]; height + 1];
    let mut v_edges = vec![vec![false; width + 1]; height];

    // Start with a simple rectangular loop
    let margin_r = (height / 4).max(1).min(height / 2);
    let margin_c = (width / 4).max(1).min(width / 2);
    
    let start_r = rng.gen_range(0..margin_r.max(1));
    let end_r = rng.gen_range((height - margin_r).max(start_r + 2)..=height);
    let start_c = rng.gen_range(0..margin_c.max(1));
    let end_c = rng.gen_range((width - margin_c).max(start_c + 2)..=width);

    // Top and bottom horizontal edges
    for c in start_c..end_c {
        h_edges[start_r][c] = true;
        h_edges[end_r][c] = true;
    }
    // Left and right vertical edges  
    for r in start_r..end_r {
        v_edges[r][start_c] = true;
        v_edges[r][end_c] = true;
    }

    // Apply random modifications
    let iterations = (width * height) as usize;
    for _ in 0..iterations {
        if !try_modify_loop(&mut h_edges, &mut v_edges, width, height, rng) {
            continue;
        }
    }

    if is_valid_loop(&h_edges, &v_edges, width, height) {
        Some((h_edges, v_edges))
    } else {
        None
    }
}

/// Try to modify the loop by bumping it
fn try_modify_loop(
    h_edges: &mut Vec<Vec<bool>>,
    v_edges: &mut Vec<Vec<bool>>,
    width: usize,
    height: usize,
    rng: &mut impl Rng,
) -> bool {
    // Pick a random cell
    let r = rng.gen_range(0..height);
    let c = rng.gen_range(0..width);

    // Get current edges around this cell
    let top = h_edges[r][c];
    let bottom = h_edges[r + 1][c];
    let left = v_edges[r][c];
    let right = v_edges[r][c + 1];

    // Try different modifications based on current state
    let edges_count = [top, bottom, left, right].iter().filter(|&&x| x).count();

    if edges_count == 0 {
        // No edges - try to add a bump if neighbors allow
        // Check if we can connect to the loop
        return false; // Skip for simplicity
    }

    if edges_count == 2 {
        // Two edges - this is a corner or straight through
        // Try to flip it
        if (top && bottom) || (left && right) {
            // Straight through - try to bump out
            if top && bottom && c + 1 < width {
                // Bump right
                if !v_edges[r][c + 1] {
                    h_edges[r][c] = false;
                    h_edges[r + 1][c] = false;
                    h_edges[r][c + 1] = true;
                    h_edges[r + 1][c + 1] = true;
                    v_edges[r][c + 1] = true;
                    
                    if is_valid_loop(h_edges, v_edges, width, height) {
                        return true;
                    }
                    
                    // Revert
                    h_edges[r][c] = true;
                    h_edges[r + 1][c] = true;
                    h_edges[r][c + 1] = false;
                    h_edges[r + 1][c + 1] = false;
                    v_edges[r][c + 1] = false;
                }
            }
        }
    }

    false
}

/// Check if edges form a valid single closed loop
fn is_valid_loop(h_edges: &[Vec<bool>], v_edges: &[Vec<bool>], width: usize, height: usize) -> bool {
    // Check all vertices have degree 0 or 2
    for vr in 0..=height {
        for vc in 0..=width {
            let mut degree = 0;
            if vc > 0 && h_edges[vr][vc - 1] { degree += 1; }
            if vc < width && h_edges[vr][vc] { degree += 1; }
            if vr > 0 && v_edges[vr - 1][vc] { degree += 1; }
            if vr < height && v_edges[vr][vc] { degree += 1; }
            
            if degree != 0 && degree != 2 {
                return false;
            }
        }
    }

    // Check single component
    let mut edges: HashSet<((usize, usize), (usize, usize))> = HashSet::new();
    for r in 0..=height {
        for c in 0..width {
            if h_edges[r][c] {
                edges.insert(((r, c), (r, c + 1)));
            }
        }
    }
    for r in 0..height {
        for c in 0..=width {
            if v_edges[r][c] {
                edges.insert(((r, c), (r + 1, c)));
            }
        }
    }

    if edges.is_empty() {
        return false;
    }

    let mut adj: HashMap<(usize, usize), Vec<(usize, usize)>> = HashMap::new();
    for &(v1, v2) in &edges {
        adj.entry(v1).or_default().push(v2);
        adj.entry(v2).or_default().push(v1);
    }

    let start = *adj.keys().next().unwrap();
    let mut visited = HashSet::new();
    let mut stack = vec![start];
    while let Some(v) = stack.pop() {
        if visited.contains(&v) {
            continue;
        }
        visited.insert(v);
        for &neighbor in adj.get(&v).unwrap_or(&vec![]) {
            if !visited.contains(&neighbor) {
                stack.push(neighbor);
            }
        }
    }

    visited.len() == adj.len()
}

/// Compute clues from a loop
fn compute_clues(h_edges: &[Vec<bool>], v_edges: &[Vec<bool>], width: usize, height: usize) -> Vec<Vec<u8>> {
    let mut clues = vec![vec![0u8; width]; height];
    
    for r in 0..height {
        for c in 0..width {
            let mut count = 0u8;
            if h_edges[r][c] { count += 1; }
            if h_edges[r + 1][c] { count += 1; }
            if v_edges[r][c] { count += 1; }
            if v_edges[r][c + 1] { count += 1; }
            clues[r][c] = count;
        }
    }
    
    clues
}

/// Generate a puzzle with given parameters
fn generate_puzzle(width: usize, height: usize, difficulty: &str, rng: &mut impl Rng) -> Option<Puzzle> {
    // Generate loop
    let (solution_h, solution_v) = generate_loop(width, height, rng)?;

    // Compute all clues
    let all_clues = compute_clues(&solution_h, &solution_v, width, height);
    
    // Determine how many clues to keep based on difficulty
    let total_cells = width * height;
    let (min_pct, max_pct) = match difficulty {
        "easy" => (0.55, 0.75),
        "medium" => (0.35, 0.55),
        "hard" => (0.20, 0.35),
        _ => (0.35, 0.55),
    };

    let target_clues = (total_cells as f64 * rng.gen_range(min_pct..max_pct)) as usize;
    
    // Start with all clues
    let mut clues: Vec<Vec<Option<u8>>> = all_clues
        .iter()
        .map(|row| row.iter().map(|&c| Some(c)).collect())
        .collect();

    // Shuffle cell order for removal
    let mut cells: Vec<(usize, usize)> = (0..height)
        .flat_map(|r| (0..width).map(move |c| (r, c)))
        .collect();
    cells.shuffle(rng);

    // Try removing clues while keeping unique solution
    let mut current_clues = total_cells;
    for (r, c) in cells {
        if current_clues <= target_clues {
            break;
        }

        let old_clue = clues[r][c];
        clues[r][c] = None;

        // Check if still uniquely solvable
        let state = SolverState::new(width, height, clues.clone());
        let solutions = state.count_solutions(2);

        if solutions != 1 {
            clues[r][c] = old_clue;
        } else {
            current_clues -= 1;
        }
    }

    Some(Puzzle {
        width,
        height,
        clues,
        difficulty: difficulty.to_string(),
        solution_h,
        solution_v,
    })
}

fn main() {
    let output_dir = Path::new("..").join("templates");
    fs::create_dir_all(&output_dir).expect("Failed to create output directory");

    let mut rng = rand::thread_rng();

    // Generate puzzles of various sizes and difficulties
    let configs = [
        (5, 5, "easy", 5),
        (5, 5, "medium", 5),
        (7, 7, "easy", 5),
        (7, 7, "medium", 5),
        (7, 7, "hard", 3),
        (10, 10, "easy", 5),
        (10, 10, "medium", 5),
        (10, 10, "hard", 3),
        (15, 15, "easy", 3),
        (15, 15, "medium", 3),
    ];

    let mut total = 0;
    for (width, height, difficulty, count) in configs {
        print!("Generating {}x{} {}... ", width, height, difficulty);
        std::io::Write::flush(&mut std::io::stdout()).ok();

        let mut generated = 0;
        let mut attempts = 0;
        let max_attempts = count * 100;

        while generated < count && attempts < max_attempts {
            attempts += 1;

            if let Some(puzzle) = generate_puzzle(width, height, difficulty, &mut rng) {
                let filename = format!("{}x{}_{:03}_{}.json", 
                    width, height, generated + 1, difficulty
                );
                let path = output_dir.join(&filename);

                let json = serde_json::to_string_pretty(&puzzle).unwrap();
                fs::write(&path, json).expect("Failed to write puzzle");

                generated += 1;
                total += 1;
            }
        }

        println!("{}/{} in {} attempts", generated, count, attempts);
    }

    println!("\nTotal: {} puzzles generated", total);
}
