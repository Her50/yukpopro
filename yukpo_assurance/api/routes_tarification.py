"""
Routes tarification — Moteur tarifaire prédictif CIMA
Calcul de prime, simulation multi-scénarios, barèmes, validation actuarielle.
"""
import csv
import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile
from pydantic import BaseModel, Field
from typing import Any, Optional

logger = logging.getLogger("yukpo_assurance.api.tarification")

from modules.tarification.moteur_tarifaire import moteur_tarifaire
from core.auth import TokenData, get_current_user, require_permission

router = APIRouter(dependencies=[Depends(get_current_user)])

BRANCHES_VALIDES = {"auto", "vie", "ird", "rc", "transport", "maladie"}


class ProfilRisqueRequest(BaseModel):
    """Profil risque générique — les champs varient selon la branche."""

    branche: str = Field(..., description="auto | vie | ird | rc | transport | maladie")

    # Champs communs
    age_assure: Optional[int] = Field(None, description="Âge de l'assuré principal (années)")
    zone_geographique: Optional[str] = Field(None, description="Ville / zone (yaoundé, douala, ...)")
    sinistres_5_ans: Optional[int] = Field(0, description="Nombre de sinistres déclarés sur 5 ans")
    anciennete_client_ans: Optional[int] = Field(0, description="Ancienneté en tant que client (ans)")
    delai_moyen_paiement_jours: Optional[int] = Field(0, description="Délai moyen de règlement prime (jours)")
    nb_contrats_actifs: Optional[int] = Field(1, description="Nombre de contrats actifs dans la compagnie")
    historique_impaye: Optional[bool] = Field(False, description="A déjà eu un impayé")

    # Auto
    puissance_fiscale_cv: Optional[int] = Field(None, description="Puissance fiscale du véhicule (CV)")
    annee_vehicule: Optional[int] = Field(None, description="Année de mise en circulation")
    usage: Optional[str] = Field(None, description="particulier | taxi | transport_commun | utilitaire | societe")
    valeur_venale_fcfa: Optional[int] = Field(None, description="Valeur vénale du véhicule (FCFA)")

    # Vie
    capital_fcfa: Optional[int] = Field(None, description="Capital décès assuré (FCFA)")
    duree_ans: Optional[int] = Field(None, description="Durée du contrat vie (années)")
    etat_sante: Optional[str] = Field(None, description="excellent | bon | moyen | mauvais")

    # IRD
    valeur_bien_fcfa: Optional[int] = Field(None, description="Valeur du bien assuré (FCFA)")
    type_construction: Optional[str] = Field(None, description="dur_standing | dur_standard | semi_dur | bois_paille | industriel")
    garanties_ird: Optional[list[str]] = Field(None, description="Liste de garanties IRD souhaitées")

    # RC
    activite_professionnelle: Optional[str] = Field(None, description="Activité pro (btp_construction, commerce_detail, ...)")
    chiffre_affaires_fcfa: Optional[int] = Field(None, description="Chiffre d'affaires annuel (FCFA)")
    nb_employes: Optional[int] = Field(None, description="Nombre de salariés")

    # Transport
    valeur_marchandises_fcfa: Optional[int] = Field(None, description="Valeur des marchandises (FCFA)")
    type_transport: Optional[str] = Field(None, description="terrestre_national | terrestre_regional | maritime_import | maritime_export | aerien")
    nb_voyages_annuels: Optional[int] = Field(None, description="Nombre de voyages par an")

    # Maladie
    nb_personnes_couvertes: Optional[int] = Field(None, description="Nombre de personnes à couvrir")
    formule_maladie: Optional[str] = Field(None, description="hospitalisation_seule | pharmacie | consultation_hospit | complementaire_totale | dentaire_optique")

    # Champs libres supplémentaires
    extras: Optional[dict[str, Any]] = Field(None, description="Champs supplémentaires libres")

    def to_profil(self) -> dict:
        d = self.model_dump(exclude_none=True, exclude={"extras"})
        if self.extras:
            d.update(self.extras)
        return d


class ValidationPrimeRequest(BaseModel):
    branche: str
    prime_proposee: int = Field(..., gt=0, description="Prime nette proposée (FCFA)")
    profil: dict = Field(default_factory=dict, description="Profil risque identique à /calculer")


