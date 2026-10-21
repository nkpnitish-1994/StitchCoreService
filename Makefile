.PHONY: bootstrap up down migrate makemigrations test lint typecheck openapi run cdk-synth

bootstrap:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

up:
	docker compose up -d db localstack

down:
	docker compose down

migrate:
	.venv/bin/python manage.py migrate

makemigrations:
	.venv/bin/python manage.py makemigrations

test:
	.venv/bin/python manage.py test

lint:
	.venv/bin/python -m compileall config operations infra/lambda

typecheck:
	@echo "Add mypy/pyright after domain package split."

openapi:
	.venv/bin/python manage.py spectacular --file packages/contracts/openapi.yaml --validate --fail-on-warn

run:
	.venv/bin/python manage.py runserver

cdk-synth:
	cd infra/cdk && npm ci && npx cdk synth -c env=beta
