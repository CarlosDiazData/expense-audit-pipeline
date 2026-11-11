PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
REGION ?= us-central1
REPOSITORY ?= expense-audit
IMAGE ?= $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(REPOSITORY)/upload:latest
TF_DIR ?= infra
TFVARS ?= terraform.tfvars
ACCESS_CODE ?=
UPLOAD_URL ?=

.PHONY: install test lint format samples build deploy tf-validate e2e clean

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

test:
	$(BIN)/pytest

lint:
	$(BIN)/ruff check src app tests scripts
	$(BIN)/ruff format --check src app tests scripts

format:
	$(BIN)/ruff check --fix src app tests scripts
	$(BIN)/ruff format src app tests scripts

samples:
	$(BIN)/python scripts/generate_samples.py

build:
	docker build -f app/upload/Dockerfile -t $(IMAGE) .
	docker push $(IMAGE)
	rm -rf build/processor
	mkdir -p build/processor
	cp -r src/expense_audit build/processor/
	cp app/processor/main.py build/processor/main.py
	cp requirements-processor.txt build/processor/requirements.txt

deploy:
	terraform -chdir=$(TF_DIR) init
	terraform -chdir=$(TF_DIR) apply -var-file=$(TFVARS) -var="upload_image=$(IMAGE)"

tf-validate:
	terraform -chdir=$(TF_DIR) init -backend=false -input=false
	terraform -chdir=$(TF_DIR) validate
	terraform -chdir=$(TF_DIR) fmt -check -recursive

e2e:
	UPLOAD_URL="$(UPLOAD_URL)" ACCESS_CODE="$(ACCESS_CODE)" scripts/e2e_demo.sh

clean:
	rm -rf build .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
