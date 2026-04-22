"""
Agenda & Rappels Employés — YukpoAssurance
Gestion des tâches, rendez-vous et rappels automatiques pour les équipes.

Fonctionnalités :
- Agenda personnel par employé (événements, RDV, réunions)
- Tâches avec priorité, échéance, avancement
- Rappels automatiques multi-canal (email, WhatsApp, notification)
- Liaison avec les modules métier (sinistres, contrats, réunions)
- Vues : jour, semaine, mois
- Notifications d'équipe
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────

PRIORITES = ["basse", "normale", "haute", "urgente"]
STATUTS_TACHE = ["a_faire", "en_cours", "bloquee", "terminee", "annulee"]
TYPES_EVENEMENT = [
    "rendez_vous", "reunion", "echeance", "tache",
    "rappel", "conge", "formation", "deplacement",
]
COULEURS_PRIORITE = {
    "basse": "#6B7280",
    "normale": "#3B82F6",
    "haute": "#F59E0B",
    "urgente": "#EF4444",
}


# ─────────────────────────────────────────────────────────────
# Générateur de rappels automatiques
# ─────────────────────────────────────────────────────────────

@dataclass
class Rappel:
    type_source: str        # tache | evenement | echeance_contrat | sinistre | reunion
    source_id: int
    employe_id: int
    message: str
    canal: str              # email | whatsapp | push
    a_envoyer_le: datetime


class GenerateurRappels:
    """Génère les rappels à envoyer selon les règles métier."""

    def rappels_pour_tache(
        self,
        tache_id: int,
        employe_id: int,
        titre: str,
        date_echeance: datetime,
        jours_avant: int = 1,
        canal: str = "push",
    ) -> List[Rappel]:
        """Génère des rappels pour une tâche proche de son échéance."""
        rappels = []
        maintenant = datetime.now(timezone.utc)

        # Rappel J-N
        date_rappel = date_echeance - timedelta(days=jours_avant)
        if date_rappel > maintenant:
            rappels.append(Rappel(
                type_source="tache",
                source_id=tache_id,
                employe_id=employe_id,
                message=f"📋 Tâche « {titre} » : échéance dans {jours_avant} jour(s).",
                canal=canal,
                a_envoyer_le=date_rappel,
            ))

        # Rappel le jour J matin (8h)
        date_j = date_echeance.replace(hour=8, minute=0, second=0, microsecond=0)
        if date_j > maintenant and date_j != date_rappel:
            rappels.append(Rappel(
                type_source="tache",
                source_id=tache_id,
                employe_id=employe_id,
                message=f"⚠️ Tâche « {titre} » : échéance AUJOURD'HUI !",
                canal=canal,
                a_envoyer_le=date_j,
            ))

        # Rappel post-échéance (retard)
        if date_echeance < maintenant:
            rappels.append(Rappel(
                type_source="tache",
                source_id=tache_id,
                employe_id=employe_id,
                message=f"🔴 RETARD — Tâche « {titre} » n'a pas été terminée à temps.",
                canal=canal,
                a_envoyer_le=maintenant + timedelta(hours=1),
            ))

        return rappels

    def rappels_pour_evenement(
        self,
        event_id: int,
        employe_id: int,
        titre: str,
        date_debut: datetime,
        delais_minutes: List[int],
        canal: str = "push",
    ) -> List[Rappel]:
        """Génère des rappels avant un événement."""
        rappels = []
        maintenant = datetime.now(timezone.utc)

        for minutes in delais_minutes:
            date_rappel = date_debut - timedelta(minutes=minutes)
            if date_rappel > maintenant:
                if minutes >= 1440:
                    label = f"{minutes // 1440} jour(s)"
                elif minutes >= 60:
                    label = f"{minutes // 60}h"
                else:
                    label = f"{minutes} min"

                rappels.append(Rappel(
                    type_source="evenement",
                    source_id=event_id,
                    employe_id=employe_id,
                    message=f"📅 Rappel — « {titre} » dans {label}.",
                    canal=canal,
                    a_envoyer_le=date_rappel,
                ))

        return rappels

    def rappels_echeances_cima(
        self,
        compagnie_id: int,
        employes_rh: List[int],  # IDs des responsables
    ) -> List[Rappel]:
        """Rappels automatiques des échéances réglementaires CIMA."""
        rappels = []
        maintenant = datetime.now(timezone.utc)
        mois_courant = maintenant.month
        annee = maintenant.year

        echeances_cima = [
            {"mois": 3, "jour": 31, "titre": "C1 — Compte rendu annuel à transmettre à la CRCA", "canal": "email"},
            {"mois": 6, "jour": 30, "titre": "C2 — États trimestriels (T1) à la CRCA", "canal": "email"},
            {"mois": 9, "jour": 30, "titre": "C2 — États trimestriels (T2) à la CRCA", "canal": "email"},
            {"mois": 12, "jour": 15, "titre": "C15 — Plan comptable provisoire fin d'exercice", "canal": "email"},
            {"mois": 4, "jour": 30, "titre": "C3 — Rapport semestriel de surveillance (S2 N-1)", "canal": "email"},
        ]

        for echeance in echeances_cima:
            date_ech = datetime(annee, echeance["mois"], echeance["jour"], 17, 0, tzinfo=timezone.utc)
            if date_ech < maintenant:
                date_ech = date_ech.replace(year=annee + 1)

            jours_restants = (date_ech - maintenant).days

            # Rappels à 30j, 15j, 7j, 3j, 1j
            for jours_avant in [30, 15, 7, 3, 1]:
                if jours_restants <= jours_avant + 2:
                    date_rappel = date_ech - timedelta(days=jours_avant)
                    if date_rappel > maintenant:
                        for emp_id in employes_rh:
                            rappels.append(Rappel(
                                type_source="echeance_cima",
                                source_id=compagnie_id,
                                employe_id=emp_id,
                                message=f"📋 CIMA — {echeance['titre']} — dans {jours_avant} jour(s). Échéance : {date_ech.strftime('%d/%m/%Y')}.",
                                canal=echeance["canal"],
                                a_envoyer_le=date_rappel,
                            ))

        return rappels

    def rappels_sinistres_en_retard(
        self,
        sinistres: List[Dict],  # [{"id": 1, "numero": "S-001", "date_ouverture": ..., "gestionnaire_id": ..., "montant_estime": ...}]
        seuil_jours_cima: int = 40,  # alerte avant les 45j CIMA
    ) -> List[Rappel]:
        """
        Rappels pour les sinistres proches du délai de règlement CIMA (45 jours).
        Art. 12-ter : règlement dans 45 jours sinon pénalité taux légal × 1.5
        """
        rappels = []
        maintenant = datetime.now(timezone.utc)

        for s in sinistres:
            date_ouv = s.get("date_ouverture")
            if isinstance(date_ouv, str):
                try:
                    date_ouv = datetime.fromisoformat(date_ouv)
                except ValueError:
                    continue
            if not date_ouv:
                continue

            if date_ouv.tzinfo is None:
                date_ouv = date_ouv.replace(tzinfo=timezone.utc)

            jours_ecoules = (maintenant - date_ouv).days
            jours_restants = 45 - jours_ecoules

            if jours_restants <= seuil_jours_cima - 40:  # déjà dépassé
                message = (
                    f"🚨 DÉPASSEMENT CIMA — Sinistre {s.get('numero', s['id'])} "
                    f"({jours_ecoules} jours écoulés). Pénalité applicable (Art. 12-ter)."
                )
            elif jours_restants <= 5:
                message = (
                    f"⚠️ URGENT — Sinistre {s.get('numero', s['id'])} "
                    f"à régler SOUS {jours_restants} JOURS (délai CIMA Art. 12-ter)."
                )
            elif jours_restants <= 15:
                message = (
                    f"📋 Sinistre {s.get('numero', s['id'])} — "
                    f"{jours_restants} jours restants avant délai CIMA."
                )
            else:
                continue

            gestionnaire_id = s.get("gestionnaire_id")
            if gestionnaire_id:
                rappels.append(Rappel(
                    type_source="sinistre",
                    source_id=s["id"],
                    employe_id=gestionnaire_id,
                    message=message,
                    canal="push",
                    a_envoyer_le=maintenant + timedelta(minutes=5),
                ))

        return rappels


# ─────────────────────────────────────────────────────────────
# Gestionnaire d'agenda
# ─────────────────────────────────────────────────────────────

class GestionnaireAgenda:

    def __init__(self, generateur: Optional[GenerateurRappels] = None):
        self.generateur = generateur or GenerateurRappels()

    def vue_semaine(
        self,
        evenements: List[Dict],
        taches: List[Dict],
        debut_semaine: date,
    ) -> Dict[str, List]:
        """
        Organise événements et tâches par jour pour une vue hebdomadaire.
        Retourne un dict {date_str: [items]}.
        """
        vue: Dict[str, List] = {}
        for i in range(7):
            jour = debut_semaine + timedelta(days=i)
            vue[jour.isoformat()] = []

        for evt in evenements:
            date_debut = evt.get("date_debut")
            if isinstance(date_debut, str):
                try:
                    date_debut = datetime.fromisoformat(date_debut).date()
                except ValueError:
                    continue
            elif isinstance(date_debut, datetime):
                date_debut = date_debut.date()
            if isinstance(date_debut, date) and date_debut.isoformat() in vue:
                vue[date_debut.isoformat()].append({**evt, "_type": "evenement"})

        for tache in taches:
            date_ech = tache.get("date_echeance")
            if isinstance(date_ech, str):
                try:
                    date_ech = datetime.fromisoformat(date_ech).date()
                except ValueError:
                    continue
            elif isinstance(date_ech, datetime):
                date_ech = date_ech.date()
            if isinstance(date_ech, date) and date_ech.isoformat() in vue:
                vue[date_ech.isoformat()].append({**tache, "_type": "tache"})

        return vue

    def taches_urgentes(
        self,
        taches: List[Dict],
        jours_horizon: int = 7,
    ) -> List[Dict]:
        """Retourne les tâches urgentes/en retard dans les N prochains jours."""
        maintenant = datetime.now(timezone.utc)
        horizon = maintenant + timedelta(days=jours_horizon)
        urgentes = []

        for t in taches:
            if t.get("statut") in ("terminee", "annulee"):
                continue
            date_ech = t.get("date_echeance")
            if not date_ech:
                continue
            if isinstance(date_ech, str):
                try:
                    date_ech = datetime.fromisoformat(date_ech)
                except ValueError:
                    continue
            if date_ech.tzinfo is None:
                date_ech = date_ech.replace(tzinfo=timezone.utc)

            jours = (date_ech - maintenant).days
            if date_ech <= horizon or t.get("priorite") in ("haute", "urgente"):
                urgentes.append({
                    **t,
                    "_jours_restants": jours,
                    "_en_retard": date_ech < maintenant,
                    "_couleur": COULEURS_PRIORITE.get(t.get("priorite", "normale"), "#3B82F6"),
                })

        urgentes.sort(key=lambda x: (x["_en_retard"], -x.get("_jours_restants", 999)), reverse=False)
        return urgentes

    def resume_journalier(
        self,
        employe_id: int,
        evenements_jour: List[Dict],
        taches_jour: List[Dict],
        rappels_cima: Optional[List[Dict]] = None,
    ) -> str:
        """Génère un résumé textuel de la journée pour un employé."""
        lignes = [f"📅 Votre journée — {date.today().strftime('%A %d %B %Y')}"]

        if evenements_jour:
            lignes.append(f"\n🗓️ {len(evenements_jour)} événement(s) :")
            for e in evenements_jour[:5]:
                heure = ""
                if e.get("date_debut"):
                    try:
                        d = datetime.fromisoformat(str(e["date_debut"]))
                        heure = f" à {d.strftime('%H:%M')}"
                    except Exception:
                        pass
                lignes.append(f"  • {e.get('titre', '—')}{heure}")

        if taches_jour:
            urgentes = [t for t in taches_jour if t.get("priorite") in ("haute", "urgente")]
            lignes.append(f"\n✅ {len(taches_jour)} tâche(s) ({len(urgentes)} urgente(s)) :")
            for t in taches_jour[:5]:
                prio = "🔴 " if t.get("priorite") == "urgente" else ""
                lignes.append(f"  {prio}• {t.get('titre', '—')}")

        if rappels_cima:
            lignes.append(f"\n📋 {len(rappels_cima)} échéance(s) CIMA proche(s)")

        if not evenements_jour and not taches_jour:
            lignes.append("\nAucun événement prévu aujourd'hui. Bonne journée ! 🌟")

        return "\n".join(lignes)
