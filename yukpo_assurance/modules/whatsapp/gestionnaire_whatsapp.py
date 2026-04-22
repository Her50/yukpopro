"""
YukpoAssurance — Module WhatsApp Chatbot Clients
Chatbot conversationnel pour les clients finaux des compagnies d'assurance.

Fonctionnalités :
  - Calcul de devis (prime) instantané selon branche/garanties
  - Déclaration de sinistre par conversation
  - Suivi de sinistre en temps réel
  - Paiement de prime via Mobile Money
  - Envoi de documents (contrat, attestation, carte verte, quittance)
  - Renouvellement de contrat

Machine à états :
  accueil → {devis, sinistre, suivi, paiement, documents, renouvellement}

API supportées :
  - Meta Cloud API (WhatsApp Business) — recommandé
  - Twilio WhatsApp API — alternative
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger("yukpo_assurance.whatsapp")


# ─── Constantes ───────────────────────────────────────────────────────────────

MENU_PRINCIPAL = """
Bonjour ! 👋 Je suis l'assistant de votre compagnie d'assurance.

Comment puis-je vous aider ?

1️⃣  Obtenir un devis
2️⃣  Déclarer un sinistre
3️⃣  Suivre mon sinistre
4️⃣  Payer ma prime
5️⃣  Mes documents (contrat, attestation)
6️⃣  Renouveler mon contrat
0️⃣  Parler à un conseiller

Répondez par le numéro de votre choix.
"""

MENU_DEVIS_BRANCHE = """
Quelle assurance vous intéresse ?

