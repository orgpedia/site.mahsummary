name := site.mahsummary/flow/genSite_

.DEFAULT_GOAL := genSite
.PHONY: genSite_all genSite

genSite_all:
	uv run python src/gen_summary.py input output all 'mr,en'

genSite:
	uv run python src/gen_summary.py input output last 'mr,en'

