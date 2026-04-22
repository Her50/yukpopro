"""
YukpoAssurance — DossierContexte
Accès intelligent au contexte d'un dossier depuis le chat.

Fonctionnement :
1. Détecte automatiquement les numéros de référence dans le message
   (SIN-2025-001, AUTO-2024-001234, REU-xxx...)
2. Charge les données depuis ORASS (sinistre, contrat assuré, historique)
3. Génère un résumé IA compact du dossier
4. Injecte le contexte enrichi dans le prompt du chat IA

→ L'IA peut ainsi rédiger une lettre personnalisée, analyser un dossier,
  proposer des actions, sans que l'employé ait besoin de tout recopier.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orass_connector import orass

logger = logging.getLogger("yukpo_assurance.dossiers.contexte")


@dataclass
class ContexteDossier:
    """Contexte enrichi d'un dossier, prêt à être injecté dans un prompt IA"""
    reference: str
    type_dossier: str               # "sinistre" | "contrat" | "reunion"
    resume_ia: str                  # Résumé compact généré par IA (4-5 points)
    donnees_brutes: dict            # Toutes les données brutes du dossier
    historique: list[dict] = field(default_factory=list)
    pieces_jointes: list[str] = field(default_factory=list)
    contacts: dict = field(default_factory=dict)  # coordonnées assuré/courtier


