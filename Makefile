RUNNER_ENV_FILE ?= .development.env

.PHONY: build run lint test
ifneq (,$(wildcard $(RUNNER_ENV_FILE)))
	include $(RUNNER_ENV_FILE)
	export $(shell sed 's/=.*//' $(RUNNER_ENV_FILE))
endif


link-development-env:
	@ln -sf $(RUNNER_ENV_FILE) .env

build:
	poetry run ./scripts/build.sh

run: link-development-env
	poetry run python api.py

.PHONY: clean
clean: ## Clean the temporary files.
	rm -rf .ruff_cache
	rm -rf megalinter-reports

.PHONY: ruff
ruff: ## Run ruff linter code check.
	poetry run ruff check .

.PHONY: black
black: ## Run black linter code check.
	poetry run black --check .

lint-python:
	poetry run ./scripts/run_lint_python.sh

test-python:
	poetry run ./scripts/run_tests_python.sh

format-python:
	poetry run isort .
	poetry run black .

.PHONY: megalint megalint-apply clean-megalint
megalint:
	docker run --platform linux/amd64 --rm \
		-v $(shell pwd):/tmp/lint:rw \
		ghcr.io/oxsecurity/megalinter:v9.6.0

megalint-apply:
	docker run --platform linux/amd64 --rm \
		-v $(shell pwd):/tmp/lint:rw \
		-e APPLY_FIXES=all \
		ghcr.io/oxsecurity/megalinter:v9.6.0

clean-megalint:
	rm -rf megalinter-reports
