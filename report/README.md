# LaTeX Report

9-page final report in IEEE style.

## Structure

```
main.tex
references.bib
sections/
  00-abstract.tex
  01-introduction.tex
  02-background.tex
  03-system-design.tex
  04-experimental-setup.tex
  05-results.tex
  06-discussion.tex
  07-conclusion.tex
  99-artifact-appendix.tex     # not counted towards 9-page limit
figures/                        # report-owned diagrams (architecture, ...)
```

Generated figures from `results/figures/` are referenced via relative
paths like `../results/figures/fig1-run1-timeline.png`. The
architecture diagram is drawn inline via TikZ in `figures/architecture.tex`.

## Build

Recommended: upload this `report/` folder + the `results/figures/`
folder to [Overleaf](https://www.overleaf.com); it compiles out of
the box.

Locally (requires a full TeX Live / MacTeX install):

```bash
# With latexmk (recommended):
latexmk -pdf -interaction=nonstopmode main.tex

# Or with a manual toolchain:
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

The output is `main.pdf`.

## Page budget

- Target: 9 pages including references but **excluding** the Artifact
  Appendix.
- Penalty: 2 marks for missing an artifact appendix; 2 marks for exceeding
  the length.
- If tight, prefer shrinking Background (Sec. 2) and Related Work before
  touching Results.
