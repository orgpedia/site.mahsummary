name := site.mahsummary/flow/genSite_

.DEFAULT_GOAL := genSite
.PHONY: genSite_all genSite

genSite_all:
	poetry run python src/gen_summary.py input output all 'mr,en'

genSite:
	poetry run python src/gen_summary.py input output last 'mr,en'

