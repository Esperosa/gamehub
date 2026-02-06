# TODO – Piškvorky (budoucí vylepšení)

Tohle je první funkční verze podle požadavků (N=3/4/5, bot 3 obtížnosti, random kdo začíná, Elo score + win chance).

Pokud budeš chtít, další iterace můžou přidat:

## UI/UX
- Lepší animace kamenů (bounce, trail), particle konfety při výhře
- Nastavitelný skin (barvy X/O, tloušťka, zvuky)
- Přepínač: "Random start" vs "Vždy hráč" vs "Vždy bot"
- Tlačítko "Reset stats" přímo v UI

## AI
- Lepší ordering tahů + transposition hashing (Zobrist) pro rychlejší hard na 5×5
- Iterative deepening s pevnou časovou kvótou na tah + ukazatel "thinking"
- Opening book pro 3×3 (aby hard hrál perfektně vždy)

## Data
- Oddělené profily hráčů
- Export historie zápasů do CSV