@router.post(
    "/calculer",
    summary="Calcul de prime complet",
    description=(
        "Calcule la prime actuarielle avec : scoring risque 0-100, barème calibré CIMA, "
        "ajustement IA, taxes 15% (ou 5% vie), et 3 offres comparatives (Basique/Standard/Premium)."
    ),
)
async def calculer_prime(
    req: ProfilRisqueRequest,
    current_user: TokenData = Depends(get_current_user),
):
    branche = req.branche.lower()
    if branche not in BRANCHES_VALIDES:
        raise HTTPException(
            400,
            f"Branche inconnue : {branche}. Valeurs acceptées : {sorted(BRANCHES_VALIDES)}",
        )
    profil = req.to_profil()
    return await moteur_tarifaire.calculer_prime(profil)


@router.post(
    "/simuler-multi-scenarios",
    summary="Simulation multi-scénarios (3 offres)",
    description=(
        "Compare directement les 3 offres tarifaires (Basique / Standard / Premium) "
        "avec le détail des garanties, franchises et primes TTC."
    ),
)
async def simuler_multi_scenarios(
    req: ProfilRisqueRequest,
    current_user: TokenData = Depends(get_current_user),
):
    branche = req.branche.lower()
    if branche not in BRANCHES_VALIDES:
        raise HTTPException(400, f"Branche inconnue : {branche}")
    profil = req.to_profil()
    resultat = await moteur_tarifaire.calculer_prime(profil)
    return {
        "branche": branche,
        "score_risque": resultat["score_risque"],
        "categorie_risque": resultat["categorie_risque"],
        "offres_comparatives": resultat["offres_comparatives"],
        "recommandations_garanties": resultat["recommandations_garanties"],
    }


@router.get(
    "/baremes/{branche}",
    summary="Barème tarifaire par branche",
    description="Retourne les tables de tarification (taux, coefficients, minimums) de la branche CIMA.",
)
async def get_bareme(
    branche: str = Path(..., description="auto | vie | ird | rc | transport | maladie"),
    current_user: TokenData = Depends(get_current_user),
):
    branche = branche.lower()
    return moteur_tarifaire.get_bareme(branche)


@router.post(
    "/valider-prime",
    summary="Validation actuarielle d'une prime proposée",
    description=(
        "Vérifie si une prime proposée est techniquement suffisante par rapport à la prime "
        "calculée + marge technique minimale 10%. Retourne un avis de conformité."
    ),
)
async def valider_prime(
    req: ValidationPrimeRequest,
    current_user: TokenData = Depends(get_current_user),
):
    branche = req.branche.lower()
    if branche not in BRANCHES_VALIDES:
        raise HTTPException(400, f"Branche inconnue : {branche}")
    return moteur_tarifaire.valider_prime(branche, req.prime_proposee, req.profil)


# ─── ML Tarification — RandomForest ──────────────────────────────────────────

class ProfilMLRequest(BaseModel):
    """Profil risque pour prédiction ML (enrichi vs profil actuariel de base)."""
    # Conducteur
    age_conducteur: int = Field(35, ge=16, le=90)
    anciennete_permis: int = Field(10, ge=0, le=72)
    nb_sinistres_3ans: int = Field(0, ge=0, le=20)
    nb_infractions_3ans: int = Field(0, ge=0, le=20)
    score_bonus_malus: float = Field(1.0, ge=0.5, le=3.5)
    # Véhicule
    puissance_fiscale_cv: int = Field(6, ge=2, le=20)
    age_vehicule_ans: int = Field(5, ge=0, le=40)
    valeur_venale_mfcfa: float = Field(5.0, ge=0.1, le=500.0)
    usage: str = Field("particulier", description="particulier|societe|utilitaire|taxi|transport_commun")
    # Contexte
    zone: str = Field("yaounde", description="yaounde|douala|bafoussam|garoua|maroua|autres")
    mois_souscription: int = Field(6, ge=1, le=12)
    branche: str = Field("auto_rc", description="auto_rc|auto_tr|ird|rc_pro|transport")
    # Prime actuarielle de base (calculée séparément)
    prime_actuarielle_fcfa: float = Field(100_000, gt=0, description="Prime actuarielle de base (FCFA)")
    # Compagnie
    taux_cession_reassurance: float = Field(0.15, ge=0.0, le=1.0)
    ratio_sp_branche: float = Field(0.62, ge=0.0, le=2.0)


