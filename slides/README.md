# Pipes search presentation

[Open the 12-slide PDF](pipes-search.pdf).

This is the Pipes portion of the Introduction to AI project. It covers the goal,
formal search model, viable actions, search space, pruning, DFS and Greedy
pseudocode, evaluation and limitations. It does not present the unfinished
second puzzle.

The editable source is [pipes-search.tex](pipes-search.tex), using LaTeX Beamer
and TikZ. All board diagrams, trees and flow diagrams are vector graphics defined
in the source. [Presentation notes](notes.md) expand the short slide text.

## Build

With [Tectonic](https://tectonic-typesetting.github.io/):

```sh
tectonic slides/pipes-search.tex --outdir slides
```

Or with an installed TeX distribution:

```sh
cd slides
pdflatex -halt-on-error pipes-search.tex
pdflatex -halt-on-error pipes-search.tex
```

Keep `results-table.tex` next to the source. It contains measured values from
the published baseline, not an illustrative table. When rerunning experiments,
update it together with `docs/benchmarks/` and the measurement date on slide 11.

The PDF is committed so teammates can present without installing LaTeX. Build
logs and temporary TeX files are ignored. Deck colors use white, dark text and
blue, matching the game's light theme.
