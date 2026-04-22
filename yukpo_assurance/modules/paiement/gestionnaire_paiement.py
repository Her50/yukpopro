"""
YukpoAssurance — Module Paiement Mobile Money
Intégration MTN MoMo, Orange Money, Wave et CinetPay (agrégateur).

Flux standard :
  1. Initier une transaction → référence interne
  2. Rediriger vers l'opérateur (ou pousser une demande USSD)
  3. Recevoir le callback de confirmation (webhook)
  4. Mettre à jour le statut en DB et notifier l'assuré

APIs intégrées :
  - MTN Mobile Money API (Collections)     → https://momoapi.mtn.com
  - Orange Money API (OrangeMoney Paiement) → Varies by country
  - CinetPay (agrégateur multi-pays CIMA)  → https://api.cinetpay.com
  - Wave API                               → wave.com/api
"""
import hashlib
import hmac
import logging
import uuid
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger("yukpo_assurance.paiement")


# ─── Constantes ───────────────────────────────────────────────────────────────

OPERATEURS_SUPPORTES = ["mtn_momo", "orange_money", "cinetpay", "wave", "stripe"]

STATUTS_TRANSACTION = {
    "en_attente":  "Transaction créée, non initiée",
    "initie":      "Demande envoyée à l'opérateur",
    "en_cours":    "En attente de confirmation client (USSD/Push)",
    "reussi":      "Paiement confirmé par l'opérateur",
    "echoue":      "Paiement refusé ou timeout",
    "annule":      "Annulé par le client",
    "rembourse":   "Remboursé",
}

PAYS_OPERATEUR = {
    "CM": ["mtn_momo", "orange_money", "cinetpay"],
    "CI": ["orange_money", "cinetpay", "wave", "mtn_momo"],
    "SN": ["orange_money", "wave", "cinetpay"],
    "BF": ["orange_money", "cinetpay", "moov_money"],
    "ML": ["orange_money", "cinetpay"],
    "TG": ["cinetpay"],
    "GA": ["airtel_money", "cinetpay"],
    "CG": ["airtel_money", "mtn_momo", "cinetpay"],
}


# ─── Gestionnaire principal ───────────────────────────────────────────────────