class ReentrainementRequest(BaseModel):
    donnees: list[dict] = Field(..., description="Liste de profils avec score_risque_reel")


@router.post(
    "/ml/predire",
    summary="Prédiction ML du risque et de la prime ajustée",
    description=(
        "Utilise le modèle RandomForest entraîné pour prédire le score de risque (0-100), "
        "le segment (bon/moyen/élevé) et la prime ML ajustée. "
        "Plus précis que le barème forfaitaire — intègre l'historique sinistral individuel."
    ),
)
async def predire_ml(
    req: ProfilMLRequest,
    current_user: TokenData = Depends(get_current_user),
):
    from modules.tarification.ml_tarification import ml_tarification, ProfilRisqueML

    profil = ProfilRisqueML(
        age_conducteur=req.age_conducteur,
        anciennete_permis=req.anciennete_permis,
        nb_sinistres_3ans=req.nb_sinistres_3ans,
        nb_infractions_3ans=req.nb_infractions_3ans,
        score_bonus_malus=req.score_bonus_malus,
        puissance_fiscale_cv=req.puissance_fiscale_cv,
        age_vehicule_ans=req.age_vehicule_ans,
        valeur_venale_mfcfa=req.valeur_venale_mfcfa,
        usage=req.usage,
        zone=req.zone,
        mois_souscription=req.mois_souscription,
        branche=req.branche,
        taux_cession_reassurance=req.taux_cession_reassurance,
        ratio_sp_branche=req.ratio_sp_branche,
    )
    pred = ml_tarification.predire(profil, req.prime_actuarielle_fcfa)

    return {
        "score_risque": pred.score_risque,
        "segment_risque": pred.segment_risque,
        "coefficient_ml": pred.coefficient_ml,
        "prime_actuarielle_fcfa": pred.prime_actuarielle_fcfa,
        "prime_ml_fcfa": pred.prime_suggestion_fcfa,
        "gain_precision_pct": pred.gain_precision_pct,
        "features_importance": pred.features_importance,
        "confiance": pred.confiance,
        "modele_version": pred.modele_version,
        "interpretation": (
            f"Score {pred.score_risque:.0f}/100 ({pred.segment_risque.replace('_', ' ')}) — "
            f"coefficient ML {pred.coefficient_ml:.3f} → prime ajustée "
            f"{pred.prime_suggestion_fcfa:,.0f} FCFA "
            f"({'↓' if pred.coefficient_ml < 1 else '↑'}"
            f"{abs(1-pred.coefficient_ml)*100:.1f}% vs actuariel)"
        ),
    }


@router.get(
    "/ml/performance",
    summary="Performance et état du modèle ML",
    description="Retourne les métriques du modèle ML : samples d'entraînement, feature importances, MAE.",
)
async def performance_ml(current_user: TokenData = Depends(get_current_user)):
    from modules.tarification.ml_tarification import ml_tarification
    return ml_tarification.rapport_performance()


@router.post(
    "/ml/reentrainer",
    summary="Ré-entraîner le modèle sur des données réelles",
    description=(
        "Lance un ré-entraînement du RandomForest sur des données de sinistralité réelle. "
        "Format : liste de profils avec score_risque_reel. Réservé aux actuaires."
    ),
)
async def reentrainer_ml(
    req: ReentrainementRequest,
    current_user: TokenData = Depends(require_permission("actuaire")),
):
    from modules.tarification.ml_tarification import ml_tarification

    if len(req.donnees) < 50:
        raise HTTPException(400, f"Minimum 50 samples requis pour ré-entraînement (fournis: {len(req.donnees)})")

    resultat = ml_tarification.entrainer(donnees_reelles=req.donnees)
    if resultat.get("statut") == "erreur":
        raise HTTPException(500, resultat["detail"])

    return {
        "statut": "ok",
        "message": f"Modèle ré-entraîné sur {resultat['nb_samples']} samples",
        "mae_cv": resultat["mae_cv"],
        "duree_secondes": resultat["duree_secondes"],
    }


