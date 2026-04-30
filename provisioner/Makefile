SHELL := /bin/bash

.PHONY: up down build logs ps restart frontend backend env health

env:
	@echo "Using .env:" && cat .env || true

build:
	@if [ "$(shell uname -s)" = "Linux" ]; then \
		echo "Linux detected: using docker-compose.linux.yml override"; \
		docker compose -f docker-compose.yml -f docker-compose.linux.yml build; \
	else \
		docker compose build; \
	fi

up:
	@if [ "$(shell uname -s)" = "Linux" ]; then \
		echo "Linux detected: using host networking override"; \
		docker compose -f docker-compose.yml -f docker-compose.linux.yml up -d; \
	else \
		docker compose up -d; \
	fi

down:
	@if [ "$(shell uname -s)" = "Linux" ]; then \
		docker compose -f docker-compose.yml -f docker-compose.linux.yml down; \
	else \
		docker compose down; \
	fi

logs:
	@if [ "$(shell uname -s)" = "Linux" ]; then \
		docker compose -f docker-compose.yml -f docker-compose.linux.yml logs -f --tail=200; \
	else \
		docker compose logs -f --tail=200; \
	fi

ps:
	@if [ "$(shell uname -s)" = "Linux" ]; then \
		docker compose -f docker-compose.yml -f docker-compose.linux.yml ps; \
	else \
		docker compose ps; \
	fi

restart:
	$(MAKE) down && $(MAKE) up

frontend:
	cd frontend && npm install && npm start

backend:
	pip install -r backend/requirements.txt && API_PORT=$${API_PORT:-5001} python backend/server.py

health:
	@echo "Checking frontend..." && curl -fsS http://localhost:$${FRONTEND_PORT:-3000} >/dev/null && echo OK || echo FAIL
	@echo "Checking backend..." && curl -fsS http://localhost:$${API_PORT:-5001}/api/status | jq . || true

# Raspberry Pi (Linux) targets using host networking
.PHONY: pi-build pi-up pi-down pi-logs pi-ps
pi-build:
	docker compose -f docker-compose.pi.yml build

pi-up:
	docker compose -f docker-compose.pi.yml up -d

pi-down:
	docker compose -f docker-compose.pi.yml down

pi-logs:
	docker compose -f docker-compose.pi.yml logs -f --tail=200

pi-ps:
	docker compose -f docker-compose.pi.yml ps
