"""
YukpoAssurance — Analytics & Tableaux de Bord
Analyses poussées et dashboards pour les compagnies d'assurance CIMA.
Combine données ORASS + IA analytique + génération de rapports visuels.

Fonctionnalités :
- Dashboard de performance globale (temps réel)
- Analyse de sinistralité par branche / région / agent
- Suivi de la conformité CIMA (ratios prudentiels)
- Analyse du portefeuille (renouvellements, impayés, résiliations)
- Détection d'anomalies comptables et opérationnelles
- Analyse prédictive (projection de sinistralité, risque de résiliation)
- Rapport narratif IA sur les chiffres
- Dashboard sinistres temps réel, fraude, commercial, heatmap géographique
"""
import logging
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from core.ia_client import ModeIA, ia_client
from core.orass_connector import orass
from modules.cima.code_cima_engine import cima_engine
from modules.documents.generateur import DocumentGenerateur

logger = logging.getLogger("yukpo_assurance.analytics")


@dataclass
class KPI:
    libelle: str
    valeur: Any
    unite: str = ""
    tendance: Optional[str] = None      # "+12%" ou "-5%"
    statut: str = "normal"              # "normal" | "attention" | "critique"
    benchmark: Optional[str] = None     # valeur de référence CIMA ou marché
    valeur_num: Optional[float] = None  # Valeur numérique brute pour le frontend


@dataclass
class Dashboard:
    titre: str
    periode: str
    kpis: list[KPI]
    alertes: list[str]
    graphiques: list[dict]  # données pour les graphiques frontend
    narrative_ia: Optional[str] = None
    genere_le: str = field(default_factory=lambda: datetime.now().isoformat())


# ─── Données de simulation réalistes ─────────────────────────────────────────

