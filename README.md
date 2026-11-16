# HybridLink-Sim : Simulation & Évaluation d'une Architecture Hybride et Résiliente pour Drone

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker Compose](https://img.shields.io/badge/docker-compose-v2-green.svg)](https://docs.docker.com/compose/)
[![Security MAVLink 2](https://img.shields.io/badge/security-MAVLink_2_Signed-orange.svg)](docs/mavlink_security.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Projet de recherche & développement préparé pour une candidature en stage de recherche au **Laboratoire Heudiasyc (UMR CNRS 7253 / UTC)**.

---

## 🎯 Problématique & Objectifs

Pour un drone évoluant hors vue directe (**BVLOS**), la liaison de commande et contrôle (**C2**) est vitale. Aucune technologie radio unique ne répond parfaitement à tous les défis opérationnels :
- **Lien A (Radio C2 - type ExpressLRS / LoRa)** : Latence ultra-faible (<10 ms), résilient aux brouillages légers, mais débit très restreint (~50 kbps).
- **Lien B (Cellulaire - 4G/5G)** : Débit élevé (>5 Mbps), portée nationale, mais latence variable (30-150 ms), gigue et pertes fréquentes lors des *handovers*.

**HybridLink-Sim** simule, sécurise et évalue une architecture multi-liens intelligente capable de :
1. **Router dynamiquement** les trames MAVLink 2 entre les liens A et B avec une machine à états à **hystérésis** (évitant le phénomène destructeur de *flapping*).
2. **Sécuriser les échanges** de bout en bout via la **signature cryptographique MAVLink 2 (HMAC-SHA256)** et une fenêtre anti-rejeu stricte face aux attaques (rejeu, usurpation, altération, DoS).
3. **Garantir la sûreté** du vecteur aérien par le déclenchement déterministe d'un **failsafe** (Hold / Return-to-Launch) dès la perte totale des liens.
4. **Fournir une évaluation scientifique** basée sur des campagnes **Monte Carlo ($N \ge 30$)**, export de métriques (p50/p95/p99) et graphiques publiables.

---

## 🏗️ Architecture Globale

Le banc est orchestré sous **Docker Compose**, séparant distinctement chaque responsabilité en conteneurs isolés :

```
      +--------------------+
      |  GCS (Station Sol) |
      +---------+----------+
                |
                v
      +--------------------+
      |    LINK-MANAGER    |  <-- Machine à états (FSM), Hystérésis & Métriques
      +----+----------+----+
           |          |
    Lien A |          | Lien B
 (ExpressLRS)         | (4G/5G)
           v          v
      +--------------------+
      |       NETEM        |  <-- Émulation noyau Linux (tc netem, latence, pertes)
      +----+----------+----+
           |          |
           +----+-----+
                |  <--------- ATTACKER (Injection, Rejeu, Altération, Flood DoS)
                v
      +--------------------+
      |   VEHICLE (UAV)    |  <-- MAVLink 2, Failsafe déterministe (RTL)
      +--------------------+
                |
                v
      +--------------------+
      |      METRICS       |  <-- Collecte CSV, Intervalles de confiance 95%, Plots
      +--------------------+
```

---

## 📁 Arborescence du Projet

```text
HybridLink-Sim/
├── .github/workflows/ci.yml       # Intégration continue (Ruff, Mypy, Pytest)
├── docker/                        # Dockerfiles spécialisés pour chaque conteneur
├── docs/                          # Documentation technique et préparation d'entretien
│   ├── architecture.md            # Détail des flux et ports/adapters
│   ├── mavlink_security.md        # Spécification MAVLink 2 & signatures
│   ├── threat_model_stride.md     # Modèle de menace STRIDE complet
│   └── heudiasyc_interview_prep.md# Synthèse pour entretien de recherche Heudiasyc
├── scenarios/                     # Scénarios de perturbation réseau YAML
├── src/                           # Code source modulaire et typé (Python 3.11+)
│   ├── common/                    # Types, modèles Pydantic, crypto HMAC, protocole
│   ├── vehicle/                   # Simulateur drone MAVLink & machine à états Failsafe
│   ├── gcs/                       # Station sol (émission de commandes & télémétrie)
│   ├── link_manager/              # Proxy hybride, sondes RTT/Loss, FSM hystérésis
│   ├── netem/                     # Gestionnaire tc qdisc netem et scénarios
│   ├── attacker/                  # Moteur d'attaques (rejeu, spoofing, tampering, DoS)
│   └── metrics/                   # Analyse statistique Monte Carlo et visualisations
├── tests/                         # Tests unitaires et d'intégration
├── Makefile                       # Commandes d'automatisation (make up, make test...)
├── pyproject.toml                 # Dépendances et configuration des outils
└── README.md                      # Documentation principale
```

---

## 🗺️ Feuille de Route du Projet

- [x] **Étape 1 : Plan & Arborescence** (Structure, architecture, documentation théorique, outillage)
- [ ] **Étape 2 : Docker Compose, Vehicle & GCS** (Conteneurs fonctionnels, échange MAVLink 2)
- [ ] **Étape 3 : Link-Manager avec Failover** (Sondes RTT/gigue/perte, FSM à hystérésis)
- [ ] **Étape 4 : NetEm & Scénarios** (Passerelle Linux tc netem pilotée par YAML)
- [ ] **Étape 5 : Sécurité & Attaques** (Signature HMAC-SHA256, anti-rejeu, conteneur d'attaque)
- [ ] **Étape 6 : Métriques & Rapport** (Campagnes Monte Carlo $N \ge 30$, IC 95%, graphiques matplotlib)
- [ ] **Étape 7 : Tests, CI & Documentation Finale** (Pytest 100%, GitHub Actions, README complet)