@router.post(
    "/ml/importer-csv-orass",
    summary="Importer un export CSV ORASS/Mercure pour ré-entraînement ML",
    description=(
        "Accepte un fichier CSV exporté depuis ORASS ou Mercure contenant l'historique de sinistralité. "
        "Colonnes minimales requises : age_conducteur, nb_sinistres_3ans, score_bonus_malus, branche, "
        "montant_sinistre_fcfa (optionnel : anciennete_permis, puissance_fiscale_cv, usage, zone). "
        "Le score_risque_reel est calculé automatiquement depuis le ratio sinistre/prime. "
        "Déclenche un ré-entraînement si ≥ 50 lignes valides sont importées."
    ),
)
async def importer_csv_orass(
    fichier: UploadFile = File(..., description="Fichier CSV export ORASS/Mercure"),
    reentrainer: bool = True,
    current_user: Any = Depends(require_permission("actuaire")),
):
    """
    Mapping colonnes CSV ORASS → ProfilRisqueML :

    Colonne CSV ORASS          → Champ ML
    ────────────────────────────────────────
    AGE_CONDUCTEUR             → age_conducteur
    ANCIENNETE_PERMIS          → anciennete_permis
    NB_SINISTRES_3ANS          → nb_sinistres_3ans
    NB_INFRACTIONS             → nb_infractions_3ans
    COEFF_BONUS_MALUS          → score_bonus_malus
    PUISSANCE_FISCALE          → puissance_fiscale_cv
    AGE_VEHICULE               → age_vehicule_ans
    VALEUR_VENALE              → valeur_venale_mfcfa (si en FCFA → diviser par 1M)
    USAGE_VEHICULE             → usage
    ZONE_RISQUE / VILLE        → zone
    MOIS_SOUSCRIPTION          → mois_souscription
    BRANCHE_CODE               → branche
    MONTANT_SINISTRE_FCFA      → montant_sinistre_fcfa
    PRIME_NETTE_FCFA           → prime_reelle_fcfa (pour calculer score_risque_reel)
    TAUX_CESSION_REASSURANCE   → taux_cession_reassurance
    RATIO_SP_BRANCHE           → ratio_sp_branche
    """
    from modules.tarification.ml_tarification import ml_tarification

    if not fichier.filename.endswith(".csv"):
        raise HTTPException(400, "Seuls les fichiers .csv sont acceptés")

    contenu = await fichier.read()
    if len(contenu) > 10 * 1024 * 1024:  # 10 MB max
        raise HTTPException(413, "Fichier trop volumineux (max 10 MB)")

    # Détecter l'encodage (UTF-8 ou latin-1 courant en exports ORASS Windows)
    for encoding in ("utf-8-sig", "latin-1", "utf-8"):
        try:
            texte = contenu.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise HTTPException(400, "Encodage du fichier non supporté (UTF-8 ou latin-1 requis)")

    # Parser le CSV
    # Supporte séparateur , ou ; (exports Excel francophones utilisent ;)
    premier_ligne = texte.split("\n")[0]
    separateur = ";" if premier_ligne.count(";") > premier_ligne.count(",") else ","

    reader = csv.DictReader(io.StringIO(texte), delimiter=separateur)

    ALIAS = {
        # Normalise les variantes de noms de colonnes ORASS/Mercure
        "AGE_CONDUCTEUR":          "age_conducteur",
        "AGE_ASSURE":              "age_conducteur",
        "ANCIENNETE_PERMIS":       "anciennete_permis",
        "NB_SINISTRES_3ANS":       "nb_sinistres_3ans",
        "NB_SINISTRES":            "nb_sinistres_3ans",
        "NB_INFRACTIONS":          "nb_infractions_3ans",
        "NB_INFRACTIONS_3ANS":     "nb_infractions_3ans",
        "COEFF_BONUS_MALUS":       "score_bonus_malus",
        "COEFFICIENT_BM":          "score_bonus_malus",
        "CRM":                     "score_bonus_malus",
        "PUISSANCE_FISCALE":       "puissance_fiscale_cv",
        "PUISSANCE_CV":            "puissance_fiscale_cv",
        "AGE_VEHICULE":            "age_vehicule_ans",
        "AGE_VEH":                 "age_vehicule_ans",
        "VALEUR_VENALE":           "valeur_venale_mfcfa",
        "VALEUR_VENALE_FCFA":      "valeur_venale_mfcfa",
        "USAGE_VEHICULE":          "usage",
        "USAGE":                   "usage",
        "ZONE_RISQUE":             "zone",
        "VILLE":                   "zone",
        "LOCALITE":                "zone",
        "MOIS_SOUSCRIPTION":       "mois_souscription",
        "BRANCHE_CODE":            "branche",
        "BRANCHE":                 "branche",
        "MONTANT_SINISTRE_FCFA":   "montant_sinistre_fcfa",
        "MONTANT_SINISTRE":        "montant_sinistre_fcfa",
        "PRIME_NETTE_FCFA":        "prime_reelle_fcfa",
        "PRIME_NETTE":             "prime_reelle_fcfa",
        "TAUX_CESSION":            "taux_cession_reassurance",
        "TAUX_CESSION_REASSURANCE":"taux_cession_reassurance",
        "RATIO_SP_BRANCHE":        "ratio_sp_branche",
        "RATIO_SP":                "ratio_sp_branche",
    }

    donnees_importees = []
    erreurs = []

    for idx, row in enumerate(reader, start=2):
        # Normaliser les noms de colonnes
        row_norm = {}
        for k, v in row.items():
            k_upper = (k or "").strip().upper().replace(" ", "_")
            mapped = ALIAS.get(k_upper, k.strip().lower())
            row_norm[mapped] = (v or "").strip()

        try:
            def _float(key, default=0.0):
                val = row_norm.get(key, "").replace(",", ".").replace(" ", "")
                try: return float(val) if val else default
                except ValueError: return default

            def _int(key, default=0):
                return int(_float(key, default))

            # Valeur vénale : si > 100 000 → probablement en FCFA entier → convertir en MFCFA
            valeur_venale_raw = _float("valeur_venale_mfcfa", 5.0)
            valeur_venale = valeur_venale_raw / 1_000_000 if valeur_venale_raw > 1000 else valeur_venale_raw

            # Normaliser la zone
            zone_raw = row_norm.get("zone", "autres").lower().strip()
            zone = zone_raw if zone_raw in (
                "yaounde", "douala", "bafoussam", "garoua", "maroua", "autres",
                "abidjan", "dakar", "libreville", "brazzaville", "bangui", "ndjamena",
            ) else "autres"

            # Normaliser la branche
            branche_raw = row_norm.get("branche", "auto_rc").lower().strip()
            branche_map = {
                "auto": "auto_rc", "auto_rc": "auto_rc", "rc_auto": "auto_rc",
                "auto_tr": "auto_tr", "tous_risques": "auto_tr",
                "ird": "ird", "incendie": "ird", "mrh": "ird",
                "rc": "rc_pro", "rc_pro": "rc_pro",
                "transport": "transport", "cargo": "transport",
            }
            branche = branche_map.get(branche_raw, "auto_rc")

            # Calcul du score_risque_reel depuis le ratio sinistre/prime
            montant_sinistre = _float("montant_sinistre_fcfa", 0.0)
            prime_reelle = _float("prime_reelle_fcfa", 100_000.0)
            ratio_sinistre = montant_sinistre / max(prime_reelle, 1.0)

            # Score 0-100 calibré : ratio 0 → score 10, ratio 1 → score 60, ratio 3+ → score 100
            score_risque_reel = min(100.0, max(0.0,
                10.0 + ratio_sinistre * 50.0
                + _int("nb_sinistres_3ans", 0) * 8.0
                + _int("nb_infractions_3ans", 0) * 5.0
                + max(0, _float("score_bonus_malus", 1.0) - 1.0) * 12.0
            ))

            donnees_importees.append({
                "age_conducteur":          _int("age_conducteur", 35),
                "anciennete_permis":       _int("anciennete_permis", 10),
                "nb_sinistres_3ans":       _int("nb_sinistres_3ans", 0),
                "nb_infractions_3ans":     _int("nb_infractions_3ans", 0),
                "score_bonus_malus":       round(_float("score_bonus_malus", 1.0), 2),
                "puissance_fiscale_cv":    _int("puissance_fiscale_cv", 6),
                "age_vehicule_ans":        _int("age_vehicule_ans", 5),
                "valeur_venale_mfcfa":     round(valeur_venale, 2),
                "usage":                   row_norm.get("usage", "particulier").lower() or "particulier",
                "zone":                    zone,
                "mois_souscription":       _int("mois_souscription", 6),
                "branche":                 branche,
                "taux_cession_reassurance":round(_float("taux_cession_reassurance", 0.15), 4),
                "ratio_sp_branche":        round(_float("ratio_sp_branche", 0.62), 4),
                "montant_sinistre_fcfa":   round(montant_sinistre, 0),
                "prime_reelle_fcfa":       round(prime_reelle, 0),
                "sinistre_survenu":        montant_sinistre > 0,
                "score_risque_reel":       round(score_risque_reel, 1),
            })

        except Exception as e:
            erreurs.append({"ligne": idx, "erreur": str(e), "donnees": dict(row)})
            if len(erreurs) > 20:
                raise HTTPException(
                    400,
                    f"Trop d'erreurs de parsing (>20). Vérifiez le format du CSV. "
                    f"Première erreur : {erreurs[0]}"
                )

    nb_valides = len(donnees_importees)
    if nb_valides < 10:
        raise HTTPException(
            400,
            f"Seulement {nb_valides} lignes valides importées. Minimum 10 requis. "
            f"Erreurs : {erreurs[:5]}"
        )

    logger.info(
        f"[ML CSV] Import ORASS : {nb_valides} lignes valides, {len(erreurs)} erreurs"
    )

    # Ré-entraînement si demandé et suffisamment de données
    resultat_entrainement = None
    if reentrainer and nb_valides >= 50:
        resultat_entrainement = ml_tarification.entrainer(donnees_reelles=donnees_importees)

    return {
        "statut": "ok",
        "fichier": fichier.filename,
        "lignes_importees": nb_valides,
        "lignes_erreur": len(erreurs),
        "erreurs_echantillon": erreurs[:5] if erreurs else [],
        "reentrainement": resultat_entrainement or (
            {"statut": "non_demande"} if not reentrainer
            else {"statut": "skipped", "raison": f"Seulement {nb_valides} lignes (min 50 pour ré-entraînement)"}
        ),
    }


