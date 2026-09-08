# Biblia
#
# Everything runs inside a project-local virtualenv at .venv, which keeps the
# install off the system Python. That matters on two common setups: macOS and
# many Linux distros ship only `python3` with no `python` on PATH, and modern
# Debian/Ubuntu refuse a bare `pip install` outright with
# "externally-managed-environment".

PY      ?= $(shell command -v python3 2>/dev/null || command -v python)
VENV    := .venv
VPY     := $(VENV)/bin/python
VPIP    := $(VENV)/bin/pip

# Windows layout (Git Bash / MSYS) puts executables in Scripts/, not bin/.
ifeq ($(OS),Windows_NT)
  VPY  := $(VENV)/Scripts/python.exe
  VPIP := $(VENV)/Scripts/pip.exe
endif

.PHONY: help all setup sources build serve dev test clean distclean

help:
	@echo "make all      setup + sources + build   (first run, ~3 minutes)"
	@echo "make serve    run the app on http://localhost:8000"
	@echo ""
	@echo "make setup    create .venv and install backend + frontend deps"
	@echo "make sources  download the open-license Bible texts (~360MB)"
	@echo "make build    build the corpus database and the frontend"
	@echo "make dev      API and Vite dev servers with hot reload"
	@echo "make test     run the verification suite"
	@echo "make clean    remove the database and frontend build"

all: setup sources build
	@echo ""
	@echo "Ready. Run 'make serve' and open http://localhost:8000"

$(VPY):
	@test -n "$(PY)" || { echo "No python3 found on PATH. Install Python 3.10+."; exit 1; }
	$(PY) -m venv $(VENV)
	$(VPIP) install --upgrade pip --quiet

setup: $(VPY)
	$(VPIP) install -r backend/requirements.txt
	cd frontend && npm install

sources:
	./scripts/fetch_sources.sh

build:
	cd backend && ../$(VPY) -m app.ingest.run --source-dir ../sources
	cd frontend && npm run build

serve:
	cd backend && ../$(VPY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000

dev:
	cd backend && ../$(VPY) -m uvicorn app.main:app --reload --port 8000 & \
	cd frontend && npm run dev

test:
	cd backend && ../$(VPY) -m pytest -q

clean:
	rm -f backend/data/bible.db backend/data/bible.db-wal backend/data/bible.db-shm
	rm -rf frontend/dist

distclean: clean
	rm -rf $(VENV) frontend/node_modules sources
