"""
YukpoAssurance — API GraphQL (Strawberry)

Expose les données métier clés via GraphQL pour :
- Dashboards analytics flexibles (frontend peut requêter exactement ce dont il a besoin)
- Intégrations partenaires (courtiers, ORASS, portails tiers)
- Requêtes complexes multi-entités en un seul appel réseau

Types exposés :
- SinistreType — sinistres, scores fraude, historique
- ContratType — polices, primes, garanties
- CourtierType — portefeuille, commissions, KPIs
- ConformiteCIMAType — ratios prudentiels, alertes
- PredictionMLType — score risque ML, prime suggérée

Auth : JWT requis dans Authorization header (réutilise la même auth que REST)
"""
from __future__ import annotations

import logging
from typing import List, Optional
from datetime import date

logger = logging.getLogger("yukpo_assurance.graphql")

try:
    import strawberry
    from strawberry.fastapi import GraphQLRouter
    from strawberry.types import Info
    _STRAWBERRY_OK = True
except ImportError:
    _STRAWBERRY_OK = False
    logger.info("[GraphQL] strawberry-graphql non installé — endpoint GraphQL désactivé")


def creer_router_graphql():
    """
    Crée et retourne le router GraphQL.
    Retourne None si strawberry n'est pas installé.
    """
    if not _STRAWBERRY_OK:
        return None

    # ── Types GraphQL ─────────────────────────────────────────────────────────

    @strawberry.type
    class SinistreType:
        numero_sinistre: str
        numero_police: str
        branche: str
        nature: str
        montant_declare: float
        statut: str
        date_sinistre: Optional[str] = None
        score_fraude: Optional[float] = None
        alerte_fraude: Optional[bool] = None

    @strawberry.type
    class ContratType:
        numero_police: str
        branche: str
        statut: str
        prime_ttc: float
        date_effet: Optional[str] = None
        date_echeance: Optional[str] = None
        assure_nom: Optional[str] = None

    @strawberry.type
    class CourtierType:
        code: str
        raison_sociale: str
        ville: str
        actif: bool
        nb_contrats: Optional[int] = None
        primes_ttc_annuelles: Optional[float] = None
        taux_commission: Optional[float] = None

    @strawberry.type
    class RatioCIMAType:
        nom: str
        valeur: float
        seuil: float
        conforme: bool
        article: str
        alerte: Optional[str] = None

    @strawberry.type
    class ConformiteCIMAType:
        statut_global: str
        score_conformite: int
        nombre_alertes: int
        ratios: List[RatioCIMAType]

    @strawberry.type
    class PredictionMLType:
        score_risque: float
        segment_risque: str
        coefficient_ml: float
        prime_actuarielle_fcfa: float
        prime_ml_fcfa: float
        confiance: str

    @strawberry.type
    class MetriquesIAType:
        modele: str
        total_requetes: int
        taux_succes: str
        temps_moyen_ms: float
        cout_total_usd: float
        circuit_ouvert: bool

    # ── Context (auth) ────────────────────────────────────────────────────────

    def _get_current_user_from_context(info: Info):
        """Extrait le user depuis le contexte HTTP (header Authorization)."""
        request = info.context["request"]
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise Exception("Authentication required")
        from core.auth import _decoder_token
        try:
            return _decoder_token(auth[7:])
        except Exception:
            raise Exception("Invalid or expired token")

    # ── Queries ───────────────────────────────────────────────────────────────

    @strawberry.type
    class Query:

        @strawberry.field
        def sinistres(
            self,
            info: Info,
            limite: int = 20,
            branche: Optional[str] = None,
            statut: Optional[str] = None,
        ) -> List[SinistreType]:
            """Liste les sinistres avec filtres optionnels."""
            user = _get_current_user_from_context(info)
            from core.orass_connector import orass
            import asyncio

            try:
                filtres = {}
                if branche:
                    filtres["branche"] = branche
                if statut:
                    filtres["statut"] = statut

                loop = asyncio.new_event_loop()
                sinistres_raw = loop.run_until_complete(
                    orass.lister_sinistres(filtres=filtres, limite=min(limite, 100))
                )
                loop.close()

                return [
                    SinistreType(
                        numero_sinistre=s.get("numero_sinistre", ""),
                        numero_police=s.get("numero_police", ""),
                        branche=s.get("branche", ""),
                        nature=s.get("nature", ""),
                        montant_declare=float(s.get("montant_declare", 0)),
                        statut=s.get("statut", ""),
                        date_sinistre=str(s.get("date_sinistre", "")),
                        score_fraude=s.get("score_fraude"),
                        alerte_fraude=s.get("alerte_fraude"),
                    )
                    for s in sinistres_raw
                ]
            except Exception as e:
                logger.warning(f"[GraphQL] sinistres query: {e}")
                return []

        @strawberry.field
        def contrats(
            self,
            info: Info,
            limite: int = 20,
            branche: Optional[str] = None,
        ) -> List[ContratType]:
            """Liste les polices d'assurance actives."""
            user = _get_current_user_from_context(info)
            from core.orass_connector import orass
            import asyncio

            try:
                loop = asyncio.new_event_loop()
                contrats_raw = loop.run_until_complete(
                    orass.lister_contrats(filtres={"branche": branche} if branche else {}, limite=min(limite, 100))
                )
                loop.close()

                return [
                    ContratType(
                        numero_police=c.get("numero_police", ""),
                        branche=c.get("branche", ""),
                        statut=c.get("statut", ""),
                        prime_ttc=float(c.get("prime_ttc", 0)),
                        date_effet=str(c.get("date_effet", "")),
                        date_echeance=str(c.get("date_echeance", "")),
                        assure_nom=c.get("assure", {}).get("nom", ""),
                    )
                    for c in contrats_raw
                ]
            except Exception as e:
                logger.warning(f"[GraphQL] contrats query: {e}")
                return []

        @strawberry.field
        def conformite_cima(
            self,
            info: Info,
            primes_nettes: float = 1_000_000_000,
            capitaux_propres: float = 500_000_000,
            provisions_techniques: float = 600_000_000,
            actifs_admis: float = 650_000_000,
            primes_brutes: float = 1_100_000_000,
            primes_cedees: float = 150_000_000,
        ) -> ConformiteCIMAType:
            """Calcul de conformité CIMA en temps réel."""
            _get_current_user_from_context(info)
            from modules.cima.code_cima_engine import cima_engine

            donnees = {
                "primes_nettes": primes_nettes,
                "capitaux_propres": capitaux_propres,
                "provisions_techniques": provisions_techniques,
                "actifs_admis_couverture": actifs_admis,
                "primes_emises_brutes": primes_brutes,
                "primes_cedees_reassurance": primes_cedees,
            }
            rapport = cima_engine.rapport_conformite_global(donnees)

            ratios = []
            for nom, ratio_data in rapport.get("ratios", {}).items():
                ratios.append(RatioCIMAType(
                    nom=nom,
                    valeur=float(ratio_data.get("taux_couverture", ratio_data.get("ratio_sp", 0)) or 0),
                    seuil=100.0,
                    conforme=bool(ratio_data.get("conforme", True)),
                    article=ratio_data.get("article", "Code CIMA"),
                    alerte=ratio_data.get("alerte"),
                ))

            return ConformiteCIMAType(
                statut_global=rapport["statut_global"],
                score_conformite=rapport["score_conformite"],
                nombre_alertes=rapport["nombre_alertes"],
                ratios=ratios,
            )

        @strawberry.field
        def prediction_ml(
            self,
            info: Info,
            age_conducteur: int = 35,
            nb_sinistres_3ans: int = 0,
            score_bonus_malus: float = 1.0,
            puissance_fiscale_cv: int = 6,
            usage: str = "particulier",
            zone: str = "yaounde",
            prime_actuarielle_fcfa: float = 100_000,
        ) -> PredictionMLType:
            """Prédiction ML du score de risque et prime ajustée."""
            _get_current_user_from_context(info)
            from modules.tarification.ml_tarification import ml_tarification, ProfilRisqueML

            profil = ProfilRisqueML(
                age_conducteur=age_conducteur,
                nb_sinistres_3ans=nb_sinistres_3ans,
                score_bonus_malus=score_bonus_malus,
                puissance_fiscale_cv=puissance_fiscale_cv,
                usage=usage,
                zone=zone,
            )
            pred = ml_tarification.predire(profil, prime_actuarielle_fcfa)

            return PredictionMLType(
                score_risque=pred.score_risque,
                segment_risque=pred.segment_risque,
                coefficient_ml=pred.coefficient_ml,
                prime_actuarielle_fcfa=pred.prime_actuarielle_fcfa,
                prime_ml_fcfa=pred.prime_suggestion_fcfa,
                confiance=pred.confiance,
            )

        @strawberry.field
        def metriques_ia(self, info: Info) -> List[MetriquesIAType]:
            """Métriques de performance des modèles IA."""
            _get_current_user_from_context(info)
            from core.ia_client import ia_client

            rapport = ia_client.rapport_metriques()
            return [
                MetriquesIAType(
                    modele=modele,
                    total_requetes=data["total"],
                    taux_succes=data["taux_succes"],
                    temps_moyen_ms=data["temps_moyen_ms"],
                    cout_total_usd=data["cout_total_usd"],
                    circuit_ouvert=data["circuit_ouvert"],
                )
                for modele, data in rapport.items()
            ]

    # ── Schéma ────────────────────────────────────────────────────────────────

    from strawberry.extensions import MaxAliasesExtension
    schema = strawberry.Schema(
        query=Query,
        extensions=[MaxAliasesExtension(max_aliases=15)],
    )

    return GraphQLRouter(
        schema,
        graphql_ide="graphiql",  # Interface GraphiQL interactive
    )