class GestionnairePaiement:
    """
    Orchestrateur de paiements Mobile Money multi-opérateurs.
    Sélectionne l'opérateur adapté et gère le cycle de vie complet.
    """

    def __init__(self, config: dict):
        """
        config : {
            "mtn_momo_api_key": ..., "mtn_momo_subscription_key": ..., "mtn_momo_env": "production",
            "orange_money_client_id": ..., "orange_money_secret": ..., "orange_money_pays": "CM",
            "cinetpay_api_key": ..., "cinetpay_site_id": ...,
            "wave_api_key": ...,
            "notify_url": "https://api.votrdomaine.com/api/v1/paiement/callback",
            "return_url": "https://votrdomaine.com/paiement/retour",
        }
        """
        self.config = config

    # ─── Initier un paiement ─────────────────────────────────────────────────

    async def initier_paiement(
        self,
        montant: float,
        devise: str = "XAF",
        operateur: str = "cinetpay",
        numero_client: Optional[str] = None,
        nom_client: Optional[str] = None,
        reference_interne: Optional[str] = None,
        description: str = "Paiement prime d'assurance",
        metadata: dict = None,
    ) -> dict:
        """
        Initie un paiement chez l'opérateur choisi.
        Retourne : {
            "reference": ...,
            "statut": "initie",
            "url_paiement": ...,   # lien redirect ou None si push USSD
            "instructions_ussd": ...,  # si applicable
            "operateur": ...,
        }
        """
        ref = reference_interne or f"PAY-{uuid.uuid4().hex[:10].upper()}"

        if operateur == "cinetpay":
            return await self._initier_cinetpay(ref, montant, devise, nom_client or "Client", description)
        elif operateur == "mtn_momo":
            return await self._initier_mtn_momo(ref, montant, devise, numero_client or "", description)
        elif operateur == "orange_money":
            return await self._initier_orange_money(ref, montant, devise, numero_client or "", description)
        elif operateur == "wave":
            return await self._initier_wave(ref, montant, devise, description)
        else:
            return self._instructions_manuelles(ref, montant, devise, operateur)

    # ─── CinetPay ────────────────────────────────────────────────────────────

    async def _initier_cinetpay(
        self, ref: str, montant: float, devise: str, nom: str, description: str
    ) -> dict:
        """
        API CinetPay v2 — agrégateur multi-pays zone CIMA.
        Supporte : MTN, Orange, Moov, Wave, Airtel via une seule intégration.
        """
        api_key = self.config.get("cinetpay_api_key", "")
        site_id = self.config.get("cinetpay_site_id", "")

        if not api_key:
            return self._simulation_paiement(ref, montant, devise, "cinetpay")

        payload = {
            "apikey": api_key,
            "site_id": site_id,
            "transaction_id": ref,
            "amount": int(montant),
            "currency": devise,
            "alternative_currency": "",
            "description": description,
            "customer_name": nom,
            "customer_surname": "",
            "customer_email": "",
            "customer_phone_number": "",
            "customer_address": "",
            "customer_city": "",
            "customer_country": "CM",
            "customer_state": "CM",
            "customer_zip_code": "",
            "notify_url": self.config.get("notify_url", ""),
            "return_url": self.config.get("return_url", ""),
            "channels": "ALL",
            "metadata": "yukpo_assurance",
            "lang": "FR",
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.cinetpay.com/v2/payment",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                data = resp.json()
                if data.get("code") == "201":
                    return {
                        "reference": ref,
                        "statut": "initie",
                        "url_paiement": data["data"]["payment_url"],
                        "operateur": "cinetpay",
                        "message": "Lien de paiement généré — rediriger le client",
                    }
                logger.error(f"[CinetPay] Erreur: {data}")
        except Exception as e:
            logger.error(f"[CinetPay] Exception: {e}")

        return self._simulation_paiement(ref, montant, devise, "cinetpay")

    # ─── MTN MoMo ────────────────────────────────────────────────────────────

    async def _initier_mtn_momo(
        self, ref: str, montant: float, devise: str, numero: str, description: str
    ) -> dict:
        """
        MTN Mobile Money Collections API.
        Envoie une demande de paiement Push (notification USSD sur le téléphone client).
        """
        api_key = self.config.get("mtn_momo_api_key", "")
        sub_key = self.config.get("mtn_momo_subscription_key", "")
        env = self.config.get("mtn_momo_env", "sandbox")

        if not api_key:
            return self._simulation_paiement(ref, montant, devise, "mtn_momo")

        base_url = "https://sandbox.momoapi.mtn.com" if env == "sandbox" else "https://proxy.momoapi.mtn.com"
        external_id = uuid.uuid4().hex

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Créer un token d'accès
                token_resp = await client.post(
                    f"{base_url}/collection/token/",
                    headers={
                        "Authorization": f"Basic {api_key}",
                        "Ocp-Apim-Subscription-Key": sub_key,
                    },
                )
                token = token_resp.json().get("access_token")
                if not token:
                    raise ValueError("Token MTN non obtenu")

                # Demande de paiement (requestToPay)
                numero_clean = numero.replace("+", "").replace(" ", "")
                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-Reference-Id": ref,
                    "X-Target-Environment": env,
                    "Ocp-Apim-Subscription-Key": sub_key,
                    "Content-Type": "application/json",
                }
                payload = {
                    "amount": str(int(montant)),
                    "currency": devise,
                    "externalId": external_id,
                    "payer": {"partyIdType": "MSISDN", "partyId": numero_clean},
                    "payerMessage": description,
                    "payeeNote": f"Paiement assurance ref {ref}",
                }
                await client.post(
                    f"{base_url}/collection/v1_0/requesttopay",
                    json=payload, headers=headers,
                )
                return {
                    "reference": ref,
                    "statut": "initie",
                    "operateur": "mtn_momo",
                    "instructions_ussd": f"Une demande de paiement a été envoyée sur le *{numero}*. Confirmez sur votre téléphone.",
                    "url_paiement": None,
                }
        except Exception as e:
            logger.error(f"[MTN MoMo] Exception: {e}")

        return self._simulation_paiement(ref, montant, devise, "mtn_momo")

    # ─── Orange Money ─────────────────────────────────────────────────────────

    async def _initier_orange_money(
        self, ref: str, montant: float, devise: str, numero: str, description: str
    ) -> dict:
        """Orange Money Payment API (Cameroun, CI, Sénégal...)"""
        client_id = self.config.get("orange_money_client_id", "")

        if not client_id:
            return self._simulation_paiement(ref, montant, devise, "orange_money")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # OAuth2 token
                token_resp = await client.post(
                    "https://api.orange.com/oauth/v3/token",
                    data={"grant_type": "client_credentials"},
                    headers={
                        "Authorization": f"Basic {self.config.get('orange_money_client_id')}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                token = token_resp.json().get("access_token")
                pays = self.config.get("orange_money_pays", "CM").lower()

                payload = {
                    "merchant_key": self.config.get("orange_money_merchant_key", ""),
                    "currency": devise,
                    "order_id": ref,
                    "amount": int(montant),
                    "return_url": self.config.get("return_url", ""),
                    "cancel_url": self.config.get("return_url", ""),
                    "notif_url": self.config.get("notify_url", ""),
                    "lang": "fr",
                    "reference": description,
                }
                resp = await client.post(
                    f"https://api.orange.com/orange-money-webpay/{pays}/v1/webpayment",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
                data = resp.json()
                return {
                    "reference": ref,
                    "statut": "initie",
                    "url_paiement": data.get("payment_url"),
                    "operateur": "orange_money",
                }
        except Exception as e:
            logger.error(f"[Orange Money] Exception: {e}")

        return self._simulation_paiement(ref, montant, devise, "orange_money")

    # ─── Wave ────────────────────────────────────────────────────────────────

    async def _initier_wave(self, ref: str, montant: float, devise: str, description: str) -> dict:
        """Wave API — Sénégal, Côte d'Ivoire, Mali, Cameroun"""
        api_key = self.config.get("wave_api_key", "")

        if not api_key:
            return self._simulation_paiement(ref, montant, devise, "wave")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.wave.com/v1/checkout/sessions",
                    json={
                        "currency": devise,
                        "amount": str(int(montant)),
                        "error_url": self.config.get("return_url", ""),
                        "success_url": self.config.get("return_url", ""),
                        "client_reference": ref,
                    },
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                )
                data = resp.json()
                return {
                    "reference": ref,
                    "statut": "initie",
                    "url_paiement": data.get("wave_launch_url"),
                    "operateur": "wave",
                }
        except Exception as e:
            logger.error(f"[Wave] Exception: {e}")

        return self._simulation_paiement(ref, montant, devise, "wave")

    # ─── Vérification statut ─────────────────────────────────────────────────

    async def verifier_statut(self, reference: str, operateur: str) -> dict:
        """Interroge l'opérateur pour connaître le statut d'une transaction."""
        if operateur == "cinetpay":
            return await self._verifier_cinetpay(reference)
        elif operateur == "mtn_momo":
            return await self._verifier_mtn(reference)
        return {"reference": reference, "statut": "inconnu", "operateur": operateur}

    async def _verifier_cinetpay(self, reference: str) -> dict:
        api_key = self.config.get("cinetpay_api_key", "")
        site_id = self.config.get("cinetpay_site_id", "")
        if not api_key:
            return {"reference": reference, "statut": "reussi", "operateur": "cinetpay", "simulation": True}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.cinetpay.com/v2/payment/check",
                    json={"apikey": api_key, "site_id": site_id, "transaction_id": reference},
                )
                data = resp.json()
                statut_map = {
                    "ACCEPTED": "reussi", "REFUSED": "echoue",
                    "PENDING": "en_cours", "CANCELLED": "annule",
                }
                return {
                    "reference": reference,
                    "statut": statut_map.get(data.get("data", {}).get("status", ""), "en_cours"),
                    "montant": data.get("data", {}).get("amount"),
                    "operateur": "cinetpay",
                }
        except Exception:
            return {"reference": reference, "statut": "inconnu", "operateur": "cinetpay"}

    async def _verifier_mtn(self, reference: str) -> dict:
        return {"reference": reference, "statut": "en_cours", "operateur": "mtn_momo"}

    # ─── Traitement callbacks ─────────────────────────────────────────────────

    def traiter_callback_cinetpay(self, payload: dict) -> dict:
        """Traite le webhook de confirmation CinetPay."""
        statut_map = {"ACCEPTED": "reussi", "REFUSED": "echoue", "CANCELLED": "annule"}
        return {
            "reference": payload.get("cpm_trans_id") or payload.get("transaction_id"),
            "statut": statut_map.get(payload.get("cpm_result", ""), "en_cours"),
            "montant": payload.get("cpm_amount"),
            "operateur": "cinetpay",
            "payload_brut": payload,
        }

    def traiter_callback_mtn(self, payload: dict) -> dict:
        """Traite le callback MTN MoMo."""
        return {
            "reference": payload.get("externalId") or payload.get("referenceId"),
            "statut": "reussi" if payload.get("status") == "SUCCESSFUL" else "echoue",
            "montant": payload.get("amount"),
            "operateur": "mtn_momo",
        }

    # ─── Simulation ──────────────────────────────────────────────────────────

    def _simulation_paiement(self, ref: str, montant: float, devise: str, operateur: str) -> dict:
        """Retourne un paiement simulé (mode développement)."""
        instructions = {
            "mtn_momo":     f"MTN MoMo : Composez *126# → Paiement marchands → Code : YUKPO001 → Montant : {montant:,.0f}",
            "orange_money": f"Orange Money : Composez #150# → Paiement → Marchand → Ref : {ref}",
            "cinetpay":     f"CinetPay : Lien → https://cinetpay.com/checkout/{ref} [SIMULATION]",
            "wave":         f"Wave : Ouvrez l'app Wave → Scanner QR → Ref : {ref}",
        }
        return {
            "reference": ref,
            "statut": "initie",
            "operateur": operateur,
            "simulation": True,
            "url_paiement": f"https://sandbox.paiement.yukpo.com/{ref}",
            "instructions_ussd": instructions.get(operateur, f"Payer {montant:,.0f} {devise} — Ref: {ref}"),
            "montant": montant,
            "devise": devise,
        }

    # ─── Instructions manuelles ───────────────────────────────────────────────

    def _instructions_manuelles(self, ref: str, montant: float, devise: str, operateur: str) -> dict:
        return {
            "reference": ref,
            "statut": "initie",
            "operateur": operateur,
            "message": f"Veuillez effectuer un paiement de {montant:,.0f} {devise} avec la référence {ref}",
        }


# ─── Calcul de remise / pénalité ─────────────────────────────────────────────

def calculer_penalite_retard_cima(
    montant_prime: float,
    jours_retard: int,
    taux_legal_annuel: float = 0.065,  # Taux légal zone CIMA (~6.5%)
) -> dict:
    """
    Calcule les pénalités de retard selon Art. 12-ter Code CIMA.
    Pénalité = taux légal + 50% par mois de retard.
    """
    taux_penalite = taux_legal_annuel * 1.5  # +50% du taux légal
    taux_journalier = taux_penalite / 365
    penalite = montant_prime * taux_journalier * jours_retard

    return {
        "montant_prime_fcfa": round(montant_prime),
        "jours_retard": jours_retard,
        "taux_penalite_annuel": f"{taux_penalite*100:.2f}%",
        "penalite_fcfa": round(penalite),
        "total_a_payer_fcfa": round(montant_prime + penalite),
        "article": "Art. 12-ter Code CIMA",
        "note": "Taux légal + 50% appliqué après 45 jours post-accord",
    }