@router.get(
    "/ml/derive",
    summary="Évaluer la dérive du modèle ML",
    description=(
        "Évalue la dérive du modèle ML sur les 200 derniers feedbacks réels. "
        "Retourne le MAE actuel et une recommandation de ré-entraînement si MAE > 15."
    ),
)
async def evaluer_derive_ml(current_user: Any = Depends(get_current_user)):
    from modules.tarification.ml_tarification import ml_tarification
    return ml_tarification.evaluer_derive()


@router.post(
    "/ml/feedback",
    summary="Enregistrer un feedback sinistre réel pour amélioration continue",
    description=(
        "Enregistre le résultat réel d'un contrat (sinistre survenu ou non) pour améliorer "
        "le modèle ML. Les feedbacks s'accumulent et déclenchent un ré-entraînement automatique "
        "tous les 100 feedbacks."
    ),
)
async def enregistrer_feedback_ml(
    req: ProfilMLRequest,
    sinistre_survenu: bool = False,
    montant_sinistre_fcfa: float = 0.0,
    current_user: Any = Depends(get_current_user),
):
    from modules.tarification.ml_tarification import ml_tarification, ProfilRisqueML

    profil = ProfilRisqueML(
        age_conducteur=req.age_conducteur,
        anciennete_permis=req.anciennete_permis,
        nb_sinistres_3ans=req.nb_sinistres_3ans,
        nb_infractions_3ans=req.nb_infractions_3ans,
        score_bonus_malus=req.score_bonus_malus,
        puissance_fiscale_cv=req.puissance_fiscale_cv,
        age_vehicule_ans=req.age_vehicule_ans,
        valeur_venale_mfcfa=req.valeur_venale_mfcfa,
        usage=req.usage,
        zone=req.zone,
        mois_souscription=req.mois_souscription,
        branche=req.branche,
        taux_cession_reassurance=req.taux_cession_reassurance,
        ratio_sp_branche=req.ratio_sp_branche,
    )
    ok = ml_tarification.enregistrer_feedback(
        profil=profil,
        prime_proposee_fcfa=req.prime_actuarielle_fcfa,
        prime_reelle_fcfa=req.prime_actuarielle_fcfa,
        sinistre_survenu=sinistre_survenu,
        montant_sinistre_fcfa=montant_sinistre_fcfa,
    )
    nb = ml_tarification._compter_feedbacks()
    return {
        "statut": "ok" if ok else "erreur",
        "feedbacks_total": nb,
        "prochain_retrainement_dans": max(0, 100 - (nb % 100)) if ok else None,
    }
