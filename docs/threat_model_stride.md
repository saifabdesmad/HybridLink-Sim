# Modèle de Menace (STRIDE) : Architecture Drone Hybride

Ce document applique la méthodologie d'analyse des menaces **STRIDE** (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege) à l'architecture de communication drone/GCS.

---

## 1. Cartographie des Actifs (*Assets*)

| Identifiant | Actif | Description | Impact en cas de compromission |
| :--- | :--- | :--- | :--- |
| **A-1** | Intégrité des Commandes C2 | Trames de pilotage (Arm, Takeoff, Waypoint, RTL, Land). | **Critique** : Crash physique, détournement du drone, collision tiers. |
| **A-2** | Disponibilité du Lien C2 | Capacité de la GCS à recevoir la télémétrie et émettre les ordres. | **Majeur** : Perte de contrôle, déclenchement forcé du failsafe. |
| **A-3** | Clé Secrète Pré-partagée ($K$) | Clé cryptographique partagée entre la GCS et le drone. | **Catastrophique** : Compromission totale de l'authentification. |
| **A-4** | Télémétrie d'état (Position/Attitude) | Informations d'altitude, coordonnées GPS, niveau batterie. | **Modéré** : Espionnage de mission, géolocalisation de la cible. |

---

## 2. Matrice d'Analyse des Menaces STRIDE

| Menace STRIDE | Scénario d'Attaque Concret | Contre-Mesure Implémentée | Efficacité / Limite |
| :--- | :--- | :--- | :--- |
| **S**poofing (Usurpation) | L'attaquant injecte un ordre `MAV_CMD_NAV_LAND` forgé pour forcer le drone à atterrir en zone hostile. | Signature MAVLink 2 (HMAC-SHA256) avec clé secrète partagée. Rejet direct sans clé valide. | **100% bloqué** tant que la clé reste secrète. |
| **T**ampering (Altération) | L'attaquant intercepte un waypoint en vol et modifie l'altitude ou les coordonnées GPS pour provoquer un crash. | Le HMAC-SHA256 couvre l'en-tête, la charge utile et le CRC. Tout bit modifié invalide la signature. | **100% bloqué**. |
| **R**epudiation (Répudiation) | Un opérateur conteste avoir émis une commande d'arrêt d'urgence ayant causé un atterrissage forcé. | Journalisation horodatée signée avec Link ID et SysID distincts par station sol. | **Atténué** (nécessiterait de l'asymétrique RSA/ECDSA pour non-répudiation légale absolue). |
| **I**nformation Disclosure | Un tiers écoute le lien radio et intercepte la position GPS et la charge utile. | *MAVLink 2 ne chiffre pas les données (pas de chiffrement symétrique standardisé par défaut)*. | **Non résolu par défaut** (Limitation documentée). Nécessite un tunnel IPsec / WireGuard ou chiffrement MAVLink expérimental. |
| **D**enial of Service (DoS) | L'attaquant inonde le canal ExpressLRS (Lien A) avec un bruit ou un flood UDP pour empêcher les commandes. | 1) Basculement automatique (*failover*) vers Lien B (Cellulaire).<br>2) Limiteur de débit local.<br>3) Failsafe automatique si les 2 liens tombent. | **Résilience accrue** par redondance hétérogène. |
| **E**levation of Privilege | Un observateur non privilégié envoie une commande de reconfiguration du géofencing ou du failsafe. | Ségrégation stricte des SysID/CompID et vérification de signature obligatoire pour les commandes de niveau administrateur. | **Bloqué**. |

---

## 3. Limites Honnêtes de la Sécurité

1. **Confidentialité non assurée** : La signature MAVLink 2 garantit l'**authenticité** et l'**intégrité**, mais les données transitent en clair. Pour un profil d'attaque avec écoute passive (espionnage), un chiffrement de niveau réseau (VPN WireGuard sur la 4G/5G) est nécessaire.
2. **Attaques par Brouillage Physique (Jamming RF)** : Si un agresseur utilise un brouilleur RF de forte puissance sur les bandes 868 MHz / 2.4 GHz et 4G/5G simultanément, aucun protocole logiciel ne peut maintenir le lien. Dans ce cas, seule la logique de **Failsafe déterministe** (RTL basé sur navigation inertielle/GPS durci) prévient la perte du vecteur.
3. **Longueur de Signature (48 bits)** : Bien que suffisante contre les attaques en direct, elle ne protège pas contre un calcul de collision hors-ligne sur des années, ce qui est acceptable pour des messages de commande valides seulement quelques secondes.

