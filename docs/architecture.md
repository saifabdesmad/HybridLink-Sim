# Architecture Système : HybridLink-Sim

Ce document présente les choix d'ingénierie et l'architecture logicielle du projet **HybridLink-Sim**.

---

## 1. Contexte & Problématique Robotique

Dans les opérations de drones autonomes ou télé-opérés (UAV - *Unmanned Aerial Vehicle*), en particulier en vol hors vue directe (**BVLOS** - *Beyond Visual Line of Sight*), le lien de commande et contrôle (**C2** - *Command and Control*) constitue le point de défaillance unique le plus critique.

### Les deux technologies complémentaires :
1. **Lien A - Radio dédiée longue portée (ex. ExpressLRS / LoRa 868-915 MHz / 2.4 GHz)** :
   - **Forces** : Latence ultra-faible (< 10 ms), gigue quasi-nulle, grande robustesse aux perturbations électromagnétiques locales, portée kilométrique sans dépendance d'infrastructure tierce.
   - **Faiblesses** : Bande passante très restreinte (quelques kbps à quelques dizaines de kbps), inadaptée au flux vidéo haute résolution ou à la télémétrie lourde.
2. **Lien B - Cellulaire (4G LTE / 5G NR)** :
   - **Forces** : Débit élevé (plusieurs Mbps), couverture quasi-nationale via infrastructure télécom, transport simultané de vidéo HD et de télémétrie.
   - **Faiblesses** : Latence variable (30 à 150 ms), gigue importante (liée aux files d'attente réseau / *bufferbloat*), pertes par paquets lors des changements d'antennes relais (*handovers*), zones blanches ou saturation cellulaire en zone urbaine dense.

**Objectif d'HybridLink-Sim** : Fournir une couche de transport et de routage intelligente (Overlay Multi-liens) garantissant la continuité de service MAVLink 2, la sécurité cryptographique et le repli déterministe (failsafe).

---

## 2. Vue d'Ensemble des Flux et Topologie Docker

```
               +---------------------------------------------------+
               |                    GCS (Station Sol)              |
               |         (Générateur de commandes & Télémétrie)    |
               +-------------------------+-------------------------+
                                         |
                                         | Interface locale (UDP loopback)
                                         v
               +---------------------------------------------------+
               |               LINK-MANAGER (Ground)               |
               |   - Émetteur / Récepteur Multipath                |
               |   - Sondes de qualité (RTT, Jitter, Loss)         |
               |   - Machine à États de sélection avec Hystérésis  |
               +-------------+-----------------------+-------------+
                             |                       |
                 Lien A      |                       |  Lien B
            (Port 14551 UDP) |                       |  (Port 14552 UDP)
                             v                       v
               +---------------------------------------------------+
               |             NETEM (Passerelle Réseau)             |
               |   - Émulation Linux tc qdisc netem                |
               |   - Injection de profil A (Faible latence, 50kbps)|
               |   - Injection de profil B (Latence variable, perte|
               |   - Scénarios YAML (dégradations, coupures)       |
               +-------------+-----------------------+-------------+
                             |                       |
               +-------------+-----------------------+-------------+
               |             ATTACKER (Vecteur d'Attaque)          |
               |   - Injection / Sniffing sur Lien A & Lien B      |
               |   - Attaques : Rejeu, Usurpation, DoS, Altération |
               +-------------+-----------------------+-------------+
                             |                       |
                             v                       v
               +---------------------------------------------------+
               |                LINK-MANAGER (Air)                 |
               |   - Dé-multiplexage & Filtrage doublons           |
               |   - Vérification signature MAVLink 2 & Fenêtre    |
               +-------------------------+-------------------------+
                                         |
                                         | Interface interne sécurisée
                                         v
               +---------------------------------------------------+
               |                   VEHICLE (UAV)                   |
               |   - Moteur de vol MAVLink (Heartbeat, Attitude)   |
               |   - Exécuteur de commandes validées               |
               |   - Failsafe déterministe (Timeout Heartbeat)     |
               +---------------------------------------------------+
```

---

## 3. Architecture Modulaire : Ports et Adaptateurs (Hexagonale)

Pour garantir la testabilité et permettre de remplacer les couches sans réécrire la logique métier :

1. **Domaine Métier (Core)** :
   - `FSM` : Machine à états finis du failover (états : `LINK_A_PRIMARY`, `LINK_B_BACKUP`, `DEGRADED`, `BLACKOUT`).
   - `FailsafeManager` : Détection de perte de signal et passage en mode de sécurité (`RTL`, `LAND`, `HOLD`).
   - `CryptoEngine` : Vérification des signatures MAVLink 2 et détection d'anti-rejeu par fenêtre glissante.
2. **Ports (Interfaces abstraites)** :
   - `ILinkTransport` : Contrat d'envoi/réception de trames (méthodes `send_frame`, `receive_frame`).
   - `ILinkMonitor` : Contrat de mesure de métriques de lien (`get_rtt`, `get_loss_rate`, `get_jitter`).
   - `ICommandHandler` : Traitement des commandes de pilotage validées.
3. **Adaptateurs (Adapters)** :
   - `UdpTransportAdapter` : Transport réseau réel sur sockets UDP Docker.
   - `SimulatedTransportAdapter` : Transport en mémoire pour tests unitaires ultra-rapides.
   - `PyMavlinkAdapter` : Sérialisation / désérialisation MAVLink 2 via `pymavlink`.

---

## 4. Compromis Techniques Notables

| Sujet | Choix retenu | Alternative écartée | Justification défendable en entretien |
| :--- | :--- | :--- | :--- |
| **Vecteur Aérien** | Simulateur Python MAVLink 2 natif | ArduPilot SITL complet (C++) | ArduPilot SITL compile plusieurs gigaoctets de C++, requiert d'importantes ressources CPU et introduit du non-déterminisme temporel en CI. Le simulateur Python natif implémente la spécification exacte du protocole MAVLink 2, permet des runs Monte Carlo $N \ge 30$ reproductibles en quelques secondes, tout en respectant l'encadrement strict des trames et de la cryptographie. |
| **Émulation Réseau** | Passerelle Linux avec `tc netem` | Simulation logicielle pure en Python (ex: `asyncio.sleep`) | `tc netem` s'exécute au niveau du noyau Linux (gestion réelle des files d'attente socket `qdisc`, drops par débordement de buffer). C'est le standard utilisé en recherche réseau (IETF, laboratoires CNRS) pour reproduire fidèlement le comportement radio/cellulaire. |
| **Couche Transport** | UDP Datagrammes | TCP | MAVLink est nativement conçu pour UDP. En robotique temps-réel, le contrôle de congestion et les retransmissions TCP créent du *Head-of-Line Blocking* (un paquet perdu bloque tous les suivants), ce qui est inacceptable pour un pilotage de drone. |

