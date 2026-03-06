PYTHON ?= py -3.13

.PHONY: install migrate seed run-api run-outbox run-processor test test-unit test-integration

install:
	$(PYTHON) -m pip install -r requirements.txt

migrate:
	$(PYTHON) -m alembic upgrade head

seed:
	$(PYTHON) -m app.scripts.seed_merchants

run-api:
	$(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-outbox:
	$(PYTHON) -m app.workers.outbox_publisher

run-processor:
	$(PYTHON) -m app.workers.processor

test: test-unit test-integration

test-unit:
	$(PYTHON) -m pytest -m "not integration" -q

test-integration:
	$(PYTHON) -m pytest -m integration -q
