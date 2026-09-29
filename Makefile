.PHONY: test test-slow backtest backtest-glm dataset judge analyze

test:
	python -m pytest -q

test-slow:
	python -m pytest -m slow -q

# Full reproducible backtest: dataset -> both-tier answers -> blind judge -> table.
# Requires OPENAI_API_KEY (and optionally OPENAI_BASE_URL); budget ~5-10 USD on OpenAI.
backtest: dataset
	python backtest/run_backtest.py
	python backtest/judge.py
	python backtest/analyze.py

# Same pipeline on Z.ai (GLM): glm-4.5-flash is free, so the run only pays
# for frontier answers and judge calls. Needs OPENAI_API_KEY set to a Z.ai key.
backtest-glm: dataset
	OPENAI_BASE_URL=https://api.z.ai/api/paas/v4 \
	python backtest/run_backtest.py --tiers backtest/tiers.glm.yaml
	OPENAI_BASE_URL=https://api.z.ai/api/paas/v4 \
	python backtest/judge.py --tiers backtest/tiers.glm.yaml
	python backtest/analyze.py

dataset:
	python backtest/build_dataset.py --with-lmsys

judge:
	python backtest/judge.py

analyze:
	python backtest/analyze.py
