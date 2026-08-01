LATEX ?= pdflatex
BIBTEX ?= $(shell command -v bibtex.original 2>/dev/null || command -v bibtex 2>/dev/null)
PYTHON ?= python3
MAIN_PDF := XORFLOW_final_paper.pdf
SUPP_PDF := XORFLOW_supplementary_appendix.pdf

.PHONY: all main supplement figures test preflight clean
all: main supplement

main:
	$(LATEX) -interaction=nonstopmode -halt-on-error main.tex
	$(BIBTEX) main
	$(LATEX) -interaction=nonstopmode -halt-on-error main.tex
	$(LATEX) -interaction=nonstopmode -halt-on-error main.tex
	cp main.pdf $(MAIN_PDF)

supplement:
	$(LATEX) -interaction=nonstopmode -halt-on-error supplement.tex
	$(LATEX) -interaction=nonstopmode -halt-on-error supplement.tex
	cp supplement.pdf $(SUPP_PDF)

figures:
	$(PYTHON) scripts/generate_round14_figures.py
	$(PYTHON) scripts/generate_round11_frontend_figures.py

# Compact arithmetic/provenance checks. The original hardware/scheduler test
# sources are retained under results_used/review5_final2/source.
test:
	$(PYTHON) -m pytest -q tests/test_round14_results.py

preflight: all test
	@pdfinfo $(MAIN_PDF) | grep -E 'Pages|Page size'
	@pdfinfo $(SUPP_PDF) | grep -E 'Pages|Page size'
	@! grep -E 'undefined references|undefined citations|Overfull \hbox' main.log supplement.log

clean:
	rm -f main.aux main.log main.out main.bbl main.blg main.pdf
	rm -f supplement.aux supplement.log supplement.out supplement.pdf
	rm -f $(MAIN_PDF) $(SUPP_PDF)
