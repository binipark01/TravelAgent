.PHONY: install test lint format run dev-backend dev-frontend test-backend build-frontend

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

run:
	uvicorn travel_agent.app.main:app --reload

dev-backend:
	uvicorn travel_agent.app.main:app --reload

dev-frontend:
	cd frontend && npm run dev

test-backend:
	pytest

build-frontend:
	cd frontend && npm run build