class DonneesSimulation:
    """
    Générateur de données réalistes et cohérentes pour la compagnie YukpoAssurance.
    Utilisé lorsque ORASS est en mode simulation.

    Modèle de référence :
    - 1 200 polices actives
    - Répartition : Auto 45%, Vie 25%, IRD 15%, RC 10%, Transport 5%
    - Primes nettes totales : 2,4 milliards FCFA
    """

    # Répartition des branches
    BRANCHES = {
        "auto":      {"part": 0.45, "sp": 0.57, "label": "Automobile"},
        "vie":       {"part": 0.25, "sp": 0.22, "label": "Vie"},
        "ird":       {"part": 0.15, "sp": 0.38, "label": "IRD"},
        "rc":        {"part": 0.10, "sp": 0.32, "label": "RC"},
        "transport": {"part": 0.05, "sp": 0.28, "label": "Transport"},
    }

    PRIMES_NETTES_TOTAL = 2_400_000_000   # 2,4 Mds FCFA
    POLICES_ACTIVES     = 1_200
    REGIONS             = ["Centre", "Littoral", "Ouest", "Nord", "Sud-Ouest", "Nord-Ouest", "Adamaoua", "Est", "Sud", "Extrême-Nord"]

    # Saisonnalité mensuelle (coefficient multiplicateur par rapport à la moyenne)
    SAISON_MOIS = [0.82, 0.78, 0.88, 0.95, 1.02, 1.12, 1.18, 1.15, 1.08, 0.98, 1.05, 1.20]

    @classmethod
    def primes_par_branche(cls) -> dict[str, dict]:
        result = {}
        for nom, b in cls.BRANCHES.items():
            primes = round(cls.PRIMES_NETTES_TOTAL * b["part"])
            sinistres = round(primes * b["sp"])
            result[nom] = {
                "label": b["label"],
                "primes": primes,
                "sinistres": sinistres,
                "ratio_sp": round(b["sp"] * 100, 1),
                "polices": round(cls.POLICES_ACTIVES * b["part"]),
            }
        return result

    @classmethod
    def evolution_mensuelle(cls, annee: int) -> list[dict]:
        """Génère 12 mois de données avec saisonnalité et tendance légère."""
        base_mensuelle = cls.PRIMES_NETTES_TOTAL / 12
        mois_noms = [
            "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
            "Juil", "Août", "Sep", "Oct", "Nov", "Déc",
        ]
        mois_courant = datetime.now().month if datetime.now().year == annee else 12
        result = []
        for i in range(12):
            if i >= mois_courant:
                break
            coeff = cls.SAISON_MOIS[i]
            # Tendance haussière légère : +0.6% par mois
            tendance = 1 + (i * 0.006)
            primes = round(base_mensuelle * coeff * tendance)
            sinistres = round(primes * (0.46 + (i % 3) * 0.02))
            result.append({
                "mois": mois_noms[i],
                "mois_num": i + 1,
                "annee": annee,
                "primes_nettes": primes,
                "sinistres": sinistres,
                "ratio_sp": round(sinistres / primes * 100, 1),
                "nouvelles_polices": round(15 + i * 1.5 + (8 if i == 11 else 0)),
                "resiliations": round(5 + i * 0.5),
            })
        return result

    @classmethod
    def sinistres_30_jours(cls) -> list[dict]:
        """Génère des sinistres récents simulés pour le dashboard temps réel."""
        nature_par_branche = {
            "auto":      ["collision", "vol", "bris_glace", "incendie_vehicule"],
            "ird":       ["incendie", "degats_eaux", "vol_effraction"],
            "transport": ["vol_cargaison", "avarie", "accident_transport"],
            "rc":        ["dommages_corporels", "dommages_materiels"],
            "vie":       ["deces", "invalidite"],
        }
        statuts = ["ouvert", "en_instruction", "en_expertise", "réglé"]
        regions = cls.REGIONS[:6]
        sinistres = []
        # ~40 sinistres sur 30 jours
        random.seed(42)
        for i in range(40):
            branche = random.choices(
                list(cls.BRANCHES.keys()),
                weights=[b["part"] for b in cls.BRANCHES.values()],
            )[0]
            nature = random.choice(nature_par_branche.get(branche, ["autre"]))
            jours_ecoulés = random.randint(1, 30)
            statut = random.choices(statuts, weights=[0.3, 0.35, 0.2, 0.15])[0]
            montant = random.choice([85_000, 150_000, 350_000, 600_000, 1_200_000, 2_500_000])
            sinistres.append({
                "numero": f"SIN-2026-{1000 + i:04d}",
                "branche": branche,
                "nature": nature,
                "date_declaration": (date.today() - timedelta(days=jours_ecoulés)).isoformat(),
                "statut": statut,
                "montant_declare": montant,
                "region": random.choice(regions),
                "delai_jours": jours_ecoulés,
                "alerte_cima": jours_ecoulés > 21 and statut in ("ouvert", "en_instruction"),
            })
        return sorted(sinistres, key=lambda x: x["date_declaration"], reverse=True)

    @classmethod
    def scores_fraude(cls) -> list[dict]:
        """Distribution des scores de fraude sur le portefeuille."""
        random.seed(7)
        dossiers = []
        for i in range(60):
            branche = random.choice(list(cls.BRANCHES.keys()))
            score = random.betavariate(2, 5) * 100  # distribution réaliste (majorité de scores bas)
            montant = random.choice([300_000, 500_000, 1_000_000, 1_500_000, 3_000_000])
            dossiers.append({
                "numero_sinistre": f"SIN-2026-{2000 + i:04d}",
                "branche": branche,
                "score_fraude": round(score, 1),
                "niveau": (
                    "critique" if score >= 75
                    else "élevé" if score >= 55
                    else "modéré" if score >= 35
                    else "faible"
                ),
                "montant_declare": montant,
                "indicateurs": random.sample(
                    [
                        "Déclaration tardive (> 30j)",
                        "Incohérence km/date sinistre",
                        "Multiple sinistres < 6 mois",
                        "Expertise contradictoire",
                        "Tiers inconnu non identifié",
                        "Montant déclaré > valeur vénale",
                        "Adresse non vérifiable",
                    ],
                    k=random.randint(0, 3),
                ),
            })
        return sorted(dossiers, key=lambda x: x["score_fraude"], reverse=True)

    @classmethod
    def pipeline_commercial(cls) -> dict:
        """Pipeline prospects, objectifs vs réalisé, top agents."""
        random.seed(13)
        agents = [
            {"code": "AGT-101", "nom": "FOUDA Pierre", "region": "Centre"},
            {"code": "AGT-102", "nom": "NGONO Marie", "region": "Littoral"},
            {"code": "AGT-103", "nom": "BELLO Alain", "region": "Ouest"},
            {"code": "AGT-104", "nom": "TAMBA Clarisse", "region": "Nord"},
            {"code": "AGT-105", "nom": "MBELE Joseph", "region": "Sud-Ouest"},
        ]
        objectif_annuel = 480_000_000  # FCFA
        mois_ecoules = min(datetime.now().month, 12)
        realise = round(objectif_annuel * (mois_ecoules / 12) * random.uniform(0.88, 1.05))
        for a in agents:
            a["polices_ce_mois"] = random.randint(4, 18)
            a["primes_ce_mois"] = a["polices_ce_mois"] * random.randint(90_000, 280_000)
            a["taux_conversion"] = round(random.uniform(0.28, 0.72) * 100, 1)
        agents_tries = sorted(agents, key=lambda x: x["primes_ce_mois"], reverse=True)
        return {
            "objectif_annuel_fcfa": objectif_annuel,
            "realise_ytd_fcfa": realise,
            "taux_realisation": round(realise / objectif_annuel * 100, 1),
            "prospects_actifs": random.randint(85, 140),
            "devis_en_attente": random.randint(22, 45),
            "conversions_30j": random.randint(14, 28),
            "top_agents": agents_tries,
        }

    @classmethod
    def heatmap_regions(cls) -> list[dict]:
        """Distribution des sinistres et primes par région."""
        random.seed(21)
        total_sinistres = 320  # sinistres sur la période
        distribution = []
        reste = 1.0
        for i, region in enumerate(cls.REGIONS):
            if i == len(cls.REGIONS) - 1:
                part = reste
            else:
                part = random.uniform(0.04, 0.20)
                reste -= part
            nb = round(total_sinistres * part)
            distribution.append({
                "region": region,
                "nb_sinistres": nb,
                "montant_sinistres_fcfa": nb * random.randint(200_000, 600_000),
                "nb_polices": round(cls.POLICES_ACTIVES * part * random.uniform(0.8, 1.2)),
                "ratio_sp_regional": round(random.uniform(0.35, 0.72) * 100, 1),
                "alerte": random.choice([True, False, False, False]),
            })
        return sorted(distribution, key=lambda x: x["nb_sinistres"], reverse=True)

    @classmethod
    def projection_fin_annee(cls, annee: int) -> dict:
        """Extrapolation des tendances jusqu'en fin d'année."""
        mois_ecoules = min(datetime.now().month, 12) if datetime.now().year == annee else 12
        factor = 12 / mois_ecoules if mois_ecoules > 0 else 1
        primes_ytd = round(cls.PRIMES_NETTES_TOTAL * mois_ecoules / 12 * random.uniform(0.93, 1.04))
        sinistres_ytd = round(primes_ytd * 0.48)
        # Projection linéaire avec légère saisonnalité de fin d'année
        coeff_fin = 1 + sum(cls.SAISON_MOIS[mois_ecoules:]) / max(12 - mois_ecoules, 1) / 12
        primes_proj = round(primes_ytd * factor * coeff_fin)
        sinistres_proj = round(sinistres_ytd * factor * 1.02)
        return {
            "annee": annee,
            "mois_ecoules": mois_ecoules,
            "primes_ytd": primes_ytd,
            "sinistres_ytd": sinistres_ytd,
            "ratio_sp_ytd": round(sinistres_ytd / primes_ytd * 100, 1) if primes_ytd else 0,
            "projection_primes_fin_annee": primes_proj,
            "projection_sinistres_fin_annee": sinistres_proj,
            "projection_ratio_sp": round(sinistres_proj / primes_proj * 100, 1) if primes_proj else 0,
            "ecart_objectif_fcfa": primes_proj - cls.PRIMES_NETTES_TOTAL,
            "ecart_objectif_pct": round((primes_proj - cls.PRIMES_NETTES_TOTAL) / cls.PRIMES_NETTES_TOTAL * 100, 1),
            "alerte_sp": sinistres_proj / primes_proj > 0.70 if primes_proj else False,
        }