class DossierContexteService:
    """
    Service d'enrichissement contextuel automatique pour le chat.

    Usage depuis le chat :
        contexte = await dossier_contexte_service.extraire_contexte(message)
        if contexte:
            system_prompt += dossier_contexte_service.formater_pour_prompt(contexte)
    """

    # ── Patterns de détection des références ──────────────────────────────────
    PATTERNS = [
        ("sinistre", r'\b(SIN-\d{4}-\d{4,6})\b'),
        ("contrat",  r'\b([A-Z]{2,6}-\d{4}-\d{5,8})\b'),
        ("reunion",  r'\b(REU-[A-Z0-9-]{5,20})\b'),
    ]
    # Numéro générique : "dossier n°12345" ou "sinistre 12345"
    PATTERN_GENERIC = r'\b(?:dossier|sinistre|police|contrat)\s+(?:n°?\s*)?(\d{4,8})\b'

    # ── Point d'entrée ────────────────────────────────────────────────────────

    async def extraire_contexte(self, message: str) -> Optional[ContexteDossier]:
        """
        Détecte une référence de dossier dans le message et charge les données.
        Retourne None si aucune référence trouvée.
        """
        msg_upper = message.upper()

        # 1. Patterns spécifiques (SIN-YYYY-XXXXXX, AUTO-YYYY-XXXXXX...)
        for type_dossier, pattern in self.PATTERNS:
            match = re.search(pattern, msg_upper)
            if match:
                reference = match.group(1)
                logger.info(f"[DossierCtx] Référence détectée : {type_dossier} {reference}")
                return await self._charger(reference, type_dossier)

        # 2. Numéro générique (fallback)
        match = re.search(self.PATTERN_GENERIC, message, re.IGNORECASE)
        if match:
            num = match.group(1)
            # Essaye sinistre en premier
            contexte = await self._charger(f"SIN-2025-{num}", "sinistre")
            if contexte:
                return contexte
            return await self._charger(f"AUTO-2024-{num}", "contrat")

        return None

    # ── Chargement par type ───────────────────────────────────────────────────

    async def _charger(self, reference: str, type_dossier: str) -> Optional[ContexteDossier]:
        try:
            if type_dossier == "sinistre":
                return await self._charger_sinistre(reference)
            elif type_dossier == "contrat":
                return await self._charger_contrat(reference)
            else:
                return None
        except Exception as e:
            logger.warning(f"[DossierCtx] Erreur chargement {reference}: {e}")
            return None

    async def _charger_sinistre(self, numero_sinistre: str) -> Optional[ContexteDossier]:
        """Charge un sinistre et le contrat associé depuis ORASS"""
        sinistre = await orass.recuperer_sinistre(numero_sinistre)
        if not sinistre:
            return None

        contrat = await orass.rechercher_contrat(numero_police=sinistre.numero_police)

        donnees = {
            "sinistre": {
                "numero": sinistre.numero_sinistre,
                "police": sinistre.numero_police,
                "date_sinistre": str(sinistre.date_sinistre),
                "date_declaration": str(sinistre.date_declaration),
                "nature": sinistre.nature,
                "lieu": sinistre.lieu,
                "description": sinistre.description,
                "statut": sinistre.statut,
                "montant_declare_fcfa": sinistre.montant_declare,
                "montant_expertisé_fcfa": sinistre.montant_expertise,
                "montant_réglé_fcfa": sinistre.montant_regle,
                "expert_assigné": sinistre.expert_assigne,
                "gestionnaire": sinistre.gestionnaire_code,
                "pieces_fournies": sinistre.pieces_fournies,
            },
            "assure": {
                "nom_complet": f"{contrat.nom_assure} {contrat.prenom_assure}" if contrat else "N/A",
                "telephone": contrat.telephone if contrat else "N/A",
                "email": contrat.email if contrat else "N/A",
                "adresse": contrat.adresse if contrat else "N/A",
                "immatriculation": contrat.immatriculation if contrat else "N/A",
                "branche": contrat.branche if contrat else "N/A",
            } if contrat else {},
        }

        contacts = {
            "nom": f"{contrat.nom_assure} {contrat.prenom_assure}" if contrat else "",
            "adresse": contrat.adresse if contrat else "",
            "telephone": contrat.telephone if contrat else "",
            "email": contrat.email if contrat else "",
        }

        resume = await self._resume_sinistre(donnees)

        return ContexteDossier(
            reference=numero_sinistre,
            type_dossier="sinistre",
            resume_ia=resume,
            donnees_brutes=donnees,
            historique=sinistre.historique,
            pieces_jointes=sinistre.pieces_fournies,
            contacts=contacts,
        )

    async def _charger_contrat(self, numero_police: str) -> Optional[ContexteDossier]:
        """Charge un contrat et ses sinistres antérieurs"""
        contrat = await orass.rechercher_contrat(numero_police=numero_police)
        if not contrat:
            return None

        sinistres = await orass.lister_sinistres_par_police(numero_police)
        validite = await orass.verifier_validite_contrat(numero_police)

        donnees = {
            "contrat": {
                "numero_police": contrat.numero_police,
                "assure": f"{contrat.nom_assure} {contrat.prenom_assure}",
                "telephone": contrat.telephone,
                "email": contrat.email,
                "adresse": contrat.adresse,
                "branche": contrat.branche,
                "statut": contrat.statut,
                "date_effet": str(contrat.date_effet),
                "date_echeance": str(contrat.date_echeance),
                "prime_nette_fcfa": contrat.prime_nette,
                "prime_ttc_fcfa": contrat.prime_ttc,
                "immatriculation": contrat.immatriculation,
                "courtier": contrat.courtier_code,
            },
            "validite": validite,
            "nb_sinistres_anterieurs": len(sinistres),
            "dernier_sinistre": sinistres[0].numero_sinistre if sinistres else None,
        }

        contacts = {
            "nom": f"{contrat.nom_assure} {contrat.prenom_assure}",
            "adresse": contrat.adresse,
            "telephone": contrat.telephone,
            "email": contrat.email or "",
        }

        resume = await self._resume_contrat(donnees)

        return ContexteDossier(
            reference=numero_police,
            type_dossier="contrat",
            resume_ia=resume,
            donnees_brutes=donnees,
            contacts=contacts,
        )

    # ── Résumés IA ────────────────────────────────────────────────────────────

    async def _resume_sinistre(self, donnees: dict) -> str:
        sinistre = donnees.get("sinistre", {})
        assure = donnees.get("assure", {})
        prompt = f"""Tu es assistant IA dans une compagnie d'assurance.
Résume ce dossier sinistre en 5 points clés pour un employé qui doit agir rapidement :

SINISTRE : {sinistre}
ASSURÉ : {assure}

Format OBLIGATOIRE (5 lignes max) :
• Assuré : [nom] | [tel] | [email]
• Sinistre : [nature] le [date] à [lieu]
• Statut : [statut actuel] | Expert : [nom]
• Montants : Déclaré [X] FCFA → Expertisé [X] FCFA → Réglé [X] FCFA
• Attention : [pièces manquantes / délais / actions urgentes]"""

        try:
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.COPILOTE)
            return rep.contenu
        except Exception:
            # Fallback texte simple si IA indisponible
            return (
                f"• Assuré : {assure.get('nom_complet', 'N/A')} | {assure.get('telephone', '')}\n"
                f"• Sinistre : {sinistre.get('nature', '?')} le {sinistre.get('date_sinistre', '?')}\n"
                f"• Statut : {sinistre.get('statut', '?')}\n"
                f"• Montant déclaré : {sinistre.get('montant_declare_fcfa', 0):,} FCFA\n"
                f"• Pièces : {', '.join(sinistre.get('pieces_fournies', []))}"
            )

    async def _resume_contrat(self, donnees: dict) -> str:
        contrat = donnees.get("contrat", {})
        prompt = f"""Résume ce contrat d'assurance en 5 points pour un employé :

CONTRAT : {contrat}
SINISTRES ANTÉRIEURS : {donnees.get('nb_sinistres_anterieurs', 0)}

Format (5 lignes max) :
• Assuré : [nom] | [tel] | [email]
• Garanties : [branche] | [statut] | [date effet → date écheance]
• Véhicule : [immatriculation] si branche auto
• Situation : [statut validité] | Prime TTC : [montant] FCFA
• Sinistres : [nb] dossiers antérieurs"""

        try:
            rep = await ia_client.appeler(prompt=prompt, mode=ModeIA.COPILOTE)
            return rep.contenu
        except Exception:
            return (
                f"• Assuré : {contrat.get('assure', 'N/A')} | {contrat.get('telephone', '')}\n"
                f"• Police : {contrat.get('numero_police', '?')} | {contrat.get('branche', '?').upper()}\n"
                f"• Statut : {contrat.get('statut', '?')}\n"
                f"• Validité : {contrat.get('date_effet', '?')} → {contrat.get('date_echeance', '?')}\n"
                f"• Prime TTC : {contrat.get('prime_ttc_fcfa', 0):,} FCFA"
            )

    # ── Formatage pour injection dans le prompt ───────────────────────────────

    def formater_pour_prompt(self, contexte: ContexteDossier) -> str:
        """
        Formate le contexte en bloc textuel prêt à être injecté dans le
        system prompt du chat. Inclut toutes les données nécessaires pour
        que l'IA puisse rédiger une lettre ou analyser le dossier sans
        demander d'informations supplémentaires.
        """
        hist_str = ""
        if contexte.historique:
            lignes = [
                f"  • {h.get('date', '?')} : {h.get('action', '?')} "
                f"[{h.get('auteur', 'système')}]"
                for h in contexte.historique[-10:]  # 10 derniers événements
            ]
            hist_str = "\nHISTORIQUE :\n" + "\n".join(lignes)

        pieces_str = ""
        if contexte.pieces_jointes:
            pieces_str = f"\nPIÈCES FOURNIES : {', '.join(contexte.pieces_jointes)}"

        contacts_str = ""
        if contexte.contacts:
            c = contexte.contacts
            contacts_str = (
                f"\nCOORDONNÉES COMPLÈTES :\n"
                f"  Nom : {c.get('nom', 'N/A')}\n"
                f"  Adresse : {c.get('adresse', 'N/A')}\n"
                f"  Téléphone : {c.get('telephone', 'N/A')}\n"
                f"  Email : {c.get('email', 'N/A')}"
            )

        return (
            f"\n\n{'═' * 60}\n"
            f"CONTEXTE DOSSIER CHARGÉ AUTOMATIQUEMENT\n"
            f"Type : {contexte.type_dossier.upper()} | Référence : {contexte.reference}\n"
            f"{'─' * 60}\n"
            f"RÉSUMÉ :\n{contexte.resume_ia}"
            f"{contacts_str}"
            f"{hist_str}"
            f"{pieces_str}\n"
            f"{'═' * 60}\n\n"
            "IMPORTANT : Tu as accès à toutes ces informations. Utilise-les "
            "directement pour répondre sans demander à l'employé de les "
            "resaisir. Pour une lettre, utilise les coordonnées exactes ci-dessus."
        )


# Singleton
dossier_contexte_service = DossierContexteService()
