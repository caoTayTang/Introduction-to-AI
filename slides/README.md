# BTL1 slides (Pipes & Light Up)

Four decks, built from one `main` file per language that inputs the per-puzzle
frame files:

| Deck | Source | Output |
|---|---|---|
| Tiếng Việt | [main-vi.tex](main-vi.tex) + `pipes-vi.tex`, `lightup-vi.tex`, `results-table.tex` | `main-vi.pdf` |
| English | [main-en.tex](main-en.tex) + `pipes-en.tex`, `lightup-en.tex`, `results-table.tex` | `main-en.pdf` |

Each puzzle contributes about ten frames: rules and a real sample board, the
search formulation, shared pruning, both algorithms with pseudocode, input
generation, the demo features, the measurement protocol, measured results and
limitations. All board diagrams are hand-written TikZ vector graphics.
[Presentation notes](notes.md) expand the slide text for both puzzles.

## Build

With [Tectonic](https://tectonic-typesetting.github.io/):

```sh
tectonic slides/main-vi.tex   # or main-en.tex
```

The Vietnamese deck loads DejaVu Sans via fontspec for full Vietnamese glyphs;
the English deck keeps Beamer's default fonts. Keep `results-table.tex` next to
the sources: it contains measured medians from the published baseline
(`docs/benchmarks/2026-10-25-pipes.csv`), not an illustrative table. When
rerunning experiments, update it together with `docs/benchmarks/` and the
measurement dates on the results frames.

Build logs and temporary TeX files are ignored. Deck colors use white, dark
text and blue, matching the games' light theme.
