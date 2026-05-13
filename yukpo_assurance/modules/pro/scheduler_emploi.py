"""
SchedulerEmploi v2 — Veille emploi réelle, multi-sources.

Sources actives (ordre de priorité) :
  1. Serper.dev Google Jobs — agrège LinkedIn, Indeed, Glassdoor + sites locaux par pays
     → Variable : SERPER_API_KEY  ← PRINCIPALE SOURCE, 2500 req/mois gratuits sur serper.dev
  2. Sites emploi locaux africains via Serper (FNE, 237jobs, ANPE…)
     → Variable : SERPER_API_KEY
  3. Adzuna API           — International, gratuit 250 req/mois
     → Variables : ADZUNA_APP_ID + ADZUNA_APP_KEY
  4. Remotive.io          — Remote tech/finance uniquement (catégorie, pas recherche libre)
     → Gratuit sans clé. Note : paramètre `search` ignoré côté API, on utilise `category`.
  5. Jobicy.com           — Remote, par tag métier (pas par mot-clé)
     → Gratuit sans clé. Note : paramètre `keyword` retourne 0, on utilise `tag`.
  6. Jooble API           — Afrique + international
     → Variable : JOOBLE_API_KEY
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("yukpo_assurance.pro.scheduler_emploi")

_CYCLE_VERIFICATION = 30 * 60   # 30 min entre chaque cycle global
_MAX_OFFRES_STORED  = 25        # max offres stockées par user
_HTTP_TIMEOUT       = 20        # secondes timeout HTTP

_running = False

# ── Mapping pays ──────────────────────────────────────────────────────────────

PAYS_INFO: dict[str, dict] = {
    "CM": {"nom": "Cameroun",       "gl": "cm", "hl": "fr", "adzuna": None,  "jooble_loc": "Cameroun"},
    "CI": {"nom": "Côte d'Ivoire",  "gl": "ci", "hl": "fr", "adzuna": None,  "jooble_loc": "Abidjan"},
    "SN": {"nom": "Sénégal",        "gl": "sn", "hl": "fr", "adzuna": None,  "jooble_loc": "Dakar"},
    "GA": {"nom": "Gabon",          "gl": "ga", "hl": "fr", "adzuna": None,  "jooble_loc": "Libreville"},
    "BF": {"nom": "Burkina Faso",   "gl": "bf", "hl": "fr", "adzuna": None,  "jooble_loc": "Ouagadougou"},
    "ML": {"nom": "Mali",           "gl": "ml", "hl": "fr", "adzuna": None,  "jooble_loc": "Bamako"},
    "CD": {"nom": "RD Congo",       "gl": "cd", "hl": "fr", "adzuna": None,  "jooble_loc": "Kinshasa"},
    "TG": {"nom": "Togo",           "gl": "tg", "hl": "fr", "adzuna": None,  "jooble_loc": "Lomé"},
    "BJ": {"nom": "Bénin",          "gl": "bj", "hl": "fr", "adzuna": None,  "jooble_loc": "Cotonou"},
    "MG": {"nom": "Madagascar",     "gl": "mg", "hl": "fr", "adzuna": None,  "jooble_loc": "Antananarivo"},
    "RW": {"nom": "Rwanda",         "gl": "rw", "hl": "fr", "adzuna": None,  "jooble_loc": "Kigali"},
    "KE": {"nom": "Kenya",          "gl": "ke", "hl": "en", "adzuna": None,  "jooble_loc": "Nairobi"},
    "NG": {"nom": "Nigeria",        "gl": "ng", "hl": "en", "adzuna": None,  "jooble_loc": "Lagos"},
    "GH": {"nom": "Ghana",          "gl": "gh", "hl": "en", "adzuna": None,  "jooble_loc": "Accra"},
    "ZA": {"nom": "Afrique du Sud", "gl": "za", "hl": "en", "adzuna": "za",  "jooble_loc": "Johannesburg"},
    "MA": {"nom": "Maroc",          "gl": "ma", "hl": "fr", "adzuna": None,  "jooble_loc": "Casablanca"},
    "TN": {"nom": "Tunisie",        "gl": "tn", "hl": "fr", "adzuna": None,  "jooble_loc": "Tunis"},
    "DZ": {"nom": "Algérie",        "gl": "dz", "hl": "fr", "adzuna": None,  "jooble_loc": "Alger"},
    "NE": {"nom": "Niger",          "gl": "ne", "hl": "fr", "adzuna": None,  "jooble_loc": "Niamey"},
    "TD": {"nom": "Tchad",          "gl": "td", "hl": "fr", "adzuna": None,  "jooble_loc": "N'Djamena"},
    "MR": {"nom": "Mauritanie",     "gl": "mr", "hl": "fr", "adzuna": None,  "jooble_loc": "Nouakchott"},
    "FR": {"nom": "France",         "gl": "fr", "hl": "fr", "adzuna": "fr",  "jooble_loc": "Paris"},
    "BE": {"nom": "Belgique",       "gl": "be", "hl": "fr", "adzuna": None,  "jooble_loc": "Bruxelles"},
    "CH": {"nom": "Suisse",         "gl": "ch", "hl": "fr", "adzuna": None,  "jooble_loc": "Genève"},
    "CA": {"nom": "Canada",         "gl": "ca", "hl": "fr", "adzuna": "ca",  "jooble_loc": "Montréal"},
}

def _info_pays(pays: str) -> dict:
    return PAYS_INFO.get(pays.upper(), {
        "nom": pays, "gl": pays.lower(), "hl": "fr", "adzuna": None, "jooble_loc": pays,
    })


# ── Point d'entrée public ──────────────────────────────────────────────────────

async def demarrer_scheduler_emploi():
    """Démarrage scheduler — désactivé par défaut depuis mai 2026.

    Mode prod = LAZY ON-DEMAND : la recherche n'est déclenchée que
    lorsque l'utilisateur ouvre la page Emploi (cache stale > 24h) ou
    clique "Rechercher". Économise ~95 % des appels Serper/Adzuna/etc.
    sur des profils inactifs.

    Pour réactiver le scheduler auto : `EMPLOI_SCHEDULER_AUTO=1` en env.
    """
    if os.getenv("EMPLOI_SCHEDULER_AUTO", "0") != "1":
        logger.info("[SchedulerEmploi] Mode LAZY on-demand (scheduler auto désactivé). "
                    "EMPLOI_SCHEDULER_AUTO=1 pour réactiver.")
        return
    global _running
    if _running:
        return
    _running = True
    logger.info("[SchedulerEmploi] Démarrage veille emploi AUTO (override env)")
    asyncio.create_task(_boucle_veille_emploi(), name="scheduler_emploi")


async def arreter_scheduler_emploi():
    global _running
    _running = False
    logger.info("[SchedulerEmploi] Arrêt veille emploi")


# ── Boucle principale ─────────────────────────────────────────────────────────

async def _boucle_veille_emploi():
    await asyncio.sleep(60)
    while _running:
        try:
            await _cycle_recherche_tous_users()
        except Exception as e:
            logger.error(f"[SchedulerEmploi] Erreur cycle: {e}")
        await asyncio.sleep(_CYCLE_VERIFICATION)


async def _cycle_recherche_tous_users():
    try:
        from core.database import async_session_maker
        from modules.pro.profil_pro import ProfilProfessionnelDB
        from sqlalchemy import select

        async with async_session_maker() as db:
            result = await db.execute(
                select(ProfilProfessionnelDB)
                .where(ProfilProfessionnelDB.recherche_emploi_active == True)
            )
            profils = result.scalars().all()

        if not profils:
            return

        now = datetime.now(timezone.utc)
        for profil in profils:
            try:
                freq_h = profil.frequence_recherche_heures or 24
                derniere = profil.derniere_recherche_emploi
                if derniere and derniere.tzinfo is None:
                    derniere = derniere.replace(tzinfo=timezone.utc)
                if derniere and (now - derniere) < timedelta(hours=freq_h):
                    continue
                logger.info(f"[SchedulerEmploi] Recherche pour user_id={profil.user_id}")
                await rechercher_offres_pour_user(user_id=profil.user_id, profil=profil)
            except Exception as e:
                logger.error(f"[SchedulerEmploi] Erreur user {profil.user_id}: {e}")
    except Exception as e:
        logger.error(f"[SchedulerEmploi] Erreur cycle global: {e}")


# ── Fonction principale de recherche ──────────────────────────────────────────

async def rechercher_offres_pour_user(
    user_id: int,
    profil=None,
    mots_cles_extra: str = "",
    pays_override: str = "",
) -> int:
    """
    Recherche réelle d'offres d'emploi pour un utilisateur.
    Sources : SerpAPI → Adzuna → Remotive → Jobicy → Jooble → Fallback IA.
    Retourne le nombre d'offres sauvegardées.
    """
    mots_cles = _extraire_mots_cles(profil, mots_cles_extra)
    pays = pays_override or (getattr(profil, "pays", None) or "CM")

    if not mots_cles:
        logger.warning(f"[SchedulerEmploi] user {user_id}: profil de recherche non configuré")
        return 0

    info = _info_pays(pays)
    logger.info(f"[SchedulerEmploi] Recherche: '{mots_cles}' · {info['nom']}")

    # ── Débit crédits (forfait recherche emploi : 2 FCFA × 20 = 40 crédits) ──
    try:
        from modules.pro.service_credits import debiter_forfait_fcfa
        ok, _, msg = await debiter_forfait_fcfa(user_id, cout_fcfa=2.0, module="recherche_emploi")
        if not ok:
            logger.warning(f"[SchedulerEmploi] Crédits insuffisants user {user_id}: {msg}")
            return 0
    except Exception as e:
        logger.debug(f"[SchedulerEmploi] Débit crédits ignoré: {e}")

    # ── Collecte en parallèle depuis toutes les sources réelles ──────────────
    resultats = await asyncio.gather(
        _fetch_serper_google_jobs(mots_cles, pays, info),
        _fetch_sites_locaux(mots_cles, pays, info),
        _fetch_adzuna(mots_cles, pays, info),
        _fetch_remotive(mots_cles),
        _fetch_jobicy(mots_cles),
        _fetch_jooble(mots_cles, pays, info),
        return_exceptions=True,
    )

    offres_brutes: list[dict] = []
    noms_sources = ["Serper Google Jobs", "Sites locaux/agences", "Adzuna", "Remotive", "Jobicy", "Jooble"]
    for nom, res in zip(noms_sources, resultats):
        if isinstance(res, list):
            logger.info(f"[SchedulerEmploi] {nom}: {len(res)} offres")
            offres_brutes.extend(res)
        elif isinstance(res, Exception):
            logger.debug(f"[SchedulerEmploi] {nom} erreur: {res}")

    # ── Dédoublonnage ─────────────────────────────────────────────────────────
    seen: set[str] = set()
    offres_uniques: list[dict] = []
    for o in offres_brutes:
        key = (o.get("url") or o.get("titre", "")).strip().lower()[:120]
        if key and key not in seen:
            seen.add(key)
            offres_uniques.append(o)

    nb_reelles = len(offres_uniques)
    logger.info(f"[SchedulerEmploi] {nb_reelles} offres réelles uniques pour user {user_id}")

    if not offres_uniques:
        logger.warning(f"[SchedulerEmploi] Aucune offre trouvée pour user {user_id} — sources indisponibles")
        await _sauvegarder_offres(user_id, [])
        return 0

    # ── Scoring ───────────────────────────────────────────────────────────────
    offres_scorees = _scorer_offres(offres_uniques, profil)
    offres_scorees.sort(key=lambda x: x.get("score", 0), reverse=True)
    offres_finales = offres_scorees[:_MAX_OFFRES_STORED]

    await _sauvegarder_offres(user_id, offres_finales)
    return len(offres_finales)


# ── Source 1 : Serper.dev Google Jobs ─────────────────────────────────────────
# Agrège LinkedIn, Indeed, Glassdoor, AfricaJobs, Rekrute, etc. en temps réel.
# Couvre TOUS les pays. La source la plus puissante.
# POST https://google.serper.dev/jobs  (header X-API-KEY, body JSON)

async def _fetch_serper_google_jobs(mots_cles: str, pays: str, info: dict) -> list[dict]:
    api_key = os.getenv("SERPER_API_KEY", "") or os.getenv("SERPAPI_KEY", "")
    if not api_key or api_key.startswith("VOTRE"):
        return []

    try:
        import httpx
        offres: list[dict] = []
        headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            # ── Tentative 1 : endpoint /jobs (plan Pro+) ─────────────────────
            jobs_ok = False
            for q in [f"{mots_cles} {info['nom']}", f"{mots_cles} afrique francophone"]:
                resp = await client.post(
                    "https://google.serper.dev/jobs",
                    json={"q": q, "gl": info["gl"], "hl": info["hl"], "num": 20, "datePosted": "week"},
                    headers=headers,
                )
                if resp.status_code == 404:
                    break  # Endpoint non disponible sur ce plan → fallback /search
                if resp.status_code != 200:
                    continue
                jobs_ok = True
                for job in resp.json().get("jobs", []):
                    offres.append({
                        "titre":            (job.get("title") or "")[:150],
                        "entreprise":       job.get("company") or "Non précisé",
                        "lieu":             job.get("location") or info["nom"],
                        "resume":           (job.get("description") or job.get("snippet") or "")[:600],
                        "url":              job.get("link") or job.get("applyLink") or "",
                        "source":           job.get("via") or "Google Jobs",
                        "source_type":      "reel",
                        "date_publication": (job.get("datePosted") or "")[:10],
                        "type_contrat":     job.get("jobType") or "Non précisé",
                        "salaire":          job.get("salary") or "",
                        "score":            0,
                    })

            # ── Fallback : /search classique si /jobs non disponible ──────────
            if not jobs_ok:
                _JOB_KWS = ["emploi", "poste", "recrutement", "offre", "job", "cdi", "cdd", "stage"]
                for q in [f"{mots_cles} offre emploi {info['nom']}", f"{mots_cles} recrutement {info['nom']}"]:
                    resp = await client.post(
                        "https://google.serper.dev/search",
                        json={"q": q, "gl": info["gl"], "hl": info["hl"], "num": 10},
                        headers=headers,
                    )
                    if resp.status_code != 200:
                        continue
                    for r in resp.json().get("organic", []):
                        titre   = r.get("title", "").strip()
                        lien    = r.get("link", "")
                        snippet = r.get("snippet", "")
                        if not titre or not lien:
                            continue
                        if not any(kw in titre.lower() or kw in snippet.lower() for kw in _JOB_KWS):
                            continue
                        offres.append({
                            "titre":            titre[:150],
                            "entreprise":       (r.get("displayedLink", "") or "").split("/")[0] or "Non précisé",
                            "lieu":             info["nom"],
                            "resume":           snippet[:600],
                            "url":              lien,
                            "source":           "Google (Serper)",
                            "source_type":      "reel",
                            "date_publication": (r.get("date") or "")[:10],
                            "type_contrat":     "Non précisé",
                            "salaire":          "",
                            "score":            0,
                        })

        return offres

    except Exception as e:
        logger.debug(f"[SchedulerEmploi] Serper erreur: {e}")
        return []


# ── Source 2 : Adzuna API ─────────────────────────────────────────────────────
# Gratuit 250 req/mois. Couvre UK, FR, CA, ZA + international.

async def _fetch_adzuna(mots_cles: str, pays: str, info: dict) -> list[dict]:
    app_id  = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_APP_KEY", "")
    if not app_id or not app_key or app_id.startswith("VOTRE"):
        return []

    # Choisir le marché Adzuna le plus proche
    adzuna_country = info.get("adzuna") or "gb"

    try:
        import httpx
        q = urllib.parse.quote(mots_cles)
        url = (
            f"https://api.adzuna.com/v1/api/jobs/{adzuna_country}/search/1"
            f"?app_id={app_id}&app_key={app_key}"
            f"&what={q}&results_per_page=20&content-type=application/json&sort_by=date"
        )
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return []

        data = resp.json()
        offres = []
        for job in data.get("results", []):
            offres.append({
                "titre":            job.get("title", "")[:150],
                "entreprise":       job.get("company", {}).get("display_name", "Non précisé"),
                "lieu":             job.get("location", {}).get("display_name", info["nom"]),
                "resume":           (job.get("description", "") or "")[:600],
                "url":              job.get("redirect_url", ""),
                "source":           f"Adzuna ({adzuna_country.upper()})",
                "source_type":      "reel",
                "date_publication": (job.get("created", "") or "")[:10],
                "type_contrat":     _normaliser_contrat(job.get("contract_type", "")),
                "salaire":          _fmt_salaire(job.get("salary_min"), job.get("salary_max")),
                "score":            0,
            })
        return offres
    except Exception as e:
        logger.debug(f"[SchedulerEmploi] Adzuna erreur: {e}")
        return []


# ── Source 3 : Remotive.io ────────────────────────────────────────────────────
# DÉSACTIVÉ : le paramètre `search` de l'API Remotive est ignoré côté serveur —
# retourne toujours les mêmes 20 postes tech US quelle que soit la requête.
# Réactivé uniquement via `category` si le profil est tech/dev.

_REMOTIVE_CATEGORY: dict[str, str] = {
    "developpeur": "software-dev", "informaticien": "software-dev",
    "data": "data", "designer": "design",
    "marketing": "marketing", "product": "product",
    "devops": "devops-sysadmin", "finance": "finance-legal",
    "comptable": "finance-legal", "auditeur": "finance-legal",
    "rh": "human-resources", "support": "customer-support",
}

async def _fetch_remotive(mots_cles: str) -> list[dict]:
    # Détecter une catégorie Remotive correspondant aux mots-clés
    mots_lower = mots_cles.lower()
    category = next(
        (cat for kw, cat in _REMOTIVE_CATEGORY.items() if kw in mots_lower),
        None,
    )
    if not category:
        return []  # Pas de catégorie pertinente → ne pas retourner de hors-sujet

    try:
        import httpx
        url = f"https://remotive.com/api/remote-jobs?category={category}&limit=10"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return []

        data = resp.json()
        offres = []
        for job in data.get("jobs", []):
            offres.append({
                "titre":            job.get("title", "")[:150],
                "entreprise":       job.get("company_name", "Non précisé"),
                "lieu":             "Remote — " + (job.get("candidate_required_location", "Monde entier") or "Monde entier"),
                "resume":           re.sub(r"<[^>]+>", " ", job.get("description", "") or "")[:600],
                "url":              job.get("url", ""),
                "source":           "Remotive.io",
                "source_type":      "reel",
                "date_publication": (job.get("publication_date", "") or "")[:10],
                "type_contrat":     job.get("job_type", "Full-time"),
                "salaire":          job.get("salary", ""),
                "score":            0,
            })
        return offres
    except Exception as e:
        logger.debug(f"[SchedulerEmploi] Remotive erreur: {e}")
        return []


# ── Source 4 : Jobicy.com ─────────────────────────────────────────────────────
# API publique gratuite. Paramètre `tag` (pas `keyword` qui retourne 0).

_JOBICY_TAG: dict[str, str] = {
    "comptable": "accounting", "auditeur": "finance", "financier": "finance",
    "actuaire": "finance", "fiscaliste": "finance", "tresorier": "finance",
    "juriste": "legal", "avocat": "legal",
    "ingenieur": "engineering", "developpeur": "engineering",
    "informaticien": "engineering", "data": "engineering",
    "marketing": "marketing", "commercial": "sales", "vente": "sales",
    "directeur": "management", "manager": "management", "drh": "hr",
    "medecin": "health", "infirmier": "health",
    "designer": "design", "graphiste": "design",
}

async def _fetch_jobicy(mots_cles: str) -> list[dict]:
    mots_lower = mots_cles.lower()
    tag = next(
        (t for kw, t in _JOBICY_TAG.items() if kw in mots_lower),
        None,
    )
    if not tag:
        return []

    try:
        import httpx
        url = f"https://jobicy.com/api/v2/remote-jobs?count=10&tag={tag}"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url, headers={"User-Agent": "YukpoBot/2.0"})
        if resp.status_code != 200:
            return []

        data = resp.json()
        offres = []
        for job in data.get("jobs", []):
            offres.append({
                "titre":            job.get("jobTitle", "")[:150],
                "entreprise":       job.get("companyName", "Non précisé"),
                "lieu":             "Remote — " + (job.get("jobGeo", "Monde entier") or "Monde entier"),
                "resume":           re.sub(r"<[^>]+>", " ", job.get("jobExcerpt", "") or "")[:600],
                "url":              job.get("url", ""),
                "source":           "Jobicy",
                "source_type":      "reel",
                "date_publication": (job.get("pubDate", "") or "")[:10],
                "type_contrat":     job.get("jobType", "Full-time"),
                "salaire":          job.get("annualSalaryMin", ""),
                "score":            0,
            })
        return offres
    except Exception as e:
        logger.debug(f"[SchedulerEmploi] Jobicy erreur: {e}")
        return []


# ── Source 5b : Sites emploi africains locaux (via Serper ciblé) ─────────────
# Cible spécifiquement les agences publiques et sites locaux par pays.
# Cameroun : FNE, NinaJob, 237jobs | CI : ANPE | SN : ANPEJ | MA : ANAPEC…

_SITES_EMPLOI_LOCAUX: dict[str, list[str]] = {
    "CM": ["fne.cm", "ninajob.cm", "emploi.cm", "237jobs.com", "kerawa.com"],
    "CI": ["emploi.ci", "anpe.ci", "afrikajob.net"],
    "SN": ["anpej.sn", "emploi.sn", "senjob.com", "afrikajob.net"],
    "GA": ["gabon-emploi.org", "emploi.ga", "afrikajob.net"],
    "BF": ["anpe.bf", "burkinaemploi.net", "afrikajob.net"],
    "ML": ["anpe.ml", "emploi.ml", "afrikajob.net"],
    "TG": ["anpe.tg", "emploitogo.com", "afrikajob.net"],
    "BJ": ["anpe.bj", "emploi.bj", "afrikajob.net"],
    "CD": ["onem.cd", "emploicd.net", "afrikajob.net"],
    "MG": ["emploi.mg", "afrikajob.net"],
    "RW": ["rdb.rw", "afrikajob.net"],
    "KE": ["brightermonday.co.ke", "myjobmag.co.ke"],
    "NG": ["jobberman.com", "myjobmag.com", "ngcareers.com"],
    "GH": ["jobsinghana.com", "myjobmag.com"],
    "ZA": ["pnet.co.za", "careers24.com", "jobplacements.com"],
    "MA": ["anapec.org", "rekrute.com", "emploi.ma"],
    "TN": ["aneti.nat.tn", "tunisietravail.net", "emploi.com.tn"],
    "DZ": ["anem.dz", "emploitic.com", "emploialgerie.com"],
    "FR": ["pole-emploi.fr", "apec.fr", "cadremploi.fr"],
    "CA": ["emploiquebec.gouv.qc.ca", "jobboom.com"],
}

# Noms lisibles pour les agences nationales (pour l'affichage source)
_NOM_AGENCE: dict[str, str] = {
    "fne.cm": "FNE Cameroun", "ninajob.cm": "NinaJob", "237jobs.com": "237Jobs",
    "anpe.ci": "ANPE Côte d'Ivoire", "anpej.sn": "ANPEJ Sénégal",
    "gabon-emploi.org": "ONE Gabon", "anpe.bf": "ANPE Burkina",
    "anpe.ml": "ANPE Mali", "anpe.tg": "ANPE Togo", "anpe.bj": "ANPE Bénin",
    "onem.cd": "ONEM Congo", "anapec.org": "ANAPEC Maroc",
    "pole-emploi.fr": "France Travail", "apec.fr": "APEC",
    "jobberman.com": "Jobberman", "rekrute.com": "Rekrute",
    "afrikajob.net": "AfrikaJob",
}

async def _fetch_sites_locaux(mots_cles: str, pays: str, info: dict) -> list[dict]:
    """Recherche ciblée sur les sites d'emploi locaux et agences nationales via Serper.dev."""
    api_key = os.getenv("SERPER_API_KEY", "") or os.getenv("SERPAPI_KEY", "")
    if not api_key or api_key.startswith("VOTRE"):
        return []

    sites = _SITES_EMPLOI_LOCAUX.get(pays.upper(), [])
    if not sites:
        return []

    try:
        import httpx
        site_query = " OR ".join(f"site:{s}" for s in sites[:6])
        q = f"{mots_cles} emploi ({site_query})"

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                json={"q": q, "gl": info["gl"], "hl": info["hl"], "num": 20},
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            )
        if resp.status_code != 200:
            return []

        data = resp.json()
        offres = []
        for r in data.get("organic", []):
            url = r.get("link", "")
            # Identifier la source depuis l'URL
            source_nom = next(
                (_NOM_AGENCE.get(s, s) for s in sites if s in url),
                info["nom"]
            )
            titre = r.get("title", "").strip()
            if not titre or len(titre) < 5:
                continue
            offres.append({
                "titre":            titre[:150],
                "entreprise":       "Voir annonce",
                "lieu":             info["nom"],
                "resume":           (r.get("snippet", "") or "")[:600],
                "url":              url,
                "source":           source_nom,
                "source_type":      "reel",
                "date_publication": r.get("date", "Récent"),
                "type_contrat":     "Non précisé",
                "salaire":          "",
                "score":            0,
            })
        return offres

    except Exception as e:
        logger.debug(f"[SchedulerEmploi] Sites locaux erreur: {e}")
        return []


