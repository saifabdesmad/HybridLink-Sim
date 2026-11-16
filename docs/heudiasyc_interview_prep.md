# Guide d'Entretien Recherche : Laboratoire Heudiasyc (UTC / CNRS)

Ce document synthétise les concepts théoriques et les arguments techniques à maîtriser pour défendre le projet **HybridLink-Sim** devant un jury ou un chercheur d'Heudiasyc.

---

## 1. Pourquoi ce sujet résonne-t-il avec Heudiasyc ?

Le laboratoire **Heudiasyc** (Heuristique et Diagnostic des Systèmes Complexes, UMR 7253 CNRS / UTC) est une référence internationale dans les domaines :
- De la robotique autonome terrestre et aérienne (drones, flottes de véhicules).
- Des réseaux véhiculaires et communications résilientes (V2X, C2, tolérance aux pannes).
- De la sûreté de fonctionnement (*Dependability*), diagnostic d'état et prise de décision sous incertitude.

Présenter un banc de test modulaire évaluant la résilience d'un lien hybride radio/cellulaire démontre immédiatement une maturité en ingénierie logicielle appliquée à la recherche expérimentale.

---

## 2. Concepts Clés à Connaître & Défendre

### A. Le Flapping et l'Hystérésis
- **Question piège** : *"Si le lien A a une meilleure latence que le lien B mais subit des micro-coupures fréquentes, que se passe-t-il ?"*
- **Réponse attendue** : Si l'on bascule instantanément dès qu'une métrique dépasse un seuil, le système oscille en permanence entre les deux liens (phénomène de **flapping** ou papillonnage). Cela dégrade la qualité de service, réordonne les paquets et sature la bande passante.
- **Solution mise en œuvre** : Une **machine à états finis avec hystérésis temporelle et métrique**. Pour revenir sur le lien A après une dégradation, le lien A doit rester stable et au-dessus d'un seuil $Q_{\text{recover}}$ pendant une durée minimale $T_{\text{hysteresis}}$ (ex: 2.0 secondes).

### B. MAVLink 1 vs MAVLink 2
- **Question** : *"Pourquoi ne pas simplement utiliser MAVLink standard ?"*
- **Réponse** : MAVLink 1 ne possède aucun mécanisme de sécurité natif (n'importe quel émetteur sur la même fréquence radio peut injecter des paquets `COMMAND_LONG` et prendre le contrôle du drone). MAVLink 2 apporte le flag d'incompatibilité `0x01` et l'en-tête de signature HMAC-SHA256, que nous combinons avec une fenêtre anti-rejeu stricte.

### C. Propriétés Formelles de Sûreté (Safety Properties)
En recherche et en sûreté critique, on formalise les garanties du système :
1. **Sûreté d'Action (Authenticity)** : Aucune commande non authentifiée ou rejouée n'est exécutée :
   $$\forall c \in \text{ExecutedCommands}, \quad \text{VerifyHMAC}(c, K) = \text{True} \land \text{Timestamp}(c) > \text{LastSeenTimestamp}$$
2. **Bornage Temporel du Failsafe (Liveness / Real-Time)** : En cas de perte totale de communication, le drone entre en mode de sécurité (RTL) en un temps strictement majoré :
   $$T_{\text{reaction}} \le T_{\text{timeout}} + \epsilon_{\text{max}}$$
   *(dans notre modèle : $3.0\text{s} + 0.2\text{s} = 3.2\text{s}$ max).*

### D. Approche Monte Carlo & Rigueur Expérimentale
- **Question** : *"Comment prouvez-vous que vos résultats ne sont pas un artefact de simulation ?"*
- **Réponse** : Un seul run n'a aucune valeur statistique en raison de la nature stochastique des réseaux (gigue, pertes aléatoires). Nous exécutons chaque scénario au moins 30 fois ($N \ge 30$) pour calculer des moyennes avec **intervalles de confiance à 95%** (selon le théorème central limite ou loi de Student), ainsi que les percentiles extrêmes (p95, p99) indispensables pour les systèmes temps-réel.

---

## 3. Réponses aux Questions Difficiles

| Question d'un chercheur | Réponse constructive |
| :--- | :--- |
| *"Pourquoi ne pas avoir utilisé de vraies radios ExpressLRS ?"* | "Pour valider la logique de contrôle et de sécurité, il est crucial de disposer d'un environnement **100% reproductible et automatisable en CI/CD**. Les radios réelles subissent les réflexions multipath de la pièce et des aléas non maîtrisés. Le banc logiciel avec `tc netem` permet d'injecter des profils contrôlés. La suite logique de mes travaux serait justement d'intégrer un banc Hardware-in-the-Loop (HITL) avec vraies radios SDR ou modules ExpressLRS." |
| *"La signature 48-bit n'est-elle pas trop faible face aux attaques modernes ?"* | "Elle est un compromis d'ingénierie embarquée : sur un canal à 50 kbps, 32 octets de signature représenteraient une surcharge inacceptable. 48 bits offrent $2.8 \times 10^{14}$ combinaisons. Comme chaque paquet comporte un timestamp valide sur quelques dizaines de millisecondes, une attaque par force brute en temps réel est calculatoirement impossible à travers le goulot d'étranglement radio." |