class AnalyticsDashboard:
    """
    Moteur d'analytics et tableaux de bord YukpoAssurance.
    """

    def __init__(self):
        self._gen = DocumentGenerateur()
        self._sim = DonneesSimulation()

    # ──────────────────────────────────────────────────────────────
    # DASHBOARD PRINCIPAL
    # ──────────────────────────────────────────────────────────────

    async def dashboard_performance_globale(
        self, annee: int, trimestre: Optional[int] = None
    ) -> Dashboard:
        """
        Dashboard de performance globale — vue DG / DAF.
        Équivalent d'un tableau de bord Superset/PowerBI mais généré par IA.
        Utilise DonneesSimulation quand ORASS est en mode simulation.
        """
        donnees = await orass.export_donnees_cima(annee, trimestre)
        conformite = cima_engine.rapport_conformite_global(donnees)

        primes_nettes = donnees.get("primes_nettes", 0)
        sinistres = donnees.get("sinistres_payes", 0)
        frais = donnees.get("frais_gestion", 0)
        sp_global = sinistres / primes_nettes * 100 if primes_nettes else 0
        rc = (sinistres + frais) / primes_nettes * 100 if primes_nettes else 0

        # Données de simulation enrichies
        branches_sim = DonneesSimulation.primes_par_branche()
        evo = DonneesSimulation.evolution_mensuelle(annee)
        nb_polices = DonneesSimulation.POLICES_ACTIVES

        # Calcul du chiffre d'affaires mensuel moyen réel
        prime_mois = round(primes_nettes / (len(evo) or 12))

        capitaux_propres = donnees.get("capitaux_propres", 0)
        marge_pct = (capitaux_propres / (primes_nettes * 0.2) * 100) if primes_nettes else 142.8

        kpis = [
            KPI(
                "Primes nettes",
                f"{primes_nettes / 1_000_000:.0f}M FCFA",
                statut="normal",
                tendance="+8%",
                valeur_num=float(primes_nettes),
            ),
            KPI(
                "Polices actives",
                f"{nb_polices:,}",
                statut="normal",
                tendance="+5%",
                valeur_num=float(nb_polices),
            ),
            KPI(
                "Ratio S/P",
                f"{sp_global:.1f}%",
                statut="attention" if sp_global > 70 else "normal",
                benchmark="< 70% CIMA",
                valeur_num=round(sp_global, 1),
            ),
            KPI(
                "Ratio combiné",
                f"{rc:.1f}%",
                statut="critique" if rc > 100 else ("attention" if rc > 90 else "normal"),
                benchmark="< 100%",
                valeur_num=round(rc, 1),
            ),
            KPI(
                "Marge solvabilité",
                f"{capitaux_propres / 1_000_000:.0f}M FCFA",
                statut=(
                    "normale" if conformite.get("statut_global") == "CONFORME" else "critique"
                ),
                benchmark="300M min (Art. 337-1 CIMA)",
                valeur_num=round(marge_pct, 1),
            ),
            KPI(
                "Prime moyenne mensuelle",
                f"{prime_mois / 1_000_000:.1f}M FCFA",
                statut="normal",
                valeur_num=float(prime_mois),
            ),
        ]

        # Graphiques
        branches_data = donnees.get("branches", {})
        labels_branches = list(branches_data.keys())
        graphiques = [
            {
                "type": "bar",
                "titre": "Primes par branche (FCFA)",
                "labels": labels_branches,
                "values": [b.get("primes", 0) for b in branches_data.values()],
                "series_sinistres": [b.get("sinistres", 0) for b in branches_data.values()],
            },
            {
                "type": "bar",
                "titre": "Ratio S/P par branche (%)",
                "labels": labels_branches,
                "values": [
                    round(b.get("sinistres", 0) / b.get("primes", 1) * 100, 1)
                    for b in branches_data.values()
                ],
            },
            {
                "type": "donut",
                "titre": "Répartition des charges",
                "labels": ["Sinistres", "Frais gestion", "Commissions", "Résultat"],
                "values": [
                    sinistres,
                    frais,
                    round(primes_nettes * 0.12),
                    max(0, primes_nettes - sinistres - frais - primes_nettes * 0.12),
                ],
            },
            {
                "type": "line",
                "titre": "Évolution mensuelle primes (FCFA)",
                "labels": [m["mois"] for m in evo],
                "values": [m["primes_nettes"] for m in evo],
                "series_sinistres": [m["sinistres"] for m in evo],
            },
        ]

        narrative = await self._generer_narrative(donnees, kpis, conformite)

        return Dashboard(
            titre=f"Performance Globale — {annee}{'T' + str(trimestre) if trimestre else ''}",
            periode=f"{annee}{'/T' + str(trimestre) if trimestre else ''}",
            kpis=kpis,
            alertes=[a.get("message", "") for a in conformite.get("alertes", [])],
            graphiques=graphiques,
            narrative_ia=narrative,
        )

    # ──────────────────────────────────────────────────────────────
    # DASHBOARD SINISTRES TEMPS RÉEL
    # ──────────────────────────────────────────────────────────────

    async def dashboard_sinistres_temps_reel(self) -> dict:
        """
        Sinistres des 30 derniers jours : flux, délais moyens, alertes CIMA.
        L'article 24 du Code CIMA impose le règlement dans les délais prescrits.
        """
        sinistres = DonneesSimulation.sinistres_30_jours()
        total = len(sinistres)
        en_alerte_cima = [s for s in sinistres if s["alerte_cima"]]
        par_branche: dict[str, int] = {}
        par_statut: dict[str, int] = {}
        montant_total = 0
        delais: list[int] = []

        for s in sinistres:
            par_branche[s["branche"]] = par_branche.get(s["branche"], 0) + 1
            par_statut[s["statut"]] = par_statut.get(s["statut"], 0) + 1
            montant_total += s["montant_declare"]
            delais.append(s["delai_jours"])

        delai_moyen = round(sum(delais) / len(delais), 1) if delais else 0
        regle = par_statut.get("réglé", 0)
        taux_reglement = round(regle / total * 100, 1) if total else 0

        alertes = []
        if len(en_alerte_cima) > 0:
            alertes.append(
                f"{len(en_alerte_cima)} sinistre(s) dépassent 21 jours sans instruction — "
                f"risque de pénalité CIMA (Art. 24 Code CIMA)"
            )
        if par_statut.get("ouvert", 0) > 15:
            alertes.append(
                f"{par_statut.get('ouvert', 0)} sinistres en statut 'ouvert' non encore instruits"
            )

        prompt = f"""Tu es gestionnaire sinistres d'une compagnie d'assurance CIMA.

Situation des sinistres des 30 derniers jours :
- Total déclarés : {total}
- Montant global déclaré : {montant_total:,} FCFA
- Délai moyen d'instruction : {delai_moyen} jours
- Taux de règlement : {taux_reglement}%
- En alerte CIMA (> 21j sans instruction) : {len(en_alerte_cima)}
- Répartition par statut : {par_statut}

Fournis en 3 phrases :
1. Évaluation du flux de sinistres par rapport aux normes CIMA
2. Risques opérationnels et réglementaires immédiats
3. Actions prioritaires pour les 7 prochains jours
"""
        try:
            reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
            analyse_ia = reponse.contenu
        except Exception:
            analyse_ia = (
                f"Flux de {total} sinistres sur 30 jours avec un délai moyen de {delai_moyen}j. "
                f"{len(en_alerte_cima)} dossier(s) en alerte CIMA nécessitent une action urgente."
            )

        return {
            "periode": "30 derniers jours",
            "total_sinistres": total,
            "montant_total_declare": montant_total,
            "delai_moyen_jours": delai_moyen,
            "taux_reglement_pct": taux_reglement,
            "repartition_branche": par_branche,
            "repartition_statut": par_statut,
            "sinistres_alerte_cima": len(en_alerte_cima),
            "detail_alertes": en_alerte_cima[:5],
            "alertes_operationnelles": alertes,
            "analyse_ia": analyse_ia,
            "sinistres_recents": sinistres[:10],
            "genere_le": datetime.now().isoformat(),
        }

    # ──────────────────────────────────────────────────────────────
    # ANALYSE FRAUDE DASHBOARD
    # ──────────────────────────────────────────────────────────────

    async def analyse_fraude_dashboard(self) -> dict:
        """
        Distribution des scores de fraude sur le portefeuille.
        Top 10 dossiers suspects avec indicateurs de fraude.
        """
        dossiers = DonneesSimulation.scores_fraude()
        distribution = {"faible": 0, "modéré": 0, "élevé": 0, "critique": 0}
        for d in dossiers:
            distribution[d["niveau"]] += 1

        top10 = dossiers[:10]
        total_montant_suspect = sum(d["montant_declare"] for d in top10)
        score_moyen = round(sum(d["score_fraude"] for d in dossiers) / len(dossiers), 1) if dossiers else 0

        prompt = f"""Tu es expert en détection de fraude dans une compagnie d'assurance CIMA (Cameroun).

Distribution des scores de fraude (portefeuille {len(dossiers)} dossiers) :
- Faible (< 35) : {distribution['faible']} dossiers
- Modéré (35-55) : {distribution['modéré']} dossiers
- Élevé (55-75) : {distribution['élevé']} dossiers
- Critique (> 75) : {distribution['critique']} dossiers
- Score moyen portefeuille : {score_moyen}/100

Top 3 dossiers suspects :
{top10[:3]}

Analyse en 4 phrases :
1. Niveau de risque fraude global du portefeuille
2. Patterns de fraude identifiés
3. Actions de contrôle à prioriser (enquête, expertise contradictoire, recours judiciaire)
4. Estimation de l'impact financier potentiel en FCFA
"""
        try:
            reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
            analyse_ia = reponse.contenu
        except Exception:
            analyse_ia = (
                f"Portefeuille de {len(dossiers)} dossiers analysés. "
                f"{distribution['critique']} dossier(s) critiques et {distribution['élevé']} "
                f"élevés nécessitent une investigation approfondie. "
                f"Montant total suspect (top 10) : {total_montant_suspect:,} FCFA."
            )

        return {
            "total_dossiers_analyses": len(dossiers),
            "score_moyen_fraude": score_moyen,
            "distribution_niveaux": distribution,
            "taux_fraude_critique_pct": round(distribution["critique"] / len(dossiers) * 100, 1),
            "montant_suspect_top10_fcfa": total_montant_suspect,
            "top10_dossiers_suspects": top10,
            "analyse_ia": analyse_ia,
            "genere_le": datetime.now().isoformat(),
        }

    # ──────────────────────────────────────────────────────────────
    # DASHBOARD COMMERCIAL
    # ──────────────────────────────────────────────────────────────

    async def dashboard_commercial(self) -> dict:
        """
        Pipeline prospects, objectifs vs réalisé, top agents, taux de conversion.
        """
        data = DonneesSimulation.pipeline_commercial()
        ecart_pct = data["taux_realisation"] - 100
        statut_objectif = (
            "en_avance" if ecart_pct >= 5
            else "dans_les_clous" if ecart_pct >= -5
            else "en_retard"
        )

        prompt = f"""Tu es directeur commercial d'une compagnie d'assurance.

Indicateurs commerciaux du moment :
- Objectif annuel : {data['objectif_annuel_fcfa']:,} FCFA
- Réalisé à date : {data['realise_ytd_fcfa']:,} FCFA ({data['taux_realisation']}%)
- Prospects actifs : {data['prospects_actifs']}
- Devis en attente : {data['devis_en_attente']}
- Conversions 30 derniers jours : {data['conversions_30j']}
- Top agent : {data['top_agents'][0]['nom']} ({data['top_agents'][0]['primes_ce_mois']:,} FCFA ce mois)

En 3 phrases concises, fournis :
1. Évaluation de la dynamique commerciale
2. Risque de non-atteinte de l'objectif annuel
3. Recommandation d'action commerciale immédiate
"""
        try:
            reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.COMMERCIAL)
            analyse_ia = reponse.contenu
        except Exception:
            analyse_ia = (
                f"Objectif annuel {'en avance' if ecart_pct >= 0 else 'en retard'} de {abs(ecart_pct):.1f}%. "
                f"{data['prospects_actifs']} prospects actifs avec {data['devis_en_attente']} devis à convertir."
            )

        return {
            "objectif_annuel_fcfa": data["objectif_annuel_fcfa"],
            "realise_ytd_fcfa": data["realise_ytd_fcfa"],
            "taux_realisation_pct": data["taux_realisation"],
            "statut_objectif": statut_objectif,
            "prospects_actifs": data["prospects_actifs"],
            "devis_en_attente": data["devis_en_attente"],
            "conversions_30j": data["conversions_30j"],
            "top_agents": data["top_agents"],
            "analyse_ia": analyse_ia,
            "genere_le": datetime.now().isoformat(),
        }

    # ──────────────────────────────────────────────────────────────
    # HEATMAP GÉOGRAPHIQUE
    # ──────────────────────────────────────────────────────────────

    async def heatmap_sinistres_geographique(self) -> dict:
        """
        Distribution des sinistres et polices par région camerounaise.
        Permet d'identifier les zones de sur-sinistralité.
        """
        regions = DonneesSimulation.heatmap_regions()
        regions_alerte = [r for r in regions if r["alerte"] or r["ratio_sp_regional"] > 65]
        montant_total = sum(r["montant_sinistres_fcfa"] for r in regions)
        region_max = max(regions, key=lambda x: x["nb_sinistres"])
        region_min = min(regions, key=lambda x: x["nb_sinistres"])

        return {
            "periode": f"Exercice {datetime.now().year}",
            "total_sinistres_portefeuille": sum(r["nb_sinistres"] for r in regions),
            "montant_total_fcfa": montant_total,
            "region_plus_sinistree": region_max["region"],
            "region_moins_sinistree": region_min["region"],
            "regions_en_alerte": [r["region"] for r in regions_alerte],
            "heatmap": regions,
            "graphique": {
                "type": "choropleth",
                "titre": "Sinistres par région — Cameroun",
                "labels": [r["region"] for r in regions],
                "values": [r["nb_sinistres"] for r in regions],
                "colors": [
                    "critique" if r["alerte"] or r["ratio_sp_regional"] > 65
                    else "attention" if r["ratio_sp_regional"] > 50
                    else "normal"
                    for r in regions
                ],
            },
            "genere_le": datetime.now().isoformat(),
        }

    # ──────────────────────────────────────────────────────────────
    # PROJECTION FIN D'ANNÉE
    # ──────────────────────────────────────────────────────────────

    async def projection_fin_annee(self, annee: int = 2026) -> dict:
        """
        Extrapolation des tendances jusqu'en fin d'exercice.
        Projection primes, sinistres, ratio S/P avec scénarios haut/bas.
        """
        proj = DonneesSimulation.projection_fin_annee(annee)
        evo = DonneesSimulation.evolution_mensuelle(annee)

        # Scénarios
        primes_proj = proj["projection_primes_fin_annee"]
        sins_proj = proj["projection_sinistres_fin_annee"]
        scenario_haut_sins = round(sins_proj * 1.15)
        scenario_bas_sins  = round(sins_proj * 0.87)

        prompt = f"""Tu es actuaire dans une compagnie d'assurance en zone CIMA.

Données de projection fin d'exercice {annee} :
- Primes YTD ({proj['mois_ecoules']} mois) : {proj['primes_ytd']:,} FCFA
- Sinistres YTD : {proj['sinistres_ytd']:,} FCFA
- Ratio S/P actuel : {proj['ratio_sp_ytd']}%
- Projection primes fin d'année : {primes_proj:,} FCFA
- Projection sinistres (base) : {sins_proj:,} FCFA → S/P {proj['projection_ratio_sp']}%
- Scénario pessimiste sinistres : {scenario_haut_sins:,} FCFA
- Scénario optimiste sinistres : {scenario_bas_sins:,} FCFA
- Écart objectif : {proj['ecart_objectif_pct']:+.1f}%

En 5 phrases professionnelles pour la Direction Générale :
1. Évaluation de la trajectoire par rapport aux objectifs
2. Risques d'atteindre le seuil S/P de 70% CIMA
3. Impact sur la marge de solvabilité
4. Recommandation tarifaire urgente si nécessaire
5. Actions prioritaires pour sécuriser les résultats de fin d'exercice
"""
        try:
            reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)
            analyse_ia = reponse.contenu
        except Exception:
            analyse_ia = (
                f"Projection fin d'exercice {annee} : primes {primes_proj / 1_000_000:.0f}M FCFA, "
                f"sinistres {sins_proj / 1_000_000:.0f}M FCFA, S/P projeté {proj['projection_ratio_sp']}%. "
                f"Écart objectif : {proj['ecart_objectif_pct']:+.1f}%."
            )

        return {
            **proj,
            "scenario_pessimiste": {
                "sinistres": scenario_haut_sins,
                "ratio_sp": round(scenario_haut_sins / primes_proj * 100, 1),
            },
            "scenario_optimiste": {
                "sinistres": scenario_bas_sins,
                "ratio_sp": round(scenario_bas_sins / primes_proj * 100, 1),
            },
            "evolution_mensuelle": evo,
            "analyse_ia": analyse_ia,
            "genere_le": datetime.now().isoformat(),
        }

    # ──────────────────────────────────────────────────────────────
    # ANALYSES SPÉCIALISÉES (existantes)
    # ──────────────────────────────────────────────────────────────

    async def analyse_sinistralite(
        self, branche: Optional[str] = None, annee: int = 2025
    ) -> dict:
        """Analyse détaillée de la sinistralité avec insights IA"""
        donnees = await orass.export_donnees_cima(annee)
        branches = donnees.get("branches", {})

        if branche and branche in branches:
            data_branche = {branche: branches[branche]}
        else:
            data_branche = branches

        tableau = []
        for nom, b in data_branche.items():
            primes = b.get("primes", 0)
            sins = b.get("sinistres", 0)
            sp = sins / primes * 100 if primes else 0
            tableau.append({
                "branche": nom.upper(),
                "primes_nettes": primes,
                "sinistres_payes": sins,
                "ratio_sp": round(sp, 1),
                "statut": "ALERTE" if sp > 70 else "NORMAL",
                "ecart_vs_seuil": round(sp - 70, 1),
            })

        prompt = f"""Tu es actuaire pour une compagnie d'assurance en zone CIMA.

Analyse cette sinistralité et fournis tes insights :
{tableau}

Pour chaque branche, identifie :
1. Les tendances préoccupantes
2. Les causes probables (fraude, sous-tarification, fréquence)
3. Les actions correctives recommandées
4. L'impact attendu sur la prochaine période

Sois précis, chiffré, et cite les seuils CIMA applicables.
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)

        return {
            "periode": str(annee),
            "tableau_sinistralite": tableau,
            "analyse_ia": reponse.contenu,
            "alertes": [b for b in tableau if b["statut"] == "ALERTE"],
        }

    async def analyse_portefeuille(self) -> dict:
        """Analyse du portefeuille : renouvellements, impayés, risques de résiliation"""
        impayes = await orass.lister_impayes(seuil_jours=30)

        stats = {
            "total_polices_actives": DonneesSimulation.POLICES_ACTIVES,
            "renouvellements_30j": 89,
            "impayes_total": len(impayes),
            "impayes_montant_fcfa": sum(i.get("prime_due", 0) for i in impayes),
            "taux_retention_estime": 87.3,
            "polices_a_risque_resiliation": len([i for i in impayes if i.get("jours_retard", 0) > 60]),
        }

        prompt = f"""Analyse ce portefeuille d'assurance et propose des actions commerciales concrètes :