# ── Source 5 : Jooble API ─────────────────────────────────────────────────────
# Agrégateur international avec bonne couverture africaine.

async def _fetch_jooble(mots_cles: str, pays: str, info: dict) -> list[dict]:
    api_key = os.getenv("JOOBLE_API_KEY", "")
    if not api_key or api_key.startswith("VOTRE"):
        return []

    try:
        import httpx
        payload = {
            "keywords": mots_cles,
            "location": info.get("jooble_loc", pays),
        }
        url = f"https://jooble.org/api/{api_key}"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
        if resp.status_code != 200:
            return []

        data = resp.json()
        offres = []
        for job in data.get("jobs", [])[:20]:
            offres.append({
                "titre":            job.get("title", "")[:150],
                "entreprise":       job.get("company", "Non précisé"),
                "lieu":             job.get("location", info["nom"]),
                "resume":           re.sub(r"<[^>]+>", " ", job.get("snippet", "") or "")[:600],
                "url":              job.get("link", ""),
                "source":           "Jooble",
                "source_type":      "reel",
                "date_publication": (job.get("updated", "") or "")[:10],
                "type_contrat":     job.get("type", "Non précisé"),
                "salaire":          job.get("salary", ""),
                "score":            0,
            })
        return offres
    except Exception as e:
        logger.debug(f"[SchedulerEmploi] Jooble erreur: {e}")
        return []


