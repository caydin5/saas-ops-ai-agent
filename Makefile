.PHONY: setup run test freeze lint

setup:
	python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt

run:
	.venv/bin/uvicorn app.main:app --reload

test:
	.venv/bin/python -m pytest

freeze:
	.venv/bin/python -m pip freeze > requirements.lock.txt

lint:
	.venv/bin/python -m py_compile app/main.py app/schemas.py app/services/planner.py app/services/tools.py