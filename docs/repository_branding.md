# Repository Branding

Tento projekt ma pripraveny branding set pro GitHub profil repozitare.

## Generovane assety

- `docs/media/repo_hero.png` - hlavni README hero obrazek (`1600x900`)
- `docs/media/social_preview.png` - GitHub social preview (`1280x640`)
- `docs/media/clips/*.gif` - kratke 4s gameplay klipy pro vsechny hry (`960x540`)

## Regenerace

```bash
.venv\Scripts\python scripts/generate_repo_branding.py --output-dir docs/media
```

Gameplay klipy:

```bash
.venv\Scripts\python scripts/generate_gameplay_clips.py --output-dir docs/media/clips --seconds 4 --fps 8
```

Vstupni zdroje:

- `hub/assets/brainhub.png`
- `docs/media/home.png`
- `docs/media/sudoku.png`
- `docs/media/othello.png`
- `docs/media/kenken.png`
- `docs/media/slitherlink.png`
- `docs/media/game2048.png`

Gameplay klipy vyzaduji bezici Qt GUI prostredi, proto se generuji jako samostatny krok.

## Nastaveni na GitHubu

1. Otevri `Settings -> General` v repozitari.
2. V sekci `Social preview` nahraj `docs/media/social_preview.png`.
3. Uloz zmenu (`Save`).

Toto je manualni krok; GitHub API to automaticky pres git push nenastavuje.