1️⃣  Auto (voiture, moto)
2️⃣  Habitation (MRH)
3️⃣  Vie / Décès
4️⃣  Maladie / Accident corporel
5️⃣  Responsabilité Civile
6️⃣  Transport de marchandises
0️⃣  Retour au menu
"""

ETATS_VALIDES = [
    "accueil", "menu_devis", "devis_auto", "devis_mrh", "devis_vie",
    "devis_maladie", "sinistre_num_police", "sinistre_description",
    "sinistre_lieu", "sinistre_date", "sinistre_confirmation",
    "suivi_demande", "paiement_police", "paiement_montant", "paiement_confirmation",
    "docs_demande", "renouvellement_police", "attente_conseiller",
]

BRANCHES_MAP = {
    "1": "auto", "2": "mrh", "3": "vie", "4": "maladie", "5": "rc", "6": "transport",
    "auto": "auto", "voiture": "auto", "moto": "auto",
    "habitation": "mrh", "maison": "mrh", "mrh": "mrh",
    "vie": "vie", "deces": "vie", "décès": "vie",
}


# ─── Moteur de conversation ────────────────────────────────────────────────────

class MoteurConversationWhatsApp:
    """
    Traite les messages entrants WhatsApp et retourne la réponse appropriée.
    Maintient l'état de la conversation via SessionWhatsAppDB.
    """

    def __init__(self, compagnie_config: dict):
        """
        compagnie_config : infos de la compagnie (nom, logo, numéros utiles)
        """
        self.compagnie = compagnie_config
        self.nom_compagnie = compagnie_config.get("nom", "Votre assureur")

    async def traiter_message(
        self,
        numero: str,
        texte: str,
        session: dict,           # état courant (depuis SessionWhatsAppDB.contexte)
        db_session,              # AsyncSession SQLAlchemy
        compagnie_id: int,
    ) -> tuple[str, dict]:
        """
        Traite un message et retourne (réponse_texte, nouvel_etat).
        """
        texte_norm = texte.strip().lower()
        etat = session.get("etat", "accueil")
        contexte = session.get("contexte", {})

        # Commandes globales
        if texte_norm in ("0", "menu", "retour", "annuler", "cancel"):
            return MENU_PRINCIPAL, {"etat": "accueil", "contexte": {}}

        if texte_norm in ("aide", "help", "?"):
            return self._aide(), {"etat": etat, "contexte": contexte}

        # Dispatch selon l'état courant
        handlers = {
            "accueil":                self._handle_accueil,
            "menu_devis":             self._handle_menu_devis,
            "devis_auto":             self._handle_devis_auto,
            "devis_mrh":              self._handle_devis_mrh,
            "devis_vie":              self._handle_devis_vie,
            "sinistre_num_police":    self._handle_sinistre_police,
            "sinistre_description":   self._handle_sinistre_description,
            "sinistre_lieu":          self._handle_sinistre_lieu,
            "sinistre_date":          self._handle_sinistre_date,
            "sinistre_confirmation":  self._handle_sinistre_confirmation,
            "suivi_demande":          self._handle_suivi,
            "paiement_police":        self._handle_paiement_police,
            "paiement_montant":       self._handle_paiement_montant,
            "paiement_confirmation":  self._handle_paiement_confirmation,
            "docs_demande":           self._handle_docs,
            "renouvellement_police":  self._handle_renouvellement,
        }

        handler = handlers.get(etat, self._handle_accueil)
        reponse, nouvel_etat = await handler(texte_norm, texte, contexte, db_session, compagnie_id)
        return reponse, nouvel_etat

    # ─── Handlers ────────────────────────────────────────────────────────────

    async def _handle_accueil(self, texte_norm, texte_orig, contexte, db, cid):
        menu_map = {
            "1": ("menu_devis", MENU_DEVIS_BRANCHE),
            "2": ("sinistre_num_police", "📋 Veuillez indiquer votre *numéro de police* (ex: AUTO-2024-001234) :"),
            "3": ("suivi_demande", "🔍 Indiquez votre *numéro de sinistre* ou votre *numéro de police* :"),
            "4": ("paiement_police", "💳 Indiquez votre *numéro de police* pour lancer le paiement :"),
            "5": ("docs_demande", "📄 Indiquez votre *numéro de police* pour recevoir vos documents :"),
            "6": ("renouvellement_police", "🔄 Indiquez votre *numéro de police* à renouveler :"),
            "0": ("attente_conseiller", f"📞 Un conseiller de {self.nom_compagnie} va vous contacter sous peu.\n\nPour un contact direct : {self.compagnie.get('telephone', 'Voir nos coordonnées')}"),
        }
        if texte_norm in menu_map:
            etat, rep = menu_map[texte_norm]
            return rep, {"etat": etat, "contexte": {}}

        # Message non reconnu → afficher le menu
        return f"Bonjour 👋 Bienvenue chez *{self.nom_compagnie}*.\n" + MENU_PRINCIPAL, {"etat": "accueil", "contexte": {}}

    async def _handle_menu_devis(self, texte_norm, texte_orig, contexte, db, cid):
        branche = BRANCHES_MAP.get(texte_norm)
        if not branche:
            return "❌ Choix non reconnu.\n" + MENU_DEVIS_BRANCHE, {"etat": "menu_devis", "contexte": {}}

        etats_devis = {"auto": "devis_auto", "mrh": "devis_mrh", "vie": "devis_vie"}
        prochain_etat = etats_devis.get(branche, "devis_auto")

        questions = {
            "auto": "🚗 *Assurance automobile*\n\nQuel est l'*usage* de votre véhicule ?\n\n1️⃣  Véhicule particulier\n2️⃣  Taxi / Transport en commun\n3️⃣  Utilitaire / Livraison\n4️⃣  Moto",
            "mrh":  "🏠 *Assurance Habitation (MRH)*\n\nQuel est votre *type de logement* ?\n\n1️⃣  Appartement en location\n2️⃣  Maison en propriété\n3️⃣  Villa\n4️⃣  Bureau / Local commercial",
            "vie":  "🛡️ *Assurance Vie / Décès*\n\nQuel est votre *âge* ? (répondez en chiffres, ex: 35)",
        }
        return questions.get(branche, questions["auto"]), {"etat": prochain_etat, "contexte": {"branche": branche}}

    async def _handle_devis_auto(self, texte_norm, texte_orig, contexte, db, cid):
        usage_map = {"1": "particulier", "2": "taxi", "3": "utilitaire", "4": "moto",
                     "particulier": "particulier", "taxi": "taxi"}
        usage = usage_map.get(texte_norm, "particulier")
        contexte["usage_auto"] = usage

        if "cylindree" not in contexte:
            return (
                "🚗 Quelle est la *puissance fiscale* (cylindrée) du véhicule ?\n\n"
                "1️⃣  Moins de 6 CV (petite berline)\n"
                "2️⃣  6 à 10 CV (berline standard)\n"
                "3️⃣  11 à 14 CV (SUV, 4x4)\n"
                "4️⃣  Plus de 14 CV (véhicule de luxe)"
            ), {"etat": "devis_auto", "contexte": {**contexte, "etape": "cylindree"}}

        if contexte.get("etape") == "cylindree":
            cv_map = {"1": "inf_6", "2": "6_10", "3": "11_14", "4": "sup_14"}
            contexte["cylindree"] = cv_map.get(texte_norm, "6_10")
            return self._calculer_devis_auto(contexte), {"etat": "accueil", "contexte": {}}

        return (
            "🚗 Quelle est la *puissance fiscale* ?\n\n"
            "1️⃣  Moins de 6 CV\n2️⃣  6 à 10 CV\n3️⃣  11 à 14 CV\n4️⃣  Plus de 14 CV"
        ), {"etat": "devis_auto", "contexte": {**contexte, "etape": "cylindree"}}

    async def _handle_devis_mrh(self, texte_norm, texte_orig, contexte, db, cid):
        if "type_logement" not in contexte:
            type_map = {"1": "appartement", "2": "maison", "3": "villa", "4": "bureau"}
            contexte["type_logement"] = type_map.get(texte_norm, "appartement")
            return (
                "🏠 Quelle est la *valeur approximative de vos biens* (meubles + appareils) en FCFA ?\n\n"
                "1️⃣  Moins de 5 millions\n"
                "2️⃣  5 à 15 millions\n"
                "3️⃣  15 à 30 millions\n"
                "4️⃣  Plus de 30 millions"
            ), {"etat": "devis_mrh", "contexte": contexte}

        valeur_map = {"1": 3000000, "2": 10000000, "3": 22000000, "4": 40000000}
        valeur_biens = valeur_map.get(texte_norm, 10000000)
        prime_annuelle = round(valeur_biens * 0.0035)
        taxe = round(prime_annuelle * 0.15)
        prime_ttc = prime_annuelle + taxe

        return (
            f"✅ *Devis Assurance Habitation (MRH)*\n\n"
            f"Type de logement : {contexte.get('type_logement', 'appartement').capitalize()}\n"
            f"Valeur des biens : {valeur_biens:,.0f} FCFA\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Prime nette annuelle : *{prime_annuelle:,.0f} FCFA*\n"
            f"Taxes (15%) : {taxe:,.0f} FCFA\n"
            f"*Prime TTC : {prime_ttc:,.0f} FCFA/an*\n"
            f"Soit *{prime_ttc//12:,.0f} FCFA/mois*\n\n"
            f"Garanties incluses :\n"
            f"✓ Incendie & Explosion\n✓ Dégâts des eaux\n✓ Vol\n✓ RC locataire\n\n"
            f"Pour souscrire, tapez *1* ou contactez notre agence.\n"
            f"Retour au menu : tapez *0*"
        ), {"etat": "accueil", "contexte": {}}

    async def _handle_devis_vie(self, texte_norm, texte_orig, contexte, db, cid):
        try:
            age = int(texte_norm)
            if not 18 <= age <= 70:
                return "⚠️ L'âge doit être entre 18 et 70 ans. Indiquez votre âge :", {"etat": "devis_vie", "contexte": contexte}
        except ValueError:
            return "⚠️ Veuillez indiquer votre âge en chiffres (ex: 35) :", {"etat": "devis_vie", "contexte": contexte}

        if "capital" not in contexte:
            contexte["age"] = age
            return (
                f"🛡️ Très bien ! Quel *capital décès* souhaitez-vous ?\n\n"
                f"1️⃣  1 million FCFA\n"
                f"2️⃣  3 millions FCFA\n"
                f"3️⃣  5 millions FCFA\n"
                f"4️⃣  10 millions FCFA\n"
                f"5️⃣  Autre montant (tapez le montant)"
            ), {"etat": "devis_vie", "contexte": contexte}

        capitaux = {"1": 1000000, "2": 3000000, "3": 5000000, "4": 10000000}
        if texte_norm in capitaux:
            capital = capitaux[texte_norm]
        else:
            try:
                capital = int(texte_norm.replace(" ", "").replace(",", "").replace(".", ""))
            except ValueError:
                capital = 5000000

        age = contexte.get("age", 35)
        # Taux selon barème CIMA indicatif
        taux_pour_mille = {(18, 30): 2.5, (30, 40): 3.5, (40, 50): 6.0, (50, 60): 10.0, (60, 71): 15.0}
        taux = next((t for (a, b), t in taux_pour_mille.items() if a <= age < b), 10.0)
        prime_annuelle = round(capital * taux / 1000)

        return (
            f"✅ *Devis Assurance Vie / Temporaire Décès*\n\n"
            f"Âge : {age} ans\n"
            f"Capital décès garanti : *{capital:,.0f} FCFA*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"*Prime annuelle : {prime_annuelle:,.0f} FCFA*\n"
            f"Soit *{prime_annuelle//12:,.0f} FCFA/mois*\n\n"
            f"✓ En cas de décès, vos proches reçoivent {capital:,.0f} FCFA\n"
            f"✓ Contrat sur 10 ans renouvelable\n"
            f"✓ Exonéré de taxe (Art. 54 Code CIMA)\n\n"
            f"Pour souscrire, tapez *1*.\nRetour au menu : tapez *0*"
        ), {"etat": "accueil", "contexte": {}}

    async def _handle_sinistre_police(self, texte_norm, texte_orig, contexte, db, cid):
        contexte["numero_police"] = texte_orig.strip().upper()
        return (
            f"📋 Police *{contexte['numero_police']}* enregistrée.\n\n"
            f"Décrivez brièvement le *sinistre survenu* (nature, circonstances) :"
        ), {"etat": "sinistre_description", "contexte": contexte}

    async def _handle_sinistre_description(self, texte_norm, texte_orig, contexte, db, cid):
        contexte["description_sinistre"] = texte_orig.strip()
        return "📍 Quel est le *lieu du sinistre* (ville, quartier, adresse) ?", {"etat": "sinistre_lieu", "contexte": contexte}

    async def _handle_sinistre_lieu(self, texte_norm, texte_orig, contexte, db, cid):
        contexte["lieu_sinistre"] = texte_orig.strip()
        return "📅 Quelle est la *date du sinistre* ? (format JJ/MM/AAAA)", {"etat": "sinistre_date", "contexte": contexte}

    async def _handle_sinistre_date(self, texte_norm, texte_orig, contexte, db, cid):
        contexte["date_sinistre"] = texte_orig.strip()
        return (
            f"📋 *Récapitulatif de votre déclaration de sinistre :*\n\n"
            f"Police : {contexte.get('numero_police', 'N/A')}\n"
            f"Date : {contexte.get('date_sinistre', 'N/A')}\n"
            f"Lieu : {contexte.get('lieu_sinistre', 'N/A')}\n"
            f"Description : {contexte.get('description_sinistre', 'N/A')}\n\n"
            f"Confirmez-vous cette déclaration ?\n\n1️⃣  Oui, confirmer\n2️⃣  Non, recommencer"
        ), {"etat": "sinistre_confirmation", "contexte": contexte}

    async def _handle_sinistre_confirmation(self, texte_norm, texte_orig, contexte, db, cid):
        if texte_norm != "1":
            return "Déclaration annulée.\n" + MENU_PRINCIPAL, {"etat": "accueil", "contexte": {}}

        # Créer le sinistre en DB via l'ORM
        import random
        num_sin = f"SIN-{datetime.now().strftime('%Y')}-{random.randint(10000, 99999)}"

        try:
            from core.database import SessionWhatsAppDB
            from sqlalchemy import select
            # Stocker en log (le vrai insert se fait dans la route API)
        except Exception:
            pass

        return (
            f"✅ *Sinistre déclaré avec succès !*\n\n"
            f"🔖 Votre numéro de sinistre : *{num_sin}*\n\n"
            f"📱 Conservez ce numéro précieusement.\n\n"
            f"Prochaines étapes :\n"
            f"1. Un gestionnaire vous contactera sous *48h*\n"
            f"2. Rassemblez vos pièces justificatives\n"
            f"3. Suivez l'avancement en tapant *3* sur ce chat\n\n"
            f"Pour toute urgence : {self.compagnie.get('telephone', 'Contactez votre agence')}\n\n"
            f"Retour au menu : tapez *0*"
        ), {"etat": "accueil", "contexte": {"dernier_sin": num_sin}}

    async def _handle_suivi(self, texte_norm, texte_orig, contexte, db, cid):
        numero = texte_orig.strip().upper()
        try:
            from core.orass_connector import orass
            if numero.startswith("SIN"):
                sinistre = await orass.recuperer_sinistre(numero)
                if sinistre:
                    return (
                        f"📊 *Suivi sinistre {numero}*\n\n"
                        f"Statut : *{sinistre.statut.upper()}*\n"
                        f"Nature : {sinistre.nature}\n"
                        f"Expert assigné : {sinistre.expert_assigne or 'En attente'}\n"
                        f"Montant déclaré : {sinistre.montant_declare:,.0f} FCFA\n"
                        f"Montant expertise : {sinistre.montant_expertise or 'En cours'}\n\n"
                        f"Pour contacter votre gestionnaire : {self.compagnie.get('telephone', 'Voir agence')}\n\n"
                        f"Retour : tapez *0*"
                    ), {"etat": "accueil", "contexte": {}}
            else:
                contrat = await orass.rechercher_contrat(numero_police=numero)
                if contrat:
                    return (
                        f"📋 *Contrat {numero}*\n\n"
                        f"Assuré : {contrat.prenom_assure} {contrat.nom_assure}\n"
                        f"Branche : {contrat.branche.upper()}\n"
                        f"Statut : *{contrat.statut.upper()}*\n"
                        f"Validité : {contrat.date_effet} → {contrat.date_echeance}\n"
                        f"Prime TTC : {contrat.prime_ttc:,.0f} FCFA/an\n\n"
                        f"Retour : tapez *0*"
                    ), {"etat": "accueil", "contexte": {}}
        except Exception as e:
            logger.warning(f"[WA] Suivi erreur: {e}")

        return (
            f"🔍 Référence *{numero}* non trouvée.\n\n"
            f"Vérifiez le numéro ou contactez votre agence :\n"
            f"{self.compagnie.get('telephone', '')}\n\n"
            f"Retour : tapez *0*"
        ), {"etat": "accueil", "contexte": {}}

    async def _handle_paiement_police(self, texte_norm, texte_orig, contexte, db, cid):
        contexte["numero_police"] = texte_orig.strip().upper()
        try:
            from core.orass_connector import orass
            contrat = await orass.rechercher_contrat(numero_police=contexte["numero_police"])
            if contrat:
                contexte["prime_ttc"] = contrat.prime_ttc
                return (
                    f"💳 *Paiement de prime*\n\n"
                    f"Police : {contrat.numero_police}\n"
                    f"Assuré : {contrat.prenom_assure} {contrat.nom_assure}\n"
                    f"Montant dû : *{contrat.prime_ttc:,.0f} FCFA*\n\n"
                    f"Confirmer le paiement de *{contrat.prime_ttc:,.0f} FCFA* ?\n\n"
                    f"1️⃣  Oui, payer via Mobile Money\n"
                    f"2️⃣  Non, annuler"
                ), {"etat": "paiement_confirmation", "contexte": contexte}
        except Exception:
            pass

        return (
            f"Quel est le *montant à payer* (en FCFA) ?"
        ), {"etat": "paiement_montant", "contexte": contexte}

    async def _handle_paiement_montant(self, texte_norm, texte_orig, contexte, db, cid):
        try:
            montant = float(texte_norm.replace(" ", "").replace(",", ""))
            contexte["prime_ttc"] = montant
        except ValueError:
            return "⚠️ Montant invalide. Indiquez le montant en chiffres :", {"etat": "paiement_montant", "contexte": contexte}

        return (
            f"💳 Paiement de *{contexte['prime_ttc']:,.0f} FCFA*\n\n"
            f"Confirmer ?\n1️⃣  Oui\n2️⃣  Non"
        ), {"etat": "paiement_confirmation", "contexte": contexte}

    async def _handle_paiement_confirmation(self, texte_norm, texte_orig, contexte, db, cid):
        if texte_norm != "1":
            return "Paiement annulé.\n" + MENU_PRINCIPAL, {"etat": "accueil", "contexte": {}}

        montant = contexte.get("prime_ttc", 0)
        police = contexte.get("numero_police", "N/A")
        import random, uuid
        ref_paiement = f"PAY-{uuid.uuid4().hex[:8].upper()}"

        # Génération lien paiement Mobile Money (CinetPay dans l'implémentation réelle)
        return (
            f"✅ *Paiement initié*\n\n"
            f"Référence : *{ref_paiement}*\n"
            f"Police : {police}\n"
            f"Montant : *{montant:,.0f} FCFA*\n\n"
            f"📱 Choisissez votre mode de paiement :\n\n"
            f"🟡 MTN Mobile Money : *#126# → Paiement marchand*\n"
            f"🟠 Orange Money : *#150# → Paiement marchand*\n"
            f"🔵 CinetPay : Lien envoyé par SMS\n\n"
            f"Code marchand : *{self.compagnie.get('code_marchand', 'YUKPO001')}*\n"
            f"Référence : *{ref_paiement}*\n\n"
            f"⚠️ Après paiement, envoyez votre *reçu de transaction* pour validation.\n\n"
            f"Retour : tapez *0*"
        ), {"etat": "accueil", "contexte": {"ref_paiement": ref_paiement}}

    async def _handle_docs(self, texte_norm, texte_orig, contexte, db, cid):
        police = texte_orig.strip().upper()
        try:
            from core.orass_connector import orass
            contrat = await orass.rechercher_contrat(numero_police=police)
            if contrat:
                return (
                    f"📄 *Documents disponibles pour {police}*\n\n"
                    f"Tapez le numéro du document souhaité :\n\n"
                    f"1️⃣  Attestation d'assurance\n"
                    f"2️⃣  Carte verte (voyage international)\n"
                    f"3️⃣  Conditions particulières (contrat)\n"
                    f"4️⃣  Dernière quittance de prime\n\n"
                    f"_Les documents seront envoyés par WhatsApp en quelques secondes._\n\n"
                    f"Retour : tapez *0*"
                ), {"etat": "accueil", "contexte": {"police_docs": police}}
        except Exception:
            pass
        return (
            f"❌ Police *{police}* non trouvée. Vérifiez le numéro.\nRetour : tapez *0*"
        ), {"etat": "accueil", "contexte": {}}

    async def _handle_renouvellement(self, texte_norm, texte_orig, contexte, db, cid):
        police = texte_orig.strip().upper()
        return (
            f"🔄 *Renouvellement police {police}*\n\n"
            f"Votre demande de renouvellement a été enregistrée.\n\n"
            f"Un conseiller vous contactera sous *24h* pour :\n"
            f"✓ Confirmer les conditions\n"
            f"✓ Vous communiquer la prime de renouvellement\n"
            f"✓ Procéder au paiement\n\n"
            f"Pour toute urgence : {self.compagnie.get('telephone', 'Contactez votre agence')}\n\n"
            f"Retour : tapez *0*"
        ), {"etat": "accueil", "contexte": {}}

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _calculer_devis_auto(self, contexte: dict) -> str:
        usage = contexte.get("usage_auto", "particulier")
        cylindree = contexte.get("cylindree", "6_10")

        primes = {
            ("particulier", "inf_6"):   {"min": 75000,  "moy": 95000},
            ("particulier", "6_10"):    {"min": 90000,  "moy": 130000},
            ("particulier", "11_14"):   {"min": 120000, "moy": 175000},
            ("particulier", "sup_14"):  {"min": 160000, "moy": 250000},
            ("taxi",        "6_10"):    {"min": 150000, "moy": 220000},
            ("utilitaire",  "6_10"):    {"min": 120000, "moy": 180000},
            ("moto",        "inf_6"):   {"min": 35000,  "moy": 55000},
        }
        tarif = primes.get((usage, cylindree), {"min": 90000, "moy": 130000})
        prime_nette = tarif["moy"]
        taxe = round(prime_nette * 0.15)
        prime_ttc = prime_nette + taxe

        return (
            f"✅ *Devis Assurance Auto (RC + Garanties de base)*\n\n"
            f"Usage : {usage.capitalize()}\n"
            f"Cylindrée : {cylindree.replace('_', ' ').replace('inf', '<').replace('sup', '>')} CV\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Prime RC obligatoire : {prime_nette:,.0f} FCFA\n"
            f"Taxe (15%) : {taxe:,.0f} FCFA\n"
            f"*Prime TTC : {prime_ttc:,.0f} FCFA/an*\n\n"
            f"Options disponibles :\n"
            f"+ Bris de glace : +15 000 FCFA\n"
            f"+ Vol/Incendie : +25 000 FCFA\n"
            f"+ Tous risques : +50 000 à 80 000 FCFA\n\n"
            f"Base légale : Art. 200 Code CIMA — RC obligatoire\n\n"
            f"Pour souscrire : contactez notre agence\n"
            f"{self.compagnie.get('telephone', '')}\n\n"
            f"Retour au menu : tapez *0*"
        )

    def _aide(self) -> str:
        return (
            f"ℹ️ *Aide — {self.nom_compagnie}*\n\n"
            f"Commandes utiles :\n"
            f"• *0* ou *menu* : retour au menu principal\n"
            f"• *1* : obtenir un devis\n"
            f"• *2* : déclarer un sinistre\n"
            f"• *3* : suivre un sinistre\n"
            f"• *4* : payer une prime\n"
            f"• *5* : mes documents\n\n"
            f"Assistance : {self.compagnie.get('telephone', 'Contactez votre agence')}\n"
            f"Horaires : Lun-Ven 8h-17h"
        )


# ─── Client API Meta WhatsApp Business Cloud ─────────────────────────────────

class ClientWhatsAppMeta:
    """
    Client HTTP pour l'API Meta WhatsApp Business Cloud.
    Permet d'envoyer messages texte, documents, et messages avec boutons.
    """

    BASE_URL = "https://graph.facebook.com/v19.0"

    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def envoyer_texte(self, to: str, texte: str) -> dict:
        """Envoie un message texte simple."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": texte},
        }
        return await self._post(payload)

    async def envoyer_document(self, to: str, url_doc: str, nom_fichier: str, legende: str = "") -> dict:
        """Envoie un document PDF ou autre."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "document",
            "document": {"link": url_doc, "caption": legende, "filename": nom_fichier},
        }
        return await self._post(payload)

    async def envoyer_boutons(self, to: str, corps: str, boutons: list[dict]) -> dict:
        """
        Envoie un message avec boutons interactifs (max 3).
        boutons = [{"id": "btn_1", "title": "Oui"}]
        """
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": corps},
                "action": {"buttons": [{"type": "reply", "reply": b} for b in boutons[:3]]},
            },
        }
        return await self._post(payload)

    async def envoyer_liste(self, to: str, corps: str, bouton_label: str, sections: list[dict]) -> dict:
        """Envoie un message avec liste de choix (menu)."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": corps},
                "action": {"button": bouton_label, "sections": sections},
            },
        }
        return await self._post(payload)

    async def marquer_lu(self, message_id: str) -> dict:
        """Marque un message comme lu."""
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        return await self._post(payload)

    async def _post(self, payload: dict) -> dict:
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload, headers=self._headers)
            if resp.status_code not in (200, 201):
                logger.error(f"[WhatsApp API] Erreur {resp.status_code}: {resp.text}")
            return resp.json()


def verifier_signature_meta(payload_bytes: bytes, signature_header: str, app_secret: str) -> bool:
    """Vérifie la signature HMAC-SHA256 du webhook Meta."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        app_secret.encode(), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature_header, expected)
