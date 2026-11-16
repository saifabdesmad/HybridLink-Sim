.PHONY: help install lint typecheck test up down restart status run-scenario evaluate report clean

PYTHON ?= python
DOCKER_COMPOSE ?= docker compose

help:
	@echo "HybridLink-Sim - Commandes disponibles :"
	@echo "  make install        Installer les dependances locales"
	@echo "  make lint           Verifier le style de code (Ruff)"
	@echo "  make typecheck      Verification de types statiques (Mypy)"
	@echo "  make test           Lancer tous les tests unitaires et d'integration"
	@echo "  make up             Demarrer l'ensemble des conteneurs Docker"
	@echo "  make down           Arreter les conteneurs Docker"
	@echo "  make restart        Redemarrer les conteneurs Docker"
	@echo "  make status         Afficher l'etat des conteneurs"
	@echo "  make run-scenario SCENARIO=01_nominal   Executer un scenario specifique"
	@echo "  make evaluate       Executer les campagnes Monte Carlo (N>=30)"
	@echo "  make report         Generer les graphiques et le tableau recapitulatif"
	@echo "  make clean          Nettoyer les caches et artefacts temporaires"

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check src tests

typecheck:
	$(PYTHON) -m mypy src tests

test:
	$(PYTHON) -m pytest -v --cov=src --cov-report=term-missing tests

up:
	$(DOCKER_COMPOSE) up -d --build

down:
	$(DOCKER_COMPOSE) down -v

restart:
	$(DOCKER_COMPOSE) restart

status:
	$(DOCKER_COMPOSE) ps

run-scenario:
	$(PYTHON) -m src.netem.scenario_runner --scenario $(SCENARIO)

evaluate:
	$(PYTHON) -m src.metrics.evaluator --runs 30

report:
	$(PYTHON) -m src.metrics.plot --input data/metrics/ --output data/plots/

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +

