SHELL := /bin/bash
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff

.PHONY: setup dev backend frontend build run test lint clean

setup: $(VENV)/bin/activate

$(VENV)/bin/activate:
	python3.11 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e "./backend[dev]"
	cd frontend && npm install

## Backend (reload) + Vite dev server
dev:
	@trap 'kill 0' EXIT; \
	$(UVICORN) app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000 & \
	cd frontend && npm run dev

## Build frontend then serve everything from FastAPI
run: build
	$(UVICORN) app.main:app --app-dir backend --host 127.0.0.1 --port 8000

backend:
	$(UVICORN) app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

test:
	cd backend && ../$(PYTEST)

lint:
	$(RUFF) check backend

clean:
	rm -rf frontend/dist