# ── Scoring ───────────────────────────────────────────────────────────────────

def _scorer_offres(offres: list[dict], profil) -> list[dict]:
    """
    Scoring hybride :
      - TF-IDF cosine similarity (sklearn) entre profil et texte offre
      - Bonus : correspondance pays, niveau, type contrat
      - Pénalité : offres simulées (score ≤ 55)
    """
    if not offres:
        return offres

    # Construire le vecteur de profil
    if profil:
        metier       = (getattr(profil, "metier", "") or "").lower()
        profil_texte = (getattr(profil, "profil_recherche_emploi", "") or "").lower()
        specialite   = (getattr(profil, "specialite", "") or "").lower()
        niveau       = (getattr(profil, "niveau", "") or "").lower()
        profil_str   = f"{metier} {profil_texte} {specialite}"
    else:
        profil_str, niveau = "", ""

    # Textes des offres
    textes_offres = [
        (o.get("titre", "") + " " + o.get("resume", "") + " " + o.get("entreprise", "")).lower()
        for o in offres
    ]

    # TF-IDF cosine similarity
    scores_tfidf = [0.0] * len(offres)
    if profil_str.strip():
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            corpus = [profil_str] + textes_offres
            vect = TfidfVectorizer(
                analyzer="word",
                ngram_range=(1, 2),
                min_df=1,
                stop_words=None,
            )
            tfidf_matrix = vect.fit_transform(corpus)
            sims = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
            scores_tfidf = sims.tolist()
        except Exception:
            # sklearn indisponible — fallback sur overlap simple
            mots_profil = set(w for w in profil_str.split() if len(w) >= 4)
            for i, texte in enumerate(textes_offres):
                if mots_profil:
                    overlap = sum(1 for m in mots_profil if m in texte)
                    scores_tfidf[i] = min(overlap / len(mots_profil), 1.0)

    niveaux_mots = {
        "junior":    ["junior", "débutant", "0-2 ans", "0-3 ans", "entry"],
        "senior":    ["senior", "confirmé", "expérimenté", "5 ans", "7 ans"],
        "expert":    ["expert", "lead", "principal", "head of"],
        "dirigeant": ["directeur", "dg", "daf", "drh", "ceo", "cfo", "vp "],
    }

    for i, offre in enumerate(offres):
        sim = scores_tfidf[i]
        # Base : 40 + jusqu'à 45 pts de similarité TF-IDF
        score = 40 + round(sim * 45)

        # Bonus niveau
        texte = textes_offres[i]
        for n, mots in niveaux_mots.items():
            if niveau == n and any(m in texte for m in mots):
                score += 8
                break

        # Bonus source premium (SerpAPI = offres plus récentes et précises)
        if offre.get("source_type") == "reel":
            score += 3
        if "SerpAPI" in offre.get("source", "") or "Google Jobs" in offre.get("source", ""):
            score += 5

        # Pénalité offre simulée
        if offre.get("source_type") == "simule":
            score = min(score, 55)

        offre["score"] = min(max(score, 1), 99)

    return offres


