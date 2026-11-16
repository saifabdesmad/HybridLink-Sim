# Sécurité des Communications MAVLink 2

Ce document détaille les mécanismes de sécurité de **MAVLink 2**, leur implémentation dans **HybridLink-Sim**, ainsi que les vulnérabilités résiduelles et leurs contre-mesures.

---

## 1. Structure d'une Trame MAVLink 2

Une trame MAVLink 2 commence par l'octet magique `0xFD` (contrairement à `0xFE` pour MAVLink 1) :

```
+-------+--------+---------------+---------------+---------+---------+---------+---------+---------+---------+-------+-----------+
| Magic | Payload| IncompatFlags | CompatFlags   | Seq     | SysID   | CompID  | MsgID   | Payload | Checksum| LinkID| Timestamp | Signature |
| (1B)  | Len(1B)| (1B)          | (1B)          | (1B)    | (1B)    | (1B)    | (3B)    | (0-255B)| (2B)    | (1B)  | (6B)      | (6B)      |
| 0xFD  |        | Flag 0x01 =   |               | 0..255  |         |         |         |         | CRC-16  |       | 48-bit    | HMAC-SHA256
+-------+--------+---------------+---------------+---------+---------+---------+---------+---------+---------+-------+-----------+
|<------------------------------ En-tête (10 octets) ----------------------------->|<-- Data -->|<- CRC ->|<--- Signature (13B) --->|
```

### Le flag d'incompatibilité `0x01` (`MAVLINK_IFLAG_SIGNED`)
- Si le bit 0 de `IncompatFlags` est positionné (`0x01`), le paquet comporte obligatoirement un bloc de signature de 13 octets à sa fin.
- Tout récepteur configuré pour exiger la sécurité doit rejeter immédiatement tout paquet dont le bit `0x01` est absent pour les messages critiques (commandes d'armement, waypoints, modes de vol).

---

## 2. Spécification de la Signature Cryptographique

Le bloc de signature (13 octets) comprend :
1. **Link ID (1 octet)** : Identifie le canal physique sur lequel la trame est émise (ex: `1` pour Lien A, `2` pour Lien B). Empêche les attaques par réflexion inter-canaux.
2. **Timestamp (6 octets, 48 bits)** : Horodatage en unités de 10 microsecondes écoulées depuis le 1er janvier 2015 UTC. Cet horodatage **doit être strictement croissant** pour un lien donné.
3. **Signature (6 octets, 48 bits)** : Les 48 premiers bits (6 octets les plus significatifs) d'un hash HMAC-SHA256 calculé comme suit :
   $$\text{HMAC-SHA256}_{\text{SecretKey}}(\text{Header} \parallel \text{Payload} \parallel \text{CRC} \parallel \text{LinkID} \parallel \text{Timestamp})$$

### Pourquoi 48 bits seulement ?
Dans les systèmes embarqués et les réseaux radio à faible débit (LoRa, ExpressLRS, télémétrie 433/915 MHz), ajouter un HMAC complet de 256 bits (32 octets) consommerait une part disproportionnée de la bande passante (un paquet moyen fait ~40 octets ; +32 octets représenterait un surcoût de 80%). Un condensat de 48 bits offre une résistance suffisante ($2^{48} \approx 2.8 \times 10^{14}$ combinaisons) face à la falsification en temps réel sur canal radio.

---

## 3. Faiblesses Théoriques & Contre-Mesures Avancées

### A. Dérive d'horloge (*Clock Skew*) & Attaque par Rejeu Fenêtré
- **Problème** : Si le drone et la GCS ne partagent pas une horloge synchronisée (ex: absence de fix GPS au démarrage dans un hangar), une tolérance temporelle $\Delta t$ est nécessaire. Un attaquant qui capture une trame légitime peut la rejouer pendant cette fenêtre de tolérance.
- **Contre-mesure HybridLink-Sim** :
  - **Fenêtre glissante d'anti-rejeu (style IPsec RFC 4303)** : Chaque trame acceptée enregistre un timestamp local. Toute trame reçue avec un timestamp inférieur ou égal au dernier timestamp validé pour ce `(LinkID, SysID)` est immédiatement jetée.
  - **Nonce / Challenge-Response** pour les actions critiques (Armement, Désarment, Failsafe override).

### B. Déni de Service (DoS) par Inondation
- **Problème** : Vérifier un HMAC-SHA256 consomme des cycles CPU. Un attaquant peut inonder le récepteur de trames aléatoires pour saturer la bande passante radio ou le microcontrôleur de vol.
- **Contre-mesure HybridLink-Sim** :
  - **Filtrage à deux niveaux (Two-Tier Drop)** : Vérification rapide de l'en-tête (Magic `0xFD`, longueur, SysID) et de la fenêtre temporelle avant de calculer le HMAC.
  - **Limiteur de débit adaptatif (Token Bucket Rate Limiter)** au niveau du `link-manager` pour étouffer le flux malveillant avant qu'il n'atteigne le contrôleur de vol.