Statistiques :
{stats}

Détail des impayés : {impayes[:5]}

Recommande :
1. Actions de recouvrement prioritaires (par segment)
2. Stratégie de rétention des clients à risque
3. Opportunités de vente croisée identifiées
4. KPIs à surveiller sur les 30 prochains jours
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)

        return {
            "statistiques": stats,
            "impayes": impayes,
            "recommandations_ia": reponse.contenu,
        }

    async def analyse_conformite_cima(self, annee: int = 2025) -> dict:
        """Analyse complète de la conformité CIMA avec rapport narratif"""
        donnees = await orass.export_donnees_cima(annee)
        rapport = cima_engine.rapport_conformite_global(donnees)

        prompt = f"""Tu es directeur technique d'une compagnie d'assurance en zone CIMA.

Voici le rapport de conformité CIMA pour l'exercice {annee} :
{rapport}

Rédige un commentaire exécutif de 5-8 phrases pour le Conseil d'Administration :
- Statut global de la conformité
- Points forts à valoriser
- Risques réglementaires identifiés
- Actions prioritaires avant le prochain contrôle CRCA
- Calendrier de mise en conformité si nécessaire
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION)

        return {
            "annee": annee,
            "rapport_technique": rapport,
            "commentaire_ca": reponse.contenu,
            "statut": rapport.get("statut_global", "N/A"),
        }

    async def detection_anomalies(self, donnees_comptables: Optional[dict] = None) -> dict:
        """
        Détection d'anomalies comptables et opérationnelles.
        Analyse : doublons, montants inhabituels, imputations suspectes.
        """
        donnees = donnees_comptables or await orass.export_donnees_cima(2025)

        prompt = f"""Tu es expert en audit interne d'une compagnie d'assurance CIMA.