# ── Extraction mots-clés ──────────────────────────────────────────────────────

def _extraire_mots_cles(profil, extra: str = "") -> str:
    mots = []
    if profil:
        profil_emploi = (getattr(profil, "profil_recherche_emploi", "") or "").strip()
        metier        = (getattr(profil, "metier", "") or "").strip()

        if profil_emploi:
            for ligne in profil_emploi.split("\n"):
                l = ligne.strip()
                if l.lower().startswith("poste"):
                    poste = re.sub(r"^poste\s*[:：]?\s*", "", l, flags=re.IGNORECASE).strip()
                    if poste:
                        mots.append(poste)
                        break
            if not mots:
                # Utiliser les 60 premiers caractères de la description
                mots.append(profil_emploi[:60].strip())

        if not mots and metier and metier not in ("professionnel", "pro"):
            mots.append(metier.replace("_", " "))

    if extra:
        mots.append(extra)

    return " ".join(mots[:2]) if mots else ""


# ── Sauvegarde DB ─────────────────────────────────────────────────────────────

async def _sauvegarder_offres(user_id: int, offres: list[dict]):
    from core.database import async_session_maker
    from modules.pro.profil_pro import ProfilProfessionnelDB
    from sqlalchemy import update

    now = datetime.utcnow()
    async with async_session_maker() as db:
        result = await db.execute(
            update(ProfilProfessionnelDB)
            .where(ProfilProfessionnelDB.user_id == user_id)
            .values(
                offres_emploi_recentes=offres,
                derniere_recherche_emploi=now,
            )
        )
        await db.commit()
        if result.rowcount == 0:
            logger.error(f"[SchedulerEmploi] user {user_id}: aucun profil mis à jour (introuvable ?)")
            raise RuntimeError(f"Profil user {user_id} introuvable lors de la sauvegarde des offres")
    simules = sum(1 for o in offres if o.get("source_type") == "simule")
    reelles = len(offres) - simules
    logger.info(
        f"[SchedulerEmploi] user {user_id}: {reelles} offres réelles + {simules} suggestions IA sauvegardées"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normaliser_contrat(raw: str) -> str:
    r = (raw or "").lower()
    if "permanent" in r or "full_time" in r or "indéterminée" in r or "cdi" in r:
        return "CDI"
    if "contract" in r or "fixed" in r or "cdd" in r or "déterminée" in r:
        return "CDD"
    if "freelance" in r or "consultant" in r:
        return "Freelance"
    if "part" in r:
        return "Temps partiel"
    if "intern" in r or "stage" in r:
        return "Stage"
    return raw or "Non précisé"


def _fmt_salaire(mini, maxi) -> str:
    if mini and maxi:
        return f"{int(mini):,} – {int(maxi):,}"
    if mini:
        return f"À partir de {int(mini):,}"
    return ""
