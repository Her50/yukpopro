"""
ProfilProfessionnel — Modèle SQLAlchemy + service CRUD.

Table `profils_pro` : un profil par utilisateur (relation 1-1 avec `utilisateurs`).
Stocke le contexte métier de chaque professionnel pour personnaliser les agents IA.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from core.database import Base

logger = logging.getLogger("yukpo_assurance.pro.profil")


# ══════════════════════════════════════════════════════════════════════════════
# Modèle SQLAlchemy
# ══════════════════════════════════════════════════════════════════════════════

class ProfilProfessionnelDB(Base):
    """
    Profil métier d'un utilisateur de la plateforme Pro.

    Champs clés :
      - metier         : "comptable" | "DRH" | "DAF" | "juriste" | "ingenieur" | …
      - pays           : "CM" | "CI" | "SN" | … (pays d'exercice)
      - secteur        : "prive" | "public" | "ngo" | "independant"
      - niveau         : "junior" | "senior" | "expert" | "dirigeant"
      - preferences    : JSON libre (thème, langue réponse, format préféré…)
      - stats_usage    : JSON compteurs (nb_rapports, nb_slides, nb_requetes_rag…)
      - badges         : JSON liste de badges gagnés (gamification)
    """
    __tablename__ = "profils_pro"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_profil_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Lien vers l'utilisateur (clé étrangère logique — pas de FK pour rester
    # compatible SQLite dev sans migration stricte)
    user_id = Column(Integer, nullable=False, index=True)

    # ── Identité professionnelle ──────────────────────────────────────────
    metier = Column(String(80), nullable=False, default="professionnel")
    # Sous-spécialité libre : "expert-comptable SYSCOHADA", "DRH grands comptes", …
    specialite = Column(String(150), nullable=True)
    pays = Column(String(5), nullable=False, default="CM")
    zone = Column(String(30), nullable=True)          # "OHADA" | "UEMOA" | "CEMAC"
    secteur = Column(String(40), nullable=False, default="prive")
    niveau = Column(String(30), nullable=False, default="senior")

    # ── Contexte employeur ────────────────────────────────────────────────
    entreprise = Column(String(200), nullable=True)
    taille_entreprise = Column(String(30), nullable=True)  # "tpe" | "pme" | "grande"
    secteur_activite = Column(String(100), nullable=True)  # secteur économique

    # ── Préférences IA ────────────────────────────────────────────────────
    langue_reponse = Column(String(10), nullable=False, default="fr")
    style_reponse = Column(String(30), nullable=False, default="professionnel")
    # "professionnel" | "didactique" | "direct" | "vulgarise"
    format_prefere = Column(String(30), nullable=False, default="standard")
    # "flash" | "standard" | "complet" (pour rapports, slides)

    # ── Préférences libres (JSON) ─────────────────────────────────────────
    preferences = Column(JSON, default=dict)
    # Ex : {"recevoir_alertes_reglementaires": true, "fuseau": "Africa/Douala"}

    # ── Statistiques d'usage ──────────────────────────────────────────────
    stats_usage = Column(JSON, default=dict)
    # Ex : {"nb_rapports": 12, "nb_slides": 5, "nb_requetes_rag": 87,
    #        "nb_analyses_data": 3, "nb_requetes_agent": 150}

    # ── Gamification ─────────────────────────────────────────────────────
    badges = Column(JSON, default=list)
    # Ex : ["premier_rapport", "expert_cgi", "100_requetes"]
    points_xp = Column(Integer, default=0, nullable=False)
    niveau_xp = Column(String(30), nullable=False, default="debutant")
    # "debutant" | "initie" | "confirme" | "expert" | "maitre"

    # ── Mémoire personnelle de l'agent ────────────────────────────────────
    # Faits persistants que l'agent doit retenir entre les sessions
    memoire_agent = Column(JSON, default=list)
    # Ex : [{"fait": "L'entreprise utilise SAGE 100", "date": "2025-01-15"},
    #        {"fait": "Clôture exercice en mars", "date": "2025-01-20"}]

    # ── Données comptables/financières contextuelles ──────────────────────
    # Exercice fiscal en cours, logiciel comptable utilisé, etc.
    contexte_metier = Column(JSON, default=dict)
    # Ex : {"logiciel_compta": "SAGE 100", "exercice": "2024",
    #        "plan_comptable": "SYSCOHADA", "nb_employes": 45}

    # ── CV et recherche d'emploi ──────────────────────────────────────────
    # Texte du CV stocké (extrait d'un upload ou saisi manuellement)
    cv_texte = Column(Text, nullable=True)
    # Chemin du dernier fichier CV uploadé (relatif à /data/)
    cv_fichier_chemin = Column(String(300), nullable=True)
    # Description libre : poste recherché, secteur, localisation, prétentions
    profil_recherche_emploi = Column(Text, nullable=True)
    # Activation de la veille automatique
    recherche_emploi_active = Column(Boolean, default=False, nullable=False)
    # Fréquence en heures (défaut : 24h)
    frequence_recherche_heures = Column(Integer, default=24, nullable=False)
    # Dernière exécution de la veille automatique
    derniere_recherche_emploi = Column(DateTime, nullable=True)
    # Offres trouvées lors de la dernière veille (JSON list, max 20)
    offres_emploi_recentes = Column(JSON, default=list)

    # ── Marchés publics ───────────────────────────────────────────────────
    marches_publics_recents = Column(JSON, nullable=True, default=list)
    derniere_recherche_marches = Column(DateTime, nullable=True)

    # ── Abonnement / accès ────────────────────────────────────────────────
    abonnement = Column(String(30), nullable=False, default="freemium")
    # "freemium" | "pro" | "enterprise"
    actif = Column(Boolean, default=True, nullable=False)

    # ── Timestamps ────────────────────────────────────────────────────────
    cree_le = Column(DateTime, default=datetime.utcnow, nullable=False)
    modifie_le = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    derniere_activite = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<ProfilPro id={self.id} user={self.user_id} metier={self.metier} pays={self.pays}>"

    def to_dict(self) -> dict:
        """Sérialisation complète pour les réponses API."""
        return {
            "id":                self.id,
            "user_id":           self.user_id,
            "metier":            self.metier,
            "specialite":        self.specialite,
            "pays":              self.pays,
            "zone":              self.zone,
            # secteur = secteur_activite pour le frontend (ex: "finance_banque")
            "secteur":           self.secteur_activite or "",
            "secteur_type":      self.secteur,        # "prive|public|ngo" (usage interne)
            "secteur_activite":  self.secteur_activite,
            "niveau":            self.niveau,
            "niveau_expertise":  self.niveau,         # alias frontend
            "niveau_experience": self.niveau,         # alias mobile
            "bio":               (self.preferences or {}).get("bio"),
            "annees_experience": (self.preferences or {}).get("annees_experience"),
            "entreprise":        self.entreprise,
            "taille_entreprise": self.taille_entreprise,
            "langue_reponse":    self.langue_reponse,
            "style_reponse":     self.style_reponse,
            "format_prefere":    self.format_prefere,
            "preferences":       self.preferences or {},
            "stats_usage":       self.stats_usage or {},
            "badges":            self.badges or [],
            "points_xp":         self.points_xp,
            "xp_points":         self.points_xp,        # alias frontend
            "niveau_xp":         self.niveau_xp,
            "niveau_pro":        self.niveau_xp,        # alias frontend
            # Compteurs usage (depuis stats_usage JSON)
            "nb_requetes_copilote": (self.stats_usage or {}).get("nb_requetes_copilote", 0),
            "nb_requetes_agent":    (self.stats_usage or {}).get("nb_requetes_agent", 0),
            "nb_requetes_rag":      (self.stats_usage or {}).get("nb_requetes_rag", 0),
            "nb_rapports_generes":  (self.stats_usage or {}).get("nb_rapports", 0),
            "nb_slides_generes":    (self.stats_usage or {}).get("nb_slides", 0),
            "nb_traductions":       (self.stats_usage or {}).get("nb_traductions", 0),
            "memoire_agent":     self.memoire_agent or [],
            "contexte_metier":   self.contexte_metier or {},
            "abonnement":                  self.abonnement,
            "actif":                       self.actif,
            # CV & emploi
            "cv_disponible":               bool(self.cv_texte or self.cv_fichier_chemin),
            "cv_texte_extrait":            bool(self.cv_texte),
            "profil_recherche_emploi":     self.profil_recherche_emploi,
            "recherche_emploi_active":     self.recherche_emploi_active,
            "frequence_recherche_heures":  self.frequence_recherche_heures,
            "derniere_recherche_emploi":   self.derniere_recherche_emploi.isoformat() if self.derniere_recherche_emploi else None,
            "offres_emploi_recentes":      self.offres_emploi_recentes or [],
            "marches_publics_recents":     self.marches_publics_recents or [],
            "derniere_recherche_marches":  self.derniere_recherche_marches.isoformat() if self.derniere_recherche_marches else None,
            # Timestamps
            "cree_le":                     self.cree_le.isoformat() if self.cree_le else None,
            "modifie_le":                  self.modifie_le.isoformat() if self.modifie_le else None,
            "derniere_activite":           self.derniere_activite.isoformat() if self.derniere_activite else None,
        }

    def to_contexte_agent(self) -> str:
        """
        Résumé du profil formaté pour injection dans le system prompt d'un agent.
        Compact et orienté métier.
        """
        lignes = [
            f"PROFIL PROFESSIONNEL :",
            f"  Métier       : {self.metier}" + (f" — {self.specialite}" if self.specialite else ""),
            f"  Pays         : {self.pays}" + (f" / Zone {self.zone}" if self.zone else ""),
            f"  Secteur      : {self.secteur} | Niveau : {self.niveau}",
        ]
        if self.entreprise:
            lignes.append(f"  Entreprise   : {self.entreprise}" +
                          (f" ({self.taille_entreprise})" if self.taille_entreprise else ""))
        if self.contexte_metier:
            ctx = self.contexte_metier
            if ctx.get("logiciel_compta"):
                lignes.append(f"  Logiciel     : {ctx['logiciel_compta']}")
            if ctx.get("plan_comptable"):
                lignes.append(f"  Plan comptable: {ctx['plan_comptable']}")
            if ctx.get("exercice"):
                lignes.append(f"  Exercice     : {ctx['exercice']}")
            if ctx.get("nb_employes"):
                lignes.append(f"  Effectif     : {ctx['nb_employes']} employés")
        if self.memoire_agent:
            lignes.append("  Mémoire :")
            for m in self.memoire_agent[-5:]:  # 5 derniers faits uniquement
                lignes.append(f"    - {m.get('fait', m)}")
        lignes.append(f"  Style réponse: {self.style_reponse} | Format: {self.format_prefere}")
        return "\n".join(lignes)
