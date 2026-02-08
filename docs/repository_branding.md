# Repository Branding

Tento projekt má připravený branding set pro GitHub profil repozitáře.

## Generované Assety

- `docs/media/repo_hero.png` - hlavní README hero obrázek (`1600x900`)
- `docs/media/social_preview.png` - GitHub social preview (`1280x640`)
- `docs/media/clips/hub.webp` - ukázka hub navigace (`8s`, `1280x720`, `10 FPS`)
- `docs/media/clips/print_dialog.webp` - práce s tisk/PDF dialogem (`8s`, `1280x720`, `10 FPS`)
- `docs/media/clips/pdf_preview.webp` - scroll náhledem exportovaného PDF (`8s`, `1280x720`, `10 FPS`)
- `docs/media/clips/<game>.webp` - 8s klipy všech her ve středním nastavení (u lehkých her větší plocha)

WebP byl zvolen kvůli rychlému načítání README při zachování dobré vizuální kvality.

## Regenerace

```bash
.venv\Scripts\python scripts/generate_repo_branding.py --output-dir docs/media
```

Gameplay klipy:

```bash
.venv\Scripts\python scripts/generate_gameplay_clips.py --output-dir docs/media/clips --seconds 8 --fps 10 --width 1280 --height 720
```

Vstupní zdroje:

- `hub/assets/brainhub.png`
- `docs/media/home.png`
- `docs/media/sudoku.png`
- `docs/media/othello.png`
- `docs/media/kenken.png`
- `docs/media/slitherlink.png`
- `docs/media/game2048.png`

Gameplay klipy vyžadují běžící Qt GUI prostředí, proto se generují jako samostatný krok.

## Nastavení na GitHubu

1. Otevři `Settings -> General` v repozitáři.
2. V sekci `Social preview` nahraj `docs/media/social_preview.png`.
3. Ulož změnu (`Save`).

Toto je manuální krok; GitHub API to automaticky přes `git push` nenastavuje.
