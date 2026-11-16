# HybridLink-Sim : Architecture de Communication Hybride, Sécurisée et Résiliente pour Drone

[![CI](https://github.com/votre-nom/HybridLink-Sim/actions/workflows/ci.yml/badge.svg)](https://github.com/votre-nom/HybridLink-Sim/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![MAVLink 2 Signed](https://img.shields.io/badge/protocol-MAVLink_2_HMAC--SHA256-orange.svg)](docs/mavlink_security.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![R&D: Heudiasyc CNRS](https://img.shields.io/badge/Research-Heudiasyc_UMR_CNRS_7253-purple.svg)](https://www.hds.utc.fr/)

> **Projet d'Ingénierie & Recherche** : Conception, implémentation et évaluation expérimentale stochastique (Monte Carlo, $N \ge 30$) d'une liaison de commande et contrôle (**C2**) hybride radio/cellulaire pour drone autonome (UAV), avec basculement sans *flapping*, sécurité MAVLink 2 durcie (RFC 4303) et repli déterministe (*failsafe*).
> 
> *Dossier technique préparé dans le cadre d'une candidature à un stage de recherche au **Laboratoire Heudiasyc (UMR CNRS 7253 / Université de Technologie de Compiègne - UTC)**.*

---

## 📑 Sommaire
1. [Contexte & Problématique Scientifique](#1-contexte--problématique-scientifique)
2. [Architecture Système & Choix d'Ingénierie](#2-architecture-système--choix-dingénierie)
3. [Machine à États Finis (FSM) & Hystérésis Anti-Flapping](#3-machine-à-états-finis-fsm--hystérésis-anti-flapping)
4. [Sécurité Cryptographique MAVLink 2 & Modèle STRIDE](#4-sécurité-cryptographique-mavlink-2--modèle-stride)
5. [Propriétés Formelles de Sûreté (Safety Properties)](#5-propriétés-formelles-de-sûreté-safety-properties)
6. [Résultats Expérimentaux & Campagnes Monte Carlo ($N=30$)](#6-résultats-expérimentaux--campagnes-monte-carlo-n30)
7. [Reproduction en Une Commande](#7-reproduction-en-une-commande)
8. [Limites Honnêtes & Perspectives de Recherche (Heudiasyc)](#8-limites-honnêtes--perspectives-de-recherche-heudiasyc)

---

## 1. Contexte & Problématique Scientifique

Lors d'un vol de drone hors vue directe (**BVLOS** - *Beyond Visual Line of Sight*), le lien de commande et contrôle (**C2**) est le point de vulnérabilité le plus critique. L'industrie et la recherche font face à un dilemme physique fondamental :
- **Lien A - Radio dédiée basse fréquence (ex: ExpressLRS / LoRa 868-915 MHz / 2.4 GHz)** :
  - *Avantages* : Latence ultra-courte (< 10 ms), gigue négligeable, liaison directe sol-air sans dépendance d'infrastructure tierce, excellente pénétration.
  - *Limites* : Bande passante drastiquement limitée ($\sim 50\text{ kbps}$), incapable de transporter de la vidéo ou de la télémétrie dense.
- **Lien B - Réseau Cellulaire (4G LTE / 5G NR)** :
  - *Avantages* : Débit massif (plusieurs Mbps), portée géographique quasi-illimitée via antennes relais opérateurs.
  - *Limites* : Latence moyenne à élevée (30 à 150 ms), forte gigue (*jitter* lié aux files d'attente d'antennes relais et au *bufferbloat*), pertes par paquets lors des changements d'antennes (*handovers*), zones blanches ou saturation soudaine en zone urbaine.

**HybridLink-Sim** répond à cette problématique en concevant un gestionnaire de liaisons hybrides capable de :
1. Mesurer en temps réel la qualité de service (QoS) de chaque canal (RTT lissé EWMA, gigue normalisée **RFC 3550**, taux de perte par fenêtre de paquets).
2. Basculer de façon transparente (*failover*) du Lien A vers le Lien B en cas de panne ou dégradation.
3. Éviter le phénomène destructeur de **flapping** (oscillations permanentes entre les deux liens) grâce à une **hystérésis temporelle et métrique**.
4. Neutraliser 100% des attaques d'injection de commandes grâce à l'authentification **MAVLink 2 signée (SHA-256)** et une **fenêtre glissante anti-rejeu (RFC 4303)**.
5. Déclencher un atterrissage ou retour au point de départ (**Failsafe RTL**) borné dans le temps lors d'un blackout total.

---

## 2. Architecture Système & Choix d'Ingénierie

Le banc est conçu selon le patron **Ports & Adaptateurs (Architecture Hexagonale)** pour isoler la logique métier (cryptographie, FSM, failsafe) des détails réseau (UDP, NetEm, SITL).

```
                      +-----------------------------------+
                      |         GCS (Station Sol)         |
                      |   - Émetteur de commandes signées |
                      |   - Écoute télémétrie & calcul RTT|
                      +-----------------+-----------------+
                                        | (UDP local :14555)
                                        v
                      +-----------------------------------+
                      |           LINK-MANAGER            |
                      |   - Sondes QoS (RTT, Jitter RFC)  |
                      |   - FSM avec Hystérésis (2.0s)    |
                      |   - Déduplication flux descendant |
                      +--------+-----------------+--------+
                               |                 |
                   Lien A      |                 | Lien B
             (ExpressLRS :14551|                 | (4G/5G :14552)
                               v                 v
                      +-----------------------------------+
                      |      NETEM (Passerelle Réseau)    |
                      |   - Noyau Linux tc qdisc netem    |
                      |   - Fallback stochastique N(mu,s) |
                      |   - Scénarios de coupure YAML     |
                      +--------+-----------------+--------+
                               |                 |
                               +--------+--------+
                                        |  <------- ATTACKER (Rejeu, Spoofing,
                                        v                     Tampering, DoS Flood)
                      +-----------------------------------+
                      |           VEHICLE (UAV)           |
                      |   - Simulateur MAVLink 2 natif    |
                      |   - Moteur Cryptographique        |
                      |   - Fenêtre Anti-Rejeu (RFC 4303) |
                      |   - Failsafe Déterministe (RTL)   |
                      +-----------------+-----------------+
                                        |
                                        v
                      +-----------------------------------+
                      |              METRICS              |
                      |   - Évaluation Monte Carlo (N>=30)|
                      |   - Intervalles de Confiance 95%  |
                      |   - Export CSV & Graphiques       |
                      +-----------------------------------+
```

### Justification des Choix Techniques (Défense en Entretien) :
- **Simulateur MAVLink 2 Python vs ArduPilot SITL C++** : ArduPilot SITL complet requiert de volumineux submodules git, consomme 2 Go de RAM par instance et génère du non-déterminisme d'ordonnancement. Notre moteur Python natif respecte à 100% la structure binaire MAVLink 2, tout en permettant d'exécuter 30 répétitions Monte Carlo complètes en moins de 10 secondes.
- **UDP Datagrammes vs TCP** : TCP intègre un contrôle de congestion et des retransmissions automatiques. En cas de perte d'un paquet radio, TCP bloque tous les paquets suivants (*Head-of-Line Blocking*), provoquant un gel de télémétrie inadmissible pour le pilotage d'un drone. MAVLink est nativement bâti sur UDP.
- **Passerelle tc netem Double-Couche** : Utilisation de `tc netem` au niveau noyau Linux sous Docker pour une fidélité physique maximale (files d'attente `qdisc`), doublée d'un fallback stochastique Python ($\mathcal{N}(\mu, \sigma)$ et Bernoulli) pour exécuter les tests sous Windows et en CI sans privilèges root.

---

## 3. Machine à États Finis (FSM) & Hystérésis Anti-Flapping

L'automate de basculement implémenté dans `src/link_manager/fsm.py` comporte 4 états :
1. `PRIMARY_LINK_A` : Canal nominal (ExpressLRS). Les commandes transitent par le Lien A, le Lien B reste en veille active.
2. `FAILOVER_LINK_B` : Canal de repli (4G/5G). Activé dès que le Lien A est dégradé (RTT > 40 ms, pertes > 8%) ou coupé.
3. `DUAL_REDUNDANT` : En cas de dégradation sévère simultanée, duplication des paquets sur les deux canaux.
4. `TOTAL_BLACKOUT` : Perte complète des deux liens de communication.

```
                  +--------------------------------+
                  |         PRIMARY_LINK_A         |
                  +---------------+----------------+
                                  |
            Lien A DOWN/Dégradé   |   Lien A rétabli STABLE
            (Bascule immédiate)   |   pendant >= T_hysteresis (2.0s)
                                  v
                  +---------------+----------------+
                  |        FAILOVER_LINK_B         |
                  +---------------+----------------+
                                  |
            Lien A et Lien B DOWN |   Rétablissement d'un lien
            (Perte totale)        |
                                  v
                  +---------------+----------------+
                  |         TOTAL_BLACKOUT         |
                  +--------------------------------+
```

### Le Principe de l'Hystérésis Temporelle
Lorsqu'un drone s'éloigne ou passe derrière un bâtiment, la liaison radio subit souvent des reconnexions brèves et instables. Un routeur naïf basculerait immédiatement sur le Lien A, puis sur le Lien B quelques millisecondes plus tard : c'est le **flapping**.
- **Notre mécanisme** : Lorsque le Lien A redevient sain, la FSM arme un chronomètre d'observation `link_a_recovered_since = now`. Le basculement de retour n'est autorisé que si le Lien A reste sans interruption dans l'état `HEALTHY` pendant au moins **$T_{\text{hysteresis}} = 2.0\text{ secondes}$**. Toute défaillance durant cette fenêtre réinitialise le minuteur.

---

## 4. Sécurité Cryptographique MAVLink 2 & Modèle STRIDE

### Structure d'une Trame Sécurisée MAVLink 2
Une trame commence par l'octet `0xFD` et porte le bit d'incompatibilité `0x01` (`MAVLINK_IFLAG_SIGNED`). Elle se termine par un bloc de signature de 13 octets :
- **Link ID (1 octet)** : Évite qu'une trame capturée sur le Lien B soit réinjectée sur le Lien A.
- **Timestamp (6 octets, 48 bits)** : Horodatage en unités de 10 microsecondes depuis le 01/01/2015 UTC.
- **Signature (6 octets, 48 bits)** : Condensat tronqué SHA-256 calculé avec la clé secrète partagée.

$$\text{Signature} = \text{SHA-256}(\text{CléSecrète} \parallel \text{Trame})[:6]$$

### Fenêtre Anti-Rejeu (RFC 4303)
Pour contrer l'attaque par rejeu où un agresseur réémet un ordre d'atterrissage légitime capturé précédemment, notre moteur maintient une fenêtre glissante de taille $W = 64$ par couple `(SysID, LinkID)` :
- Si $\text{timestamp} > \text{max\_timestamp}$ : Trame acceptée, fenêtre avancée.
- Si $\text{timestamp} < \text{seuil\_fenêtre}$ : Trame rejetée (périmée).
- Si $\text{timestamp}$ déjà présent dans l'historique récent : **Trame rejetée (attaque par rejeu bloquée)**.

### Matrice d'Analyse des Menaces STRIDE

| Menace STRIDE | Scénario d'Attaque Concret | Contre-Mesure Implémentée | Efficacité / Limite |
| :--- | :--- | :--- | :--- |
| **S**poofing | Injection d'un faux ordre `LAND` ou `DISARM` par un pirate au sol. | Signature MAVLink 2 SHA-256 avec clé secrète 256 bits. | **100% bloqué** sans la clé. |
| **T**ampering | Modification des coordonnées d'un waypoint en vol (Man-in-the-Middle). | Condensat SHA-256 couvrant en-tête et payload. Tout bit modifié invalide la signature. | **100% bloqué**. |
| **R**epudiation | Un télépilote conteste l'émission d'un ordre d'arrêt d'urgence. | Journalisation horodatée signée avec Link ID et SysID distincts par station. | **Atténué** (nécessiterait de l'asymétrique pour valeur légale). |
| **I**nformation Disclosure | Écoute passive de la position GPS et de l'altitude du drone. | *MAVLink 2 standard ne chiffre pas les données*. | **Non résolu nativement** (Nécessite tunnel WireGuard/IPsec sur 4G). |
| **D**enial of Service | Inondation radio (DoS flood) pour saturer le récepteur et bloquer le C2. | 1) Basculement automatique sur Lien B.<br>2) Limiteur de débit local.<br>3) Failsafe RTL autonome. | **Résilience accrue** par redondance hétérogène. |
| **E**levation of Privilege | Un observateur injecte des ordres de niveau commande de vol sans armement. | Vérification stricte des SysID/CompID et signature obligatoire sur `COMMAND_LONG`. | **Bloqué**. |

---

## 5. Propriétés Formelles de Sûreté (Safety Properties)

1. **Propriété 1 (Authenticité & Intégrité d'Action)** :
   $$\forall c \in \text{ExecutedCommands}, \quad \text{VerifySignature}(c, K) = \text{True} \land \text{Timestamp}(c) \notin \text{SeenTimestamps}$$
   *Aucune commande non signée, falsifiée ou rejouée ne peut modifier l'état du drone.*
2. **Propriété 2 (Bornage Temporel du Failsafe)** :
   $$\text{Si } \forall l \in \{A, B\}, \text{Status}(l) = \text{DOWN} \text{ pendant } t \ge T_{\text{failsafe}} \implies \text{Mode} \leftarrow \text{RTL} \text{ en } t \le T_{\text{failsafe}} + 200\text{ ms}$$
   *En cas de blackout total, le drone passe en mode de sauvegarde en moins de 3.2 secondes.*
3. **Propriété 3 (Stabilité Anti-Flapping)** :
   $$\text{Switches}(B \to A) \le 1 \quad \text{par fenêtre de } 2.0\text{ secondes}$$
   *Aucun retour intempestif sur le lien primaire ne peut survenir sans observation préalable continue.*

---

## 6. Résultats Expérimentaux & Campagnes Monte Carlo ($N=30$)

Les données ci-dessous proviennent de l'exécution de **30 runs indépendants** par scénario opérationnel (données brutes disponibles dans `data/metrics/monte_carlo_runs.csv`) :

| Scénario Opérationnel | Mode Sécurité | RTT $p_{50}$ | RTT $p_{95}$ | RTT $p_{99}$ | RTT Moyen ($\pm \text{IC}_{95\%}$) | Disponibilité | Temps Basculement | Rejet Attaques | Ordres Pirates Exécutés |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **01_nominal** | ACTIVE | 8.0 ms | 10.5 ms | 11.3 ms | $8.0 \pm 0.08$ ms | $100.0\%$ | N/A | $100.0\%$ | **0** |
| **02_degradation_link_a** | ACTIVE | 48.6 ms | 66.5 ms | 71.4 ms | $48.3 \pm 0.62$ ms | $99.6\%$ | $26.4 \pm 2.58$ ms | $100.0\%$ | **0** |
| **03_cut_link_a_recovery**| ACTIVE | 47.6 ms | 65.8 ms | 70.8 ms | $47.9 \pm 0.74$ ms | $99.7\%$ | $25.0 \pm 1.74$ ms | $100.0\%$ | **0** |
| **04_congestion_link_b** | ACTIVE | 7.9 ms | 10.2 ms | 35.9 ms | $7.9 \pm 0.06$ ms | $100.0\%$ | N/A | $100.0\%$ | **0** |
| **06_spoofing** *(Sans Sécurité)* | DÉSACTIVÉE | 8.5 ms | 14.0 ms | 20.0 ms | $9.0 \pm 0.00$ ms | $40.0\%$ | N/A | **0.0%** | **300** *(Compromis)* |
| **06_spoofing** *(Avec Sécurité)* | ACTIVE | 8.0 ms | 12.0 ms | 16.0 ms | $9.0 \pm 0.00$ ms | $100.0\%$ | N/A | **100.0%** | **0** *(Protégé)* |
| **07_replay** *(Sans Sécurité)* | DÉSACTIVÉE | 8.5 ms | 14.0 ms | 20.0 ms | $9.0 \pm 0.00$ ms | $40.0\%$ | N/A | **0.0%** | **300** *(Compromis)* |
| **07_replay** *(Avec Sécurité)* | ACTIVE | 8.0 ms | 12.0 ms | 16.0 ms | $9.0 \pm 0.00$ ms | $100.0\%$ | N/A | **100.0%** | **0** *(Protégé)* |
| **08_tampering** *(Avec Sécurité)*| ACTIVE | 8.0 ms | 12.0 ms | 16.0 ms | $9.0 \pm 0.00$ ms | $100.0\%$ | N/A | **100.0%** | **0** *(Protégé)* |
| **09_dos_flood** *(Avec Sécurité)*| ACTIVE | 8.0 ms | 12.0 ms | 16.0 ms | $9.0 \pm 0.00$ ms | $100.0\%$ | N/A | **100.0%** | **0** *(Protégé)* |

### Visualisations Graphiques Générées (`data/plots/`) :
- `01_latency_timeline_failover.png` : Tracé chronologique du RTT montrant le saut à 48 ms lors de la coupure et le retour à 8 ms après la fenêtre d'hystérésis.
- `02_latency_percentiles.png` : Comparaison des percentiles $p_{50}$, $p_{95}$ et $p_{99}$ sous perturbation.
- `03_security_comparison.png` : Contraste saisissant entre mode sans sécurité (300 commandes pirates exécutées) et mode sécurisé (0 commande frauduleuse).
- `04_failover_recovery_distribution.png` : Boxplots illustrant la dispersion statistique des temps de réaction.

---

## 7. Reproduction en Une Commande

### Prérequis
- Python 3.11+
- Git
- Docker & Docker Compose (optionnel mais supporté)

### Option A : Exécution Locale Rapide (Sans Docker)
```powershell
# 1. Installer les dépendances
python -m pip install -e ".[dev]"

# 2. Lancer la suite de 23 tests automatisés
python -m pytest tests/ -v

# 3. Lancer la campagne complète Monte Carlo (N=30) et générer les graphiques
python -m src.metrics.main --runs 30
```

### Option B : Déploiement Conteneurisé Multi-Services (Docker Compose)
```bash
# Démarrer les 4 services principaux (Vehicle, NetEm, Link-Manager, GCS)
docker compose up -d --build

# Lancer une campagne d'attaque spécifique
docker compose --profile attack run attacker

# Consulter l'état des liaisons en direct
docker compose logs -f link-manager
```

---

## 8. Limites Honnêtes & Perspectives de Recherche (Heudiasyc)

Dans une démarche scientifique rigoureuse, il convient de souligner les limites actuelles du banc de simulation :
1. **Propagation Radio Simplifiée** : Le modèle actuel applique un délai gaussien et des pertes de Bernoulli. En milieu réel (forêt, canyon urbain), la propagation subit des masquages d'antenne liés à l'attitude du drone (effet de masque du châssis en carbone lors d'un virage serré) et des évanouissements rapides (*Rayleigh/Rician fading*).
2. **Synchronisation d'Horloge** : La fenêtre anti-rejeu repose sur une dérive temporelle bornée entre la station sol et le drone (assurée dans la réalité par les récepteurs GNSS). Un décalage d'horloge prolongé sans GPS requerrait un protocole de resynchronisation sécurisé (ex: challenge-response avec nonces).
3. **Absence de Chiffrement de la Télémétrie** : Conformément à la norme MAVLink 2, les trames sont **signées** mais non chiffrées (la charge utile circule en clair). Pour contrer l'écoute passive (espionnage de position), un tunnel chiffré de couche réseau (WireGuard) est requis sur le lien cellulaire.

### Pistes d'Ouverture pour le Stage de Recherche à Heudiasyc :
- **Banc Hardware-in-the-Loop (HITL)** : Remplacer la couche NetEm logicielle par deux véritables émetteurs/récepteurs radio ExpressLRS 868 MHz reliés en coaxial ou en chambre anéchoïque.
- **Routage Hybride Adaptatif par Apprentissage par Renforcement** : Entraîner un agent intelligent prédisant la perte de lien radio quelques secondes avant sa survenue en fonction de la trajectoire du drone et de la carte topologique du laboratoire.
- **Microcontrôleur Dédié à la Passerelle Radio** : Déporter la FSM et la vérification cryptographique sur un microcontrôleur temps-réel durci (ex: STM32H7 double-cœur sous FreeRTOS / Zephyr RTOS) indépendant du calculateur de mission.
