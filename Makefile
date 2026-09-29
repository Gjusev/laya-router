.PHONY: test test-slow backtest dataset judge analyze

test:
	python -m pytest -q

test-slow:
	python -m pytest -m slow -q

# Full reproducible backtest: dataset -> both-tier answers -> blind judge -> table.
# Requires OPENAI_API_KEY (and optionally OPENAI_BASE_URL); budget ~5-10 USD.
backtest: dataset
	python backtest/run_backtest.py
	python backtest/judge.py
	python backtest/analyze.py

dataset:
	python backtest/build_dataset.py --with-lmsys

judge:
	python backtest/judge.py

analyze:
	python backtest/analyze.py
