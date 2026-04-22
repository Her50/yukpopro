"""
TrendPulse — YukpoAssurance (portage complet de yukpomnang2/trend_aggregator_service.rs)
Collecte multi-sources : SerpAPI (Google Trends), YouTube Data API, NewsAPI, signaux internes.
Scoring personnalisé par secteur d'activité et profil commercial de l'entreprise.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger("yukpo.trends")

# ─────────────────────────────────────────────────────────────
# Modèles de données (miroir exact de yukpomnang2)
# ─────────────────────────────────────────────────────────────

@dataclass
class ProduitMatch:
    produit_id: int
    produit_nom: str
    service_id: int
    service_nom: str
    score_match: float
    prix_actuel: float
    est_promo: bool


@dataclass
class ActionRecommandee:
    type_action: str            # create_promo | launch_campaign | schedule_post | none
    titre: str
    description: str
    roas_estime: Optional[float] = None
    budget_suggere_fcfa: Optional[int] = None
    route: Optional[str] = None


@dataclass
class Tendance:
    id: str
    sujet: str
    region: str
    score_social: float         # 0-100
    score_commerce: float       # 0-100
    score_opportunite: float    # 0-100 (score final pondéré)
    momentum_pct: float         # variation vs période précédente
    categories: List[str]
    sources: List[str]
    periode: str
    produits_matches: List[ProduitMatch] = field(default_factory=list)
    action_recommandee: Optional[ActionRecommandee] = None
    resume: str = ""
    recommandations: List[str] = field(default_factory=list)
    prevision_j3: Optional[float] = None    # score prévu dans 3 jours
    confiance_prevision: Optional[float] = None


@dataclass
class TendancePersonnalite:
    """Personnalité/célébrité en tendance (politique, sport, music, business)."""
    nom: str
    mentions: int
    domaine: str        # politique | sport | musique | business | media
    momentum_pct: float
    sources: List[str]


@dataclass
class TendanceSecteur:
    """Secteur économique en tendance."""
    secteur: str
    croissance_pct: float
    top_sujet: str
    regions: List[str]


@dataclass
class PulseTendances:
    region: str
    periode: str
    genere_le: str
    tendances: List[Tendance]
    tendances_personnalisees: List[Tendance]    # scorées selon profil compagnie
    personnalites: List[TendancePersonnalite]
    top_secteurs: List[TendanceSecteur]
    tendances_en_hausse: List[str]
    top_categories: List[str]
    resume_executif: str


# ─────────────────────────────────────────────────────────────
# Contexte commercial utilisateur (portage de user_context_service.rs)
# ─────────────────────────────────────────────────────────────

@dataclass
class ProduitContexte:
    id: int
    nom: str
    categorie: str
    prix: float
    est_promo: bool
    description: Optional[str] = None


@dataclass
class ServiceContexte:
    id: int
    nom: str
    secteur: str
    ville: str
    produits: List[ProduitContexte] = field(default_factory=list)


@dataclass
class SignalPub:
    campagne_id: int
    plateforme: str
    depenses_fcfa: float
    roas: Optional[float]


@dataclass
class ContexteCommercial:
    """Profil commercial de la compagnie connectée — utilisé pour personnaliser les tendances."""
    compagnie_id: int
    secteur: str
    ville: str
    services: List[ServiceContexte] = field(default_factory=list)
    signaux_pub: List[SignalPub] = field(default_factory=list)
    a_comptes_sociaux: bool = False
    a_meta_ads: bool = False
    nb_produits_total: int = 0


# ─────────────────────────────────────────────────────────────
# Catalogue de référence sectorielle (veille CIMA + signaux marché)
# ─────────────────────────────────────────────────────────────

TENDANCES_BASE: Dict[str, List[Dict]] = {
    "assurance": [
        {
            "sujet": "Assurance auto obligatoire — contrôles renforcés",
            "categories": ["assurance_auto", "réglementation", "cima"],
            "sources": ["google", "presse"],
            "score_social": 65, "score_commerce": 80, "score_opportunite": 85,
            "resume": "Les autorités intensifient les contrôles. Opportunité de communication sur la conformité.",
            "recommandations": [
                "Publier sur les obligations légales de l'assurance auto",
                "Promouvoir la souscription en ligne",
                "Rappeler les sanctions en cas de défaut",
            ],
        },
        {
            "sujet": "Mobile Money — paiement de primes en hausse",
            "categories": ["fintech", "paiement", "assurance_vie"],
            "sources": ["linkedin", "twitter"],
            "score_social": 72, "score_commerce": 88, "score_opportunite": 90,
            "resume": "L'adoption du paiement de primes via MTN/Orange croît fortement.",
            "recommandations": [
                "Communiquer sur les options Mobile Money",
                "Campagne de réabonnement en ligne",
                "Mettre en avant la simplicité du processus",
            ],
        },
        {
            "sujet": "Sinistres climatiques — inondations saison des pluies",
            "categories": ["sinistres", "assurance_mrh", "climatique"],
            "sources": ["google", "presse", "facebook"],
            "score_social": 78, "score_commerce": 75, "score_opportunite": 82,
            "resume": "Saison des pluies → sinistres MRH et auto. Opportunité MRH.",
            "recommandations": [
                "Campagne de sensibilisation assurance MRH",
                "Rappel délais déclaration (Art. 12 CIMA)",
                "Guide : que faire en cas d'inondation ?",
            ],
        },
        {
            "sujet": "Assurance vie — retraite et planification financière",
            "categories": ["assurance_vie", "épargne", "retraite"],
            "sources": ["linkedin", "google"],
            "score_social": 55, "score_commerce": 70, "score_opportunite": 78,
            "resume": "Montée d'intérêt pour la prévoyance et la retraite. Cible : 35-55 ans.",
            "recommandations": [
                "Contenu éducatif sur l'épargne-retraite",
                "Témoignages clients",
                "Calculateur de prévoyance interactif",
            ],
        },
        {
            "sujet": "Digitalisation des sinistres — déclaration en ligne",
            "categories": ["digital", "sinistres", "expérience_client"],
            "sources": ["linkedin", "twitter"],
            "score_social": 60, "score_commerce": 82, "score_opportunite": 88,
            "resume": "Les clients réclament des services digitaux. Déclaration en ligne = critère de choix.",
            "recommandations": [
                "Présenter les outils digitaux de la compagnie",
                "Tutoriel : déclarer un sinistre en ligne",
                "Mettre en avant les délais CIMA (Art. 12-ter : 45 jours)",
            ],
        },
    ],
    "banque": [
        {
            "sujet": "Crédit PME — financement de l'entrepreneuriat",
            "categories": ["crédit", "pme", "entrepreneuriat"],
            "sources": ["linkedin", "facebook"],
            "score_social": 70, "score_commerce": 85, "score_opportunite": 88,
            "resume": "Fort appétit pour les crédits PME.",
            "recommandations": ["Webinaire crédits entreprises", "Témoignages entrepreneurs", "Conditions simplifiées"],
        },
        {
            "sujet": "Application bancaire mobile — concurrence fintech",
            "categories": ["mobile", "digital", "fintech"],
            "sources": ["twitter", "google"],
            "score_social": 75, "score_commerce": 80, "score_opportunite": 85,
            "resume": "Les fintechs captent des parts de marché.",
            "recommandations": ["Promouvoir l'app mobile", "Mettre en avant la sécurité", "Comparer les services"],
        },
    ],
    "sante": [
        {
            "sujet": "Prévention paludisme — saison haute",
            "categories": ["prévention", "santé_publique", "paludisme"],
            "sources": ["facebook", "whatsapp"],
            "score_social": 80, "score_commerce": 65, "score_opportunite": 75,
            "resume": "Pic saisonnier du paludisme. Opportunité cliniques/hôpitaux.",
            "recommandations": ["Campagne de sensibilisation", "Offre de dépistage", "Conseils prévention"],
        },
    ],
    "microfinance": [
        {
            "sujet": "Tontines digitales — épargne collaborative en ligne",
            "categories": ["épargne", "digital", "communauté"],
            "sources": ["whatsapp", "facebook"],
            "score_social": 72, "score_commerce": 78, "score_opportunite": 82,
            "resume": "Les tontines migrent vers le digital.",
            "recommandations": ["Lancer un produit tontine digital", "Communication sur la sécurité", "Webinaire épargne"],
        },
    ],
    "commerce": [
        {
            "sujet": "E-commerce local — boom des achats en ligne",
            "categories": ["e-commerce", "digital", "livraison"],
            "sources": ["google", "facebook", "instagram"],
            "score_social": 82, "score_commerce": 90, "score_opportunite": 88,
            "resume": "Les consommateurs africains adoptent massivement le shopping en ligne.",
            "recommandations": ["Créer une boutique en ligne", "Offrir la livraison gratuite", "Mettre en avant les promos"],
        },
    ],
}

REGIONS = {
    "CM": "Cameroun", "SN": "Sénégal", "CI": "Côte d'Ivoire",
    "NG": "Nigéria", "BF": "Burkina Faso", "ML": "Mali", "ALL": "Afrique CIMA",
}

# Scores d'engagement horaires (données Afrique subsaharienne — source yukpomnang2)
SCORES_HORAIRES: List[float] = [
    0.1, 0.05, 0.03, 0.02, 0.02, 0.05,   # 0h-5h
    0.3, 0.5, 0.65, 0.7, 0.7, 0.75,       # 6h-11h
    0.8, 0.75, 0.7, 0.75, 0.8, 0.85,      # 12h-17h
    0.95, 0.9, 0.85, 0.7, 0.5, 0.3,       # 18h-23h (pic 18h-20h)
]


# ─────────────────────────────────────────────────────────────
# Agrégateur externe — SerpAPI / YouTube / NewsAPI
# ─────────────────────────────────────────────────────────────

class AgregateurExternes:
    """Collecte les tendances depuis les APIs externes (portage de trend_aggregator_service.rs)."""

    def __init__(
        self,
        serpapi_key: str = "",
        youtube_api_key: str = "",
        newsapi_key: str = "",
    ):
        self.serpapi_key = serpapi_key
        self.youtube_api_key = youtube_api_key
        self.newsapi_key = newsapi_key

    async def fetch_all(self, region: str, periode: str) -> List[Tendance]:
        """Collecte depuis toutes les sources en parallèle."""
        region_code = region.upper()
        country_lower = region.lower()

        tasks = []
        if self.serpapi_key:
            tasks.append(self._fetch_google_trends(region_code))
        if self.youtube_api_key:
            tasks.append(self._fetch_youtube(region_code))
        if self.newsapi_key:
            tasks.append(self._fetch_newsapi(country_lower))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        tendances: List[Tendance] = []
        for r in results:
            if isinstance(r, list):
                tendances.extend(r)

        # Dédupliquer par sujet
        vus: set[str] = set()
        uniq: List[Tendance] = []
        for t in tendances:
            key = t.sujet.lower()[:40]
            if key not in vus:
                vus.add(key)
                uniq.append(t)

        return uniq

    async def _fetch_google_trends(self, region: str) -> List[Tendance]:
        """SerpAPI Google Trends Trending Searches (portage exact de yukpomnang2)."""
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                # Essai 1 : Google Trends Trending Searches via SerpAPI
                url = (
                    f"https://serpapi.com/search.json?engine=google_trends"
                    f"&data_type=TRENDING_SEARCHES&geo={region}&hl=fr"
                    f"&api_key={self.serpapi_key}"
                )
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    parsed = self._parse_serpapi_trending(data, region)
                    if parsed:
                        return parsed

                # Essai 2 : Recherche Google organique par mots-clés
                country_name = {
                    "CI": "Côte d'Ivoire tendances",
                    "CM": "Cameroun tendances actualité",
                    "SN": "Sénégal tendances actualité",
                    "NG": "Nigeria trends today",
                }.get(region, "Afrique tendances")
                url2 = (
                    f"https://serpapi.com/search.json?engine=google"
                    f"&q={quote(country_name)}&gl={region.lower()}&hl=fr&num=15"
                    f"&api_key={self.serpapi_key}"
                )
                resp2 = await client.get(url2)
                if resp2.status_code == 200:
                    return self._parse_serpapi_organic(resp2.json(), region)

                # Fallback RSS Google Trends direct
                return await self._fetch_google_rss(region)
        except Exception as e:
            logger.warning(f"[Trends] SerpAPI erreur pour {region}: {e}")
            return await self._fetch_google_rss(region)

    async def _fetch_google_rss(self, region: str) -> List[Tendance]:
        """Fallback RSS Google Trends (parfois bloqué sur cloud)."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                url = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={region}"
                resp = await client.get(url)
                if resp.status_code == 200:
                    return self._parse_google_rss(resp.text, region)
        except Exception:
            pass
        return []

    def _parse_serpapi_trending(self, data: dict, region: str) -> List[Tendance]:
        searches = data.get("trending_searches", [])
        tendances = []
        for i, item in enumerate(searches[:20]):
            # Structure SerpAPI: item["title"]["query"] ou item["query"]["query"] ou item["query"]
            topic = (
                (item.get("title") or {}).get("query")
                or (item.get("query") or {}).get("query")
                or item.get("query")
            )
            if not topic:
                continue
            traffic_str = str(item.get("formattedTraffic", "1000")).replace("+", "").replace(",", "").replace("K", "000")
            try:
                traffic = float(traffic_str)
            except ValueError:
                traffic = 1000.0
            social_score = min(100.0, max(10.0, traffic / 200000.0 * 100.0))
            tendances.append(Tendance(
                id=f"serp-{region}-{i}",
                sujet=topic,
                region=region,
                score_social=social_score,
                score_commerce=0.0,
                score_opportunite=0.0,
                momentum_pct=max(10.0, 85.0 - i * 3.5),
                categories=[],
                sources=["Google Trends"],
                periode="24h",
            ))
        return tendances

    def _parse_serpapi_organic(self, data: dict, region: str) -> List[Tendance]:
        results = data.get("organic_results", [])
        tendances = []
        for i, item in enumerate(results[:10]):
            title = item.get("title", "")
            if len(title) < 5:
                continue
            tendances.append(Tendance(
                id=f"serp-organic-{region}-{i}",
                sujet=title,
                region=region,
                score_social=max(20.0, 75.0 - i * 4.0),
                score_commerce=0.0,
                score_opportunite=0.0,
                momentum_pct=max(10.0, 70.0 - i * 4.0),
                categories=["actualité"],
                sources=["Google"],
                periode="24h",
            ))
        return tendances

    def _parse_google_rss(self, rss_text: str, region: str) -> List[Tendance]:
        """Parse RSS Google Trends (format XML)."""
        tendances = []
        try:
            items = rss_text.split("<item>")[1:]
            for i, item in enumerate(items[:20]):
                title = self._extract_xml(item, "title")
                traffic_str = self._extract_xml(item, "ht:approx_traffic").replace("+", "").replace(",", "")
                if not title:
                    continue
                try:
                    traffic = float(traffic_str) if traffic_str else 1000.0
                except ValueError:
                    traffic = 1000.0
                social_score = min(100.0, max(5.0, traffic / 200000.0 * 100.0))
                tendances.append(Tendance(
                    id=f"google-rss-{region}-{i}",
                    sujet=title,
                    region=region,
                    score_social=social_score,
                    score_commerce=0.0,
                    score_opportunite=0.0,
                    momentum_pct=max(5.0, 80.0 - i * 3.5),
                    categories=[],
                    sources=["Google Trends"],
                    periode="24h",
                ))
        except Exception as e:
            logger.debug(f"[Trends] RSS parse erreur: {e}")
        return tendances

    async def _fetch_youtube(self, region: str) -> List[Tendance]:
        """YouTube Data API — mostPopular + fallback search."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                # Essai 1 : mostPopular par pays
                url = (
                    f"https://www.googleapis.com/youtube/v3/videos"
                    f"?part=snippet,statistics&chart=mostPopular"
                    f"&regionCode={region}&maxResults=20&key={self.youtube_api_key}"
                )
                resp = await client.get(url)
                if resp.status_code == 200:
                    parsed = self._parse_youtube(resp.json(), region)
                    if parsed:
                        return parsed

                # Essai 2 : recherche YouTube par mots-clés régionaux
                search_q = {
                    "CI": "Côte d'Ivoire musique tendance 2025",
                    "CM": "Cameroun musique makossa tendance",
                    "SN": "Sénégal mbalax tendance 2025",
                    "NG": "Nigeria afrobeats trending 2025",
                }.get(region, "Afrique musique tendance 2025")
                url2 = (
                    f"https://www.googleapis.com/youtube/v3/search"
                    f"?part=snippet&q={quote(search_q)}&type=video&order=viewCount"
                    f"&maxResults=15&relevanceLanguage=fr&key={self.youtube_api_key}"
                )
                resp2 = await client.get(url2)
                if resp2.status_code == 200:
                    return self._parse_youtube_search(resp2.json(), region)
        except Exception as e:
            logger.debug(f"[Trends] YouTube erreur pour {region}: {e}")
        return []

    def _parse_youtube(self, data: dict, region: str) -> List[Tendance]:
        tendances = []
        CATEGORIES_YT = {
            "1": "Film", "2": "Véhicules", "10": "Musique", "17": "Sport",
            "20": "Jeux vidéo", "22": "Blogs", "23": "Comédie", "24": "Divertissement",
            "25": "Actualités", "26": "Tutoriels", "28": "Science & Tech",
        }
        for i, item in enumerate(data.get("items", [])[:15]):
            title = item.get("snippet", {}).get("title", "")
            if not title:
                continue
            category_id = item.get("snippet", {}).get("categoryId", "0")
            try:
                views = float(item.get("statistics", {}).get("viewCount", 0))
            except (ValueError, TypeError):
                views = 0.0
            social_score = min(100.0, max(5.0, views / 500000.0 * 100.0))
            tendances.append(Tendance(
                id=f"youtube-{region}-{i}",
                sujet=title,
                region=region,
                score_social=social_score,
                score_commerce=0.0,
                score_opportunite=0.0,
                momentum_pct=max(5.0, 60.0 - i * 2.5),
                categories=[CATEGORIES_YT.get(category_id, "Général")],
                sources=["YouTube"],
                periode="24h",
            ))
        return tendances

    def _parse_youtube_search(self, data: dict, region: str) -> List[Tendance]:
        tendances = []
        for i, item in enumerate(data.get("items", [])[:12]):
            title = item.get("snippet", {}).get("title", "")
            if not title:
                continue
            tendances.append(Tendance(
                id=f"youtube-search-{region}-{i}",
                sujet=title,
                region=region,
                score_social=max(10.0, 70.0 - i * 3.0),
                score_commerce=0.0,
                score_opportunite=0.0,
                momentum_pct=max(10.0, 65.0 - i * 3.0),
                categories=["Musique"],
                sources=["YouTube"],
                periode="24h",
            ))
        return tendances

    async def _fetch_newsapi(self, country: str) -> List[Tendance]:
        """NewsAPI — top-headlines + fallback /everything par mots-clés."""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                # Pays supportés par NewsAPI top-headlines
                supported = {"ng", "za", "eg", "ma"}
                region_upper = country.upper()

                if country in supported:
                    url = (
                        f"https://newsapi.org/v2/top-headlines"
                        f"?country={country}&pageSize=20&apiKey={self.newsapi_key}"
                    )
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        parsed = self._parse_newsapi(resp.json(), region_upper)
                        if parsed:
                            return parsed

                # Fallback /everything avec mots-clés régionaux
                keyword = {
                    "ci": '"Côte d\'Ivoire" OR "Abidjan" tendance',
                    "cm": '"Cameroun" OR "Yaoundé" OR "Douala" tendance',
                    "sn": '"Sénégal" OR "Dakar" tendance',
                    "ng": "Nigeria trend Lagos",
                }.get(country, "Afrique tendances")
                url2 = (
                    f"https://newsapi.org/v2/everything"
                    f"?q={quote(keyword)}&language=fr&sortBy=publishedAt"
                    f"&pageSize=20&apiKey={self.newsapi_key}"
                )
                resp2 = await client.get(url2)
                if resp2.status_code == 200:
                    return self._parse_newsapi(resp2.json(), region_upper)
        except Exception as e:
            logger.debug(f"[Trends] NewsAPI erreur pour {country}: {e}")
        return []

    def _parse_newsapi(self, data: dict, region: str) -> List[Tendance]:
        tendances = []
        for i, art in enumerate(data.get("articles", [])[:15]):
            title = art.get("title", "")
            source = (art.get("source") or {}).get("name", "NewsAPI")
            if not title or title == "[Removed]":
                continue
            tendances.append(Tendance(
                id=f"news-{region}-{i}",
                sujet=title,
                region=region,
                score_social=max(10.0, 50.0 - i * 2.0),
                score_commerce=0.0,
                score_opportunite=0.0,
                momentum_pct=max(5.0, 40.0 - i * 1.5),
                categories=[],
                sources=[source],
                periode="24h",
            ))
        return tendances

    @staticmethod
    def _extract_xml(xml: str, tag: str) -> str:
        open_tag = f"<{tag}>"
        close_tag = f"</{tag}>"
        start = xml.find(open_tag)
        end = xml.find(close_tag)
        if start == -1 or end == -1:
            return ""
        content = xml[start + len(open_tag):end].strip()
        return content.lstrip("<![CDATA[").rstrip("]]>").strip()


# ─────────────────────────────────────────────────────────────
# Scoring personnalisé (portage de score_trend_for_user de yukpomnang2)
# ─────────────────────────────────────────────────────────────

MOTS_CLES_SECTEUR: Dict[str, List[str]] = {
    "assurance": [
        "assurance", "sinistre", "police", "prime", "contrat", "garantie",
        "couverture", "indemnisation", "cima", "préjudice",
    ],
    "banque": [
        "banque", "crédit", "prêt", "épargne", "compte", "virement",
        "mobile money", "fintech", "taux", "cobac",
    ],
    "sante": [
        "santé", "hôpital", "clinique", "médecin", "médicament", "maladie",
        "traitement", "épidémie", "paludisme", "vaccin",
    ],
    "commerce": [
        "promotion", "solde", "alimentation", "marché", "boutique",
        "achat", "shopping", "livraison", "commande", "e-commerce",
    ],
    "microfinance": [
        "tontine", "épargne", "micro-crédit", "pme", "entrepreneur",
        "inclusion", "mobile money", "financement",
    ],
    "immobilier": [
        "logement", "maison", "appartement", "terrain", "loyer",
        "achat immobilier", "construction", "promotion immobilière",
    ],
    "transport": [
        "transport", "voyage", "déplacement", "taxi", "covoiturage",
        "mobilité", "fête", "événement", "carburant",
    ],
}


def scorer_tendance_pour_compagnie(
    tendance: Tendance,
    contexte: ContexteCommercial,
) -> Tendance:
    """
    Recalcule commerce_score et opportunity_score selon le profil réel de la compagnie.
    Portage exact de score_trend_for_user() de yukpomnang2.
    """
    from copy import deepcopy
    t = deepcopy(tendance)
    topic_lower = t.sujet.lower()
    commerce_score = 0.0
    produits_matches: List[ProduitMatch] = []

    # Multiplicateur selon le secteur d'activité
    multiplicateur = {
        "sante": 1.8, "pharmacie": 1.8,
        "commerce": 1.5, "e_commerce": 1.3,
        "assurance": 1.2, "banque": 1.2,
        "transport": 1.0,
    }.get(contexte.secteur.lower(), 1.0)

    # 1. Matching avec les produits/services de la compagnie
    for service in contexte.services:
        for produit in service.produits:
            nom_lower = produit.nom.lower()
            cat_lower = produit.categorie.lower()
            mots_nom = [w for w in nom_lower.split() if len(w) >= 4]
            mots_sujet = [w for w in topic_lower.split() if len(w) >= 4]
            communs = len(set(mots_nom) & set(mots_sujet))
            cat_match = cat_lower in topic_lower or (len(cat_lower) >= 4 and cat_lower[:6] in topic_lower)
            match_score = (communs * 20.0 + (25.0 if cat_match else 0.0)) * multiplicateur
            if match_score > 0:
                commerce_score += match_score
                produits_matches.append(ProduitMatch(
                    produit_id=produit.id,
                    produit_nom=produit.nom,
                    service_id=service.id,
                    service_nom=service.nom,
                    score_match=match_score,
                    prix_actuel=produit.prix,
                    est_promo=produit.est_promo,
                ))

    # 2. Boost sectoriel — mots-clés du secteur dans le sujet
    mots_cles = MOTS_CLES_SECTEUR.get(contexte.secteur.lower(), [])
    boost_sectoriel = sum(12.0 for kw in mots_cles if kw in topic_lower)
    commerce_score += boost_sectoriel

    # 3. Boost ROAS si campagnes Meta performantes
    roas_moyen = (
        sum(s.roas for s in contexte.signaux_pub if s.roas and s.roas > 0)
        / max(1, len([s for s in contexte.signaux_pub if s.roas and s.roas > 0]))
        if contexte.signaux_pub else 0.0
    )
    if roas_moyen > 2.5:
        commerce_score += 20.0

    commerce_score = min(100.0, commerce_score)
    t.score_commerce = commerce_score

    # 4. Score d'opportunité pondéré (social/commerce selon secteur)
    if contexte.secteur.lower() in ("sante", "pharmacie"):
        sw, cw = 0.35, 0.65
    elif contexte.secteur.lower() in ("transport",):
        sw, cw = 0.55, 0.45
    elif contexte.secteur.lower() in ("commerce", "assurance", "banque"):
        sw, cw = 0.30, 0.70
    else:
        sw, cw = 0.40, 0.60

    momentum_bonus = min(15.0, t.momentum_pct / 100.0 * 15.0)
    t.score_opportunite = min(100.0, t.score_social * sw + commerce_score * cw + momentum_bonus)

    # 5. Top produits matchés (max 3)
    produits_matches.sort(key=lambda p: p.score_match, reverse=True)
    t.produits_matches = produits_matches[:3]

    # 6. Action recommandée si opportunité élevée
    seuil = {"commerce": 60.0, "sante": 55.0}.get(contexte.secteur.lower(), 65.0)
    if t.score_opportunite >= seuil and t.produits_matches:
        t.action_recommandee = _construire_action(t, contexte, roas_moyen)

    # 7. Prévision J+3 (simple : momentum → extrapolation linéaire)
    delta = t.momentum_pct / 100.0 * t.score_opportunite * 0.15
    t.prevision_j3 = min(100.0, max(0.0, t.score_opportunite + delta))
    t.confiance_prevision = 0.6 if abs(t.momentum_pct) > 5 else 0.4

    return t


def _construire_action(
    t: Tendance,
    ctx: ContexteCommercial,
    roas_moyen: float,
) -> ActionRecommandee:
    service_id = t.produits_matches[0].service_id if t.produits_matches else 0
    if ctx.a_meta_ads and roas_moyen > 2.0:
        budget = 15000
        roas_estime = roas_moyen * 1.2
        return ActionRecommandee(
            type_action="launch_campaign",
            titre=f"Lancer une campagne sur « {t.sujet[:50]} »",
            description=(
                f"Basé sur ton ROAS historique {roas_moyen:.1f}x, un budget de {budget:,} FCFA "
                f"devrait générer ~{int(budget * roas_estime):,} FCFA"
            ),
            roas_estime=roas_estime,
            budget_suggere_fcfa=budget,
            route="community-manager",
        )
    elif ctx.a_comptes_sociaux:
        return ActionRecommandee(
            type_action="schedule_post",
            titre=f"Publier sur « {t.sujet[:50]} »",
            description="Cette tendance correspond à vos produits. Créez un post maintenant.",
            route="community-manager",
        )
    else:
        return ActionRecommandee(
            type_action="create_promo",
            titre="Créer une offre promotionnelle",
            description=f"La tendance « {t.sujet[:50]} » est une opportunité commerciale à saisir.",
        )


# ─────────────────────────────────────────────────────────────
# Veille réglementaire (enrichie)
# ─────────────────────────────────────────────────────────────

VEILLE_REGLEMENTAIRE: Dict[str, List[Dict]] = {
    "assurance": [
        {
            "titre": "Circulaire CRCA — Renforcement des provisions PSAP",
            "date": "2026-01-15", "impact": "élevé",
            "resume": "La CRCA exige un renforcement des PSAP avec la méthode Chain-Ladder obligatoire pour les branches longues.",
            "action_requise": "Réviser le calcul des PSAP avant clôture semestrielle.",
            "source": "CRCA",
        },
        {
            "titre": "Art. 12-ter CIMA — Rappel délai règlement 45 jours",
            "date": "2026-02-01", "impact": "élevé",
            "resume": "Tout sinistre doit être réglé dans les 45 jours sous peine de pénalité au taux légal × 1,5.",
            "action_requise": "Vérifier les dossiers sinistres ouverts > 30 jours.",
            "source": "CIMA",
        },
        {
            "titre": "Capital minimum 3 milliards FCFA — Calendrier de mise en conformité",
            "date": "2026-03-01", "impact": "critique",
            "resume": "Les compagnies n'ayant pas atteint le capital minimum de 3 milliards FCFA risquent un retrait d'agrément.",
            "action_requise": "Vérifier la conformité du capital social et préparer le plan de recapitalisation.",
            "source": "CIMA / CRCA",
        },
        {
            "titre": "Formulaire C1 CIMA — Rapport annuel de gestion",
            "date": "2026-03-31", "impact": "critique",
            "resume": "Dépôt obligatoire du formulaire C1 (états financiers, comptes techniques) avant le 31 mars.",
            "action_requise": "Préparer et valider les états financiers pour dépôt à la CRCA.",
            "source": "CIMA",
        },
        {
            "titre": "OHADA — Réforme du droit des sûretés",
            "date": "2026-01-01", "impact": "moyen",
            "resume": "La réforme du droit des sûretés OHADA impacte les contrats de garantie et caution.",
            "action_requise": "Auditer les contrats de caution en portefeuille.",
            "source": "OHADA",
        },
    ],
    "banque": [
        {
            "titre": "COBAC — Ratio de solvabilité minimum 10%",
            "date": "2026-01-01", "impact": "élevé",
            "resume": "Renforcement des exigences de fonds propres.",
            "action_requise": "Calculer le ratio de solvabilité et préparer le rapport COBAC.",
            "source": "COBAC",
        },
        {
            "titre": "COBAC — Limites aux grands risques",
            "date": "2026-02-01", "impact": "élevé",
            "resume": "Les expositions sur un même bénéficiaire ne peuvent dépasser 45% des fonds propres.",
            "action_requise": "Revue du portefeuille de crédits pour vérifier les concentrations.",
            "source": "COBAC",
        },
    ],
    "microfinance": [
        {
            "titre": "COBAC — Plafond des taux d'intérêt MFI",
            "date": "2026-02-15", "impact": "moyen",
            "resume": "Rappel des plafonds de taux d'intérêt pour les micro-crédits.",
            "action_requise": "Auditer le portefeuille pour conformité tauxologique.",
            "source": "COBAC",
        },
    ],
}


# ─────────────────────────────────────────────────────────────
# Moteur TrendPulse principal
# ─────────────────────────────────────────────────────────────

class MoteurTrends:

    def __init__(
        self,
        claude_api_key: str = "",
        openai_api_key: str = "",
        secteur: str = "assurance",
        serpapi_key: str = "",
        youtube_api_key: str = "",
        newsapi_key: str = "",
    ):
        self.claude_api_key = claude_api_key
        self.openai_api_key = openai_api_key
        self.secteur = secteur
        self.agregateur = AgregateurExternes(
            serpapi_key=serpapi_key,
            youtube_api_key=youtube_api_key,
            newsapi_key=newsapi_key,
        )

    async def obtenir_tendances(
        self,
        region: str = "CM",
        periode: str = "24h",
        categorie: Optional[str] = None,
        score_min: float = 0.0,
        limit: int = 20,
        contexte: Optional[ContexteCommercial] = None,
    ) -> PulseTendances:
        """
        Collecte les tendances depuis les sources externes ET le catalogue interne.
        Si contexte fourni, personnalise les scores.
        """
        region = region.upper()
        tendances_externes: List[Tendance] = []
        tendances_internes: List[Tendance] = []

        # 1. Sources externes si APIs configurées
        try:
            tendances_externes = await self.agregateur.fetch_all(region, periode)
        except Exception as e:
            logger.warning(f"[Trends] Erreur sources externes: {e}")

        # 2. Catalogue interne sectoriel
        for t in TENDANCES_BASE.get(self.secteur, TENDANCES_BASE.get("assurance", [])):
            if categorie and not any(categorie.lower() in c.lower() for c in t["categories"]):
                continue
            momentum = self._momentum_deterministe(t["sujet"], region, periode)
            score_opp = min(100.0, t["score_opportunite"] + momentum * 0.3)
            tendances_internes.append(Tendance(
                id=f"internal-{hashlib.md5(t['sujet'].encode()).hexdigest()[:8]}",
                sujet=t["sujet"],
                region=region,
                score_social=float(t["score_social"]),
                score_commerce=float(t["score_commerce"]),
                score_opportunite=round(score_opp, 1),
                momentum_pct=round(momentum, 1),
                categories=t["categories"],
                sources=t["sources"],
                periode=periode,
                resume=t.get("resume", ""),
                recommandations=t.get("recommandations", []),
            ))

        # 3. Enrichir les tendances externes avec les scores commerce
        for t_ext in tendances_externes:
            t_ext.score_opportunite = round(t_ext.score_social * 0.6 + t_ext.momentum_pct * 0.2, 1)

        # 4. Fusionner et dédupliquer (internes en premier)
        toutes = tendances_internes + tendances_externes
        vus: set[str] = set()
        fusionnees: List[Tendance] = []
        for t in toutes:
            key = t.sujet.lower()[:30]
            if key not in vus:
                vus.add(key)
                fusionnees.append(t)

        # 5. Filtrer
        if score_min > 0:
            fusionnees = [t for t in fusionnees if t.score_opportunite >= score_min]

        # 6. Tri par score décroissant
        fusionnees.sort(key=lambda x: x.score_opportunite, reverse=True)
        fusionnees = fusionnees[:limit]

        # 7. Personnalisation si contexte fourni
        tendances_perso: List[Tendance] = []
        if contexte:
            perso = [scorer_tendance_pour_compagnie(t, contexte) for t in fusionnees[:10]]
            perso.sort(key=lambda x: x.score_opportunite, reverse=True)
            tendances_perso = perso

        # 8. Personnalités et secteurs en tendance (extraits des sources externes)
        personnalites = self._extraire_personnalites(tendances_externes)
        top_secteurs = self._top_secteurs(fusionnees)

        return PulseTendances(
            region=REGIONS.get(region, region),
            periode=periode,
            genere_le=datetime.now(timezone.utc).isoformat(),
            tendances=fusionnees,
            tendances_personnalisees=tendances_perso,
            personnalites=personnalites,
            top_secteurs=top_secteurs,
            tendances_en_hausse=[t.sujet for t in fusionnees if t.momentum_pct > 5][:5],
            top_categories=self._top_categories(fusionnees)[:5],
            resume_executif=self._resume_executif(fusionnees, region),
        )

    def _momentum_deterministe(self, sujet: str, region: str, periode: str) -> float:
        """Momentum déterministe basé sur hash (reproductible sans base de données)."""
        seed = sum(ord(c) for c in sujet + region)
        base = (seed % 30) - 10
        if periode == "7d":
            base *= 0.7
        elif periode == "30d":
            base *= 0.5
        return base

    def _top_categories(self, tendances: List[Tendance]) -> List[str]:
        comptage: Dict[str, int] = {}
        for t in tendances:
            for c in t.categories:
                comptage[c] = comptage.get(c, 0) + 1
        return sorted(comptage, key=lambda k: comptage[k], reverse=True)

    def _resume_executif(self, tendances: List[Tendance], region: str) -> str:
        if not tendances:
            return "Aucune tendance significative détectée pour cette période."
        top = tendances[0]
        en_hausse = [t for t in tendances if t.momentum_pct > 5]
        top_cats = self._top_categories(tendances)[:3]
        return (
            f"Le marché {REGIONS.get(region, region)} présente {len(tendances)} tendances actives. "
            f"Principale opportunité : « {top.sujet} » (score {top.score_opportunite:.0f}/100). "
            f"{len(en_hausse)} tendance(s) en forte hausse. "
            f"Catégories dominantes : {', '.join(top_cats)}."
        )

    def _extraire_personnalites(self, tendances: List[Tendance]) -> List[TendancePersonnalite]:
        """Détecte les personnalités à partir des sujets tendances."""
        DOMAINES = {
            "musique": ["musique", "chanson", "artiste", "album", "concert", "youtube"],
            "sport": ["football", "sport", "équipe", "match", "can", "coupe", "fifa"],
            "politique": ["président", "gouvernement", "élection", "ministre", "politique"],
            "business": ["entreprise", "startup", "ceo", "business", "fintech"],
        }
        personnalites = []
        for t in tendances[:15]:
            sujet_lower = t.sujet.lower()
            domaine = "media"
            for d, mots in DOMAINES.items():
                if any(m in sujet_lower for m in mots):
                    domaine = d
                    break
            # Heuristique : sujet court sans catégorie = probablement une personnalité/événement
            if len(t.sujet.split()) <= 4 and not t.categories:
                personnalites.append(TendancePersonnalite(
                    nom=t.sujet,
                    mentions=int(t.score_social * 100),
                    domaine=domaine,
                    momentum_pct=t.momentum_pct,
                    sources=t.sources,
                ))
        return personnalites[:10]

    def _top_secteurs(self, tendances: List[Tendance]) -> List[TendanceSecteur]:
        """Agrège les tendances par secteur économique."""
        MAPPING = {
            "assurance": ["assurance", "prime", "sinistre", "garantie", "cima"],
            "fintech": ["mobile money", "fintech", "paiement", "banque"],
            "santé": ["santé", "médecin", "maladie", "clinique", "paludisme"],
            "commerce": ["boutique", "shopping", "promotion", "solde", "livraison"],
            "agriculture": ["agriculture", "récolte", "pluie", "saison", "alimentation"],
        }
        secteur_scores: Dict[str, List[float]] = {}
        for t in tendances:
            sujet_lower = t.sujet.lower()
            for secteur, mots in MAPPING.items():
                if any(m in sujet_lower for m in mots):
                    if secteur not in secteur_scores:
                        secteur_scores[secteur] = []
                    secteur_scores[secteur].append(t.momentum_pct)
        top = []
        for secteur, momentums in secteur_scores.items():
            top.append(TendanceSecteur(
                secteur=secteur,
                croissance_pct=sum(momentums) / len(momentums),
                top_sujet=tendances[0].sujet if tendances else "",
                regions=[tendances[0].region] if tendances else [],
            ))
        top.sort(key=lambda x: x.croissance_pct, reverse=True)
        return top[:5]

    async def analyser_avec_ia(
        self,
        tendances: List[Tendance],
        contexte_compagnie: str = "",
    ) -> str:
        """Analyse stratégique IA approfondie."""
        prompt = (
            f"Analyse les tendances de marché suivantes pour une compagnie du secteur {self.secteur} "
            f"en Afrique :\n\n"
        )
        for t in tendances[:5]:
            prompt += f"- {t.sujet} (opportunité: {t.score_opportunite:.0f}/100, momentum: {t.momentum_pct:+.1f}%)\n"
            if t.resume:
                prompt += f"  Résumé: {t.resume}\n"
            if t.produits_matches:
                prompt += f"  Produits matchés: {', '.join(p.produit_nom for p in t.produits_matches[:2])}\n"
        if contexte_compagnie:
            prompt += f"\nContexte compagnie : {contexte_compagnie}\n"
        prompt += (
            "\nFournis une analyse stratégique en 5-7 lignes :\n"
            "1) L'opportunité principale à saisir\n"
            "2) Le risque principal\n"
            "3) 3 actions concrètes dans les 30 jours\n"
            "4) ROI estimé si l'opportunité est bien exploitée"
        )

        if self.claude_api_key:
            try:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=self.claude_api_key)
                response = await client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=600,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}],
                )
                return response.content[0].text
            except Exception:
                pass

        if self.openai_api_key:
            try:
                from openai import AsyncOpenAI
                resp = await AsyncOpenAI(api_key=self.openai_api_key).chat.completions.create(
                    model="gpt-4o", max_tokens=600,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.choices[0].message.content or ""
            except Exception:
                pass

        # Fallback
        top = tendances[0] if tendances else None
        if top:
            return (
                f"Analyse : La tendance « {top.sujet} » (score {top.score_opportunite:.0f}/100) "
                f"est la principale opportunité. "
                + (f"Actions : {'; '.join(top.recommandations[:3])}." if top.recommandations else "")
            )
        return "Aucune tendance significative à analyser."

    def evaluer_alerte(
        self,
        tendance: Tendance,
        seuil_opportunite: float = 75.0,
        seuil_momentum: float = 10.0,
    ) -> bool:
        return tendance.score_opportunite >= seuil_opportunite and tendance.momentum_pct >= seuil_momentum

    def veille_reglementaire(self, secteur: str = "assurance") -> List[Dict]:
        return VEILLE_REGLEMENTAIRE.get(secteur, [])

    @staticmethod
    def regions_supportees() -> Dict[str, str]:
        return REGIONS.copy()

    @staticmethod
    def meilleure_heure_publication(plateforme: str) -> int:
        """Heure optimale basée sur les scores d'engagement africains (yukpomnang2)."""
        defaults = {
            "facebook": 18, "instagram": 18, "linkedin": 8,
            "twitter": 9, "whatsapp": 10, "tiktok": 19,
        }
        return defaults.get(plateforme.lower(), 18)
