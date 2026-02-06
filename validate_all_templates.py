"""
KenKen Template Validator
Checks that all templates conform to difficulty rules:

OPERATIONS:
- Easy: only + and * (no - or /)
- Medium: +, *, - (no /)
- Hard: +, *, -, / (all operations)

SINGLES (hints) targets:
- Easy 4-7: ~45-50%
- Easy 8-9: max 25%
- Medium: max 15-25%
- Hard: max 10%

CAGE SIZES:
- Easy: max 2-3 cells
- Medium: max 3-4 cells
- Hard: max 5 cells
"""

import json
import os
from collections import Counter
from dataclasses import dataclass
from typing import List, Dict, Tuple

TEMPLATES_DIR = 'games/kenken/templates'

@dataclass
class ValidationResult:
    file: str
    total: int
    valid: int
    issues: List[str]

def validate_template(template: dict, size: int, difficulty: str) -> Tuple[bool, List[str]]:
    """Validate a single template against difficulty rules."""
    issues = []
    cages = template['cages']
    
    # Count singles
    singles = sum(1 for c in cages if len(c['cells']) == 1)
    total_cages = len(cages)
    singles_pct = singles * 100 / total_cages if total_cages > 0 else 0
    
    # Get operations used
    ops = set(c['operation'] for c in cages if c['operation'] != '')
    
    # Get max cage size
    max_cage = max(len(c['cells']) for c in cages)
    
    # Check operations by difficulty
    if difficulty == 'easy':
        forbidden_ops = ops & {'-', '/'}
        if forbidden_ops:
            issues.append(f"Easy has forbidden ops: {forbidden_ops}")
    elif difficulty == 'medium':
        forbidden_ops = ops & {'/'}
        if forbidden_ops:
            issues.append(f"Medium has forbidden ops: {forbidden_ops}")
    # Hard allows all ops
    
    # Check singles percentage
    if size >= 8:
        if difficulty == 'easy' and singles_pct > 30:
            issues.append(f"8-9 Easy singles too high: {singles_pct:.0f}% (max 25%)")
        elif difficulty == 'medium' and singles_pct > 20:
            issues.append(f"8-9 Medium singles too high: {singles_pct:.0f}% (max 15%)")
        elif difficulty == 'hard' and singles_pct > 15:
            issues.append(f"8-9 Hard singles too high: {singles_pct:.0f}% (max 10%)")
    else:
        if difficulty == 'easy' and singles_pct < 30:
            issues.append(f"Easy singles too low: {singles_pct:.0f}% (should be ~45-50%)")
        elif difficulty == 'hard' and singles_pct > 20:
            issues.append(f"Hard singles too high: {singles_pct:.0f}% (max ~10%)")
    
    # Check max cage size
    expected_max = {'easy': 3, 'medium': 4, 'hard': 5}[difficulty]
    if max_cage > expected_max:
        issues.append(f"{difficulty} has cage size {max_cage} (max {expected_max})")
    
    return len(issues) == 0, issues

def analyze_file(filepath: str) -> ValidationResult:
    """Analyze a single template file."""
    filename = os.path.basename(filepath)
    parts = filename.replace('.json', '').split('_')
    size = int(parts[0])
    difficulty = parts[1]
    
    with open(filepath, 'r', encoding='utf-8') as f:
        templates = json.load(f)
    
    valid_count = 0
    all_issues = []
    
    for i, t in enumerate(templates):
        is_valid, issues = validate_template(t, size, difficulty)
        if is_valid:
            valid_count += 1
        else:
            for issue in issues[:3]:  # Limit issues per template
                all_issues.append(f"  Template {i}: {issue}")
    
    return ValidationResult(
        file=filename,
        total=len(templates),
        valid=valid_count,
        issues=all_issues[:10]  # Limit total issues shown
    )

def get_stats(filepath: str) -> dict:
    """Get detailed stats for a template file."""
    filename = os.path.basename(filepath)
    parts = filename.replace('.json', '').split('_')
    size = int(parts[0])
    difficulty = parts[1]
    
    with open(filepath, 'r', encoding='utf-8') as f:
        templates = json.load(f)
    
    singles_pcts = []
    ops_counter = Counter()
    cage_sizes = Counter()
    
    for t in templates:
        cages = t['cages']
        singles = sum(1 for c in cages if len(c['cells']) == 1)
        total = len(cages)
        singles_pcts.append(singles * 100 / total)
        
        for c in cages:
            if c['operation']:
                ops_counter[c['operation']] += 1
            cage_sizes[len(c['cells'])] += 1
    
    return {
        'file': filename,
        'size': size,
        'difficulty': difficulty,
        'count': len(templates),
        'singles_min': min(singles_pcts),
        'singles_max': max(singles_pcts),
        'singles_avg': sum(singles_pcts) / len(singles_pcts),
        'ops': dict(ops_counter),
        'cage_sizes': dict(cage_sizes),
    }

def main():
    print("=" * 70)
    print("  KENKEN TEMPLATE VALIDATION REPORT")
    print("=" * 70)
    print()
    
    # Expected rules
    print("EXPECTED RULES:")
    print("  Operations:  Easy=+,*  |  Medium=+,*,-  |  Hard=+,*,-,/")
    print("  Max cage:    Easy=3    |  Medium=4      |  Hard=5")
    print("  Singles:     Easy=45-50% (8-9: 25%)  |  Medium=25% (8-9: 15%)  |  Hard=10%")
    print()
    print("-" * 70)
    print()
    
    files = sorted([f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.json')])
    
    all_valid = True
    
    for f in files:
        filepath = os.path.join(TEMPLATES_DIR, f)
        stats = get_stats(filepath)
        result = analyze_file(filepath)
        
        # Determine status
        if result.valid == result.total:
            status = "✓ OK"
        else:
            status = f"⚠ {result.valid}/{result.total}"
            all_valid = False
        
        # Format operations
        ops_str = ', '.join(sorted(k for k in stats['ops'].keys() if k))
        
        # Format cage sizes
        sizes_str = ', '.join(f"{k}:{v}" for k, v in sorted(stats['cage_sizes'].items()))
        
        print(f"{f}:")
        print(f"  Count: {stats['count']}")
        print(f"  Singles: min={stats['singles_min']:.0f}%, max={stats['singles_max']:.0f}%, avg={stats['singles_avg']:.0f}%")
        print(f"  Operations: {ops_str}")
        print(f"  Cage sizes: {sizes_str}")
        print(f"  Status: {status}")
        
        if result.issues:
            print(f"  Issues:")
            for issue in result.issues[:5]:
                print(f"    {issue}")
        
        print()
    
    print("-" * 70)
    if all_valid:
        print("✓ ALL TEMPLATES VALID!")
    else:
        print("⚠ SOME TEMPLATES HAVE ISSUES - see above")
    print()

if __name__ == "__main__":
    main()