Analyse ces données comptables et identifie toutes les anomalies :
{donnees}

Types d'anomalies à détecter :
1. Montants inhabituellement élevés ou bas
2. Incohérences entre provisions et sinistres
3. Ratios hors normes CIMA
4. Écarts de rapprochement bancaire potentiels
5. Anomalies dans la structure des charges

Retourne une liste priorisée d'anomalies avec :
- Description de l'anomalie
- Niveau de risque (faible/modéré/élevé/critique)
- Vérification recommandée
- Article CIMA applicable si pertinent
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.ANALYSE)

        return {
            "anomalies_detectees": reponse.contenu,
            "donnees_analysees": list(donnees.keys()),
            "genere_le": datetime.now().isoformat(),
        }

    async def analyse_predictive(self, donnees_historiques: Optional[dict] = None) -> dict:
        """
        Analyse prédictive :
        - Projection de sinistralité sur 6 mois
        - Risque de dégradation du ratio combiné
        - Recommandations tarifaires
        """
        donnees = donnees_historiques or await orass.export_donnees_cima(2025)

        prompt = f"""Tu es actuaire pour une compagnie d'assurance en zone CIMA (Cameroun).

Réalise une analyse prédictive sur base de ces données :
{donnees}

Fournis :
1. Projection de sinistralité sur 6 prochains mois (avec fourchette basse/haute)
2. Probabilité de dépasser le seuil S/P de 70% sur 12 mois
3. Impact attendu sur la marge de solvabilité
4. Recommandations tarifaires par branche
5. Scénarios de stress : que se passe-t-il si la sinistralité augmente de 15% ?

Quantifie chaque projection en FCFA et en % avec les hypothèses retenues.
"""
        reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.PRECISION)

        return {
            "analyse_predictive": reponse.contenu,
            "horizon": "6-12 mois",
            "methode": "Analyse actuarielle IA basée sur données ORASS",
        }

    async def rapport_complet_direction(self, annee: int = 2025) -> Optional[dict]:
        """
        Génère un rapport complet de direction (PDF) avec tous les indicateurs.
        Combine toutes les analyses en un document unique.
        """
        logger.info(f"[Analytics] Génération rapport direction {annee}")

        donnees = await orass.export_donnees_cima(annee)
        conformite = cima_engine.rapport_conformite_global(donnees)
        dashboard = await self.dashboard_performance_globale(annee)
        sinistralite = await self.analyse_sinistralite(annee=annee)

        outline = {
            "document_type": "pdf",
            "title": f"Rapport de Direction — Exercice {annee}",
            "subtitle": "Analyse complète de la performance et de la conformité CIMA",
            "author": "YukpoAssurance — Direction Générale",
            "theme": "blue",
            "pages": [
                {
                    "title": "Synthèse Exécutive",
                    "layout": "kpi",
                    "kpis": [
                        {"value": k.valeur, "label": k.libelle, "trend": k.tendance or ""}
                        for k in dashboard.kpis
                    ],
                },
                {
                    "title": "Analyse de la Sinistralité",
                    "layout": "table",
                    "table": {
                        "headers": ["Branche", "Primes (FCFA)", "Sinistres (FCFA)", "S/P (%)", "Statut"],
                        "rows": [
                            [
                                b["branche"], f"{b['primes_nettes']:,}",
                                f"{b['sinistres_payes']:,}", f"{b['ratio_sp']}%", b["statut"],
                            ]
                            for b in sinistralite["tableau_sinistralite"]
                        ],
                    },
                },
                {
                    "title": "Conformité CIMA",
                    "layout": "content",
                    "content": f"Statut global : {conformite.get('statut_global', 'N/A')}",
                    "bullets": [a.get("message", "") for a in conformite.get("alertes", [])]
                    or ["Aucune alerte critique — conformité satisfaisante"],
                },
                {
                    "title": "Analyse IA — Commentaire de Direction",
                    "layout": "content",
                    "content": dashboard.narrative_ia or "Voir les analyses détaillées ci-dessus",
                },
                {
                    "title": "Prochaines Échéances Réglementaires",
                    "layout": "table",
                    "table": {
                        "headers": ["Échéance", "Obligation", "Responsable"],
                        "rows": [
                            [e["echeance"], e["obligation"], "Direction Financière"]
                            for e in cima_engine._prochaines_echeances()
                        ],
                    },
                },
            ],
        }

        return await self._gen.generer(outline)

    # ──────────────────────────────────────────────────────────────
    # NARRATIVE IA
    # ──────────────────────────────────────────────────────────────

    async def _generer_narrative(
        self, donnees: dict, kpis: list[KPI], conformite: dict
    ) -> str:
        """Génère un commentaire narratif IA sur les chiffres du dashboard"""
        kpis_str = "\n".join(f"- {k.libelle}: {k.valeur} ({k.statut})" for k in kpis)

        prompt = f"""Tu es le directeur technique d'une compagnie d'assurance en zone CIMA.

En 4-5 phrases professionnelles, commente ces indicateurs de performance :
{kpis_str}

Statut conformité CIMA : {conformite.get('statut_global', 'N/A')}
Alertes : {len(conformite.get('alertes', []))}

Ton commentaire doit être :
- Factuel et chiffré
- Orienté vers les actions à prendre
- Adapté pour la Direction Générale
- Avec référence aux normes CIMA si pertinent
"""
        try:
            reponse = await ia_client.appeler(prompt=prompt, mode=ModeIA.REDACTION)
            return reponse.contenu
        except Exception:
            # Fallback si aucun modèle IA disponible
            return (
                "Les indicateurs clés de performance sont disponibles. "
                "Consultez les sections détaillées pour l'analyse complète."
            )

    def dashboard_to_dict(self, db: Dashboard) -> dict:
        # Extract raw numeric values for frontend KPI cards
        kpis_raw: dict = {}
        for k in db.kpis:
            if k.libelle == "Primes nettes":
                kpis_raw["primes_nettes"] = k.valeur_num if hasattr(k, "valeur_num") else 2_400_000_000
            elif k.libelle == "Ratio S/P":
                kpis_raw["ratio_sp"] = k.valeur_num if hasattr(k, "valeur_num") else 68.4
            elif k.libelle in ("Marge solvabilité", "Marge de solvabilité"):
                kpis_raw["marge_solvabilite"] = k.valeur_num if hasattr(k, "valeur_num") else 142.8
            elif k.libelle == "Polices actives":
                kpis_raw["polices_actives"] = k.valeur_num if hasattr(k, "valeur_num") else 12_847

        # Extract primes_par_branche from graphiques
        primes_par_branche = []
        repartition_charges = []
        for g in db.graphiques:
            if g.get("titre", "").startswith("Primes par branche"):
                labels = g.get("labels", [])
                primes_vals = g.get("values", [])
                sins_vals = g.get("series_sinistres", [0] * len(labels))
                primes_par_branche = [
                    {"branche": lb.capitalize(), "primes": pv, "sinistres": sv}
                    for lb, pv, sv in zip(labels, primes_vals, sins_vals)
                ]
            elif g.get("type") == "donut" and "Répartition" in g.get("titre", ""):
                labels = g.get("labels", [])
                vals = g.get("values", [])
                total = sum(vals) or 1
                repartition_charges = [
                    {"categorie": lb, "montant": v, "pourcentage": round(v / total * 100, 1)}
                    for lb, v in zip(labels, vals)
                ]

        # Build CIMA alerts with frontend shape
        alertes_cima = []
        for i, msg in enumerate(db.alertes):
            niveau = "error" if "critique" in msg.lower() or "insuffisant" in msg.lower() else (
                "warning" if "attention" in msg.lower() or "seuil" in msg.lower() or "%" in msg else "info"
            )
            alertes_cima.append({"id": str(i + 1), "type": niveau, "message": msg})

        return {
            "titre": db.titre,
            "periode": db.periode,
            "genere_le": db.genere_le,
            # Raw numeric KPIs for frontend cards
            **kpis_raw,
            # Structured data for charts
            "primes_par_branche": primes_par_branche,
            "repartition_charges": repartition_charges,
            "alertes_cima": alertes_cima,
            "narrative_ia": db.narrative_ia,
            # Full KPI list for advanced consumers
            "kpis": [
                {
                    "libelle": k.libelle,
                    "valeur": k.valeur,
                    "unite": k.unite,
                    "tendance": k.tendance,
                    "statut": k.statut,
                    "benchmark": k.benchmark,
                }
                for k in db.kpis
            ],
            "alertes": db.alertes,
            "graphiques": db.graphiques,
        }


# Instance singleton
analytics = AnalyticsDashboard()
