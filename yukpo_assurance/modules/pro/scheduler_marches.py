"""
SchedulerMarches — Veille marchés publics par secteur d'activité.

Source UNIQUE désormais : **Serper.dev (Google Search)** avec 3 queries
enrichies — l'expérience prod a montré que dgMarket (404 depuis 2017),
UNGM legacy /Public/Notice/Search (302), et DevBusiness UN (page "Phase
Down" depuis 2024) sont tous morts. Au lieu de scraper 5 sources mortes,
on tape Google Search via Serper avec 3 stratégies complémentaires :

  Q1 — Recherche libre par mots-clés (last month)         → terrain large
  Q2 — Site-locked sur les plateformes ARMP locales pays  → précision pays
  Q3 — Recherche anglophone "tender procurement"          → international

Les **mots-clés** sont extraits via LLM (gpt-4.1-nano) à partir du profil
(metier + specialite + secteur_activite + entreprise + contexte_metier),
au lieu du dict statique de 30 métiers qui ratait tous les profils
spécifiques (notaire, agro-alimentaire, ingénieur en énergies renouvelables…).
Fallback sur des termes hard-codés si LLM indisponible.

Variables : SERPER_API_KEY (header X-API-KEY, POST google.serper.dev/search)

Cycle : toutes les 6 heures par défaut.
Stockage : ProfilProfessionnelDB.marches_publics_recents (JSON, max 15 avis).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta

logger = logging.getLogger("yukpo_assurance.pro.scheduler_marches")

_CYCLE_VERIFICATION = 2 * 60 * 60   # vérifier toutes les 2h
_FREQUENCE_DEFAUT   = 6              # heures entre deux recherches par user
_MAX_MARCHES        = 15

_running = False

# ── Plateformes d'appel d'offres par pays ─────────────────────────────────────
# Servent à site-locker la 2e query Serper pour des résultats hyper-locaux.

_PLATEFORMES_PAYS: dict[str, list[str]] = {
    "CM": ["armp.cm", "minmap.cm", "marchespublics.cm", "spm.cm"],
    "CI": ["marchespublics.ci", "armp-ci.org", "anrmp.ci"],
    "SN": ["marchespublics.sn", "dgcmp.sn", "armp.sn"],
    "GA": ["anrmp.ga", "marchespublics.ga"],
    "BF": ["arcop.bf", "marchespublics.bf"],
    "ML": ["armds.ml", "marchespublics.gov.ml"],
    "TG": ["armp.tg", "marchespublics.tg"],
    "BJ": ["armp.bj", "marchespublics.bj"],
    "CD": ["armp.cd", "marchespublics.gouv.cd"],
    "MG": ["armp.mg"],
    "MA": ["marchespublics.gov.ma", "mtpnet.gov.ma", "marchespublics.ma"],
    "TN": ["marchespublics.gov.tn"],
    "DZ": ["mfdgi.gov.dz"],
    "FR": ["boamp.fr", "marches-publics.info", "ted.europa.eu"],
    "BE": ["publicprocurement.be", "ted.europa.eu"],
    "CA": ["canadabuys.canada.ca", "seao.ca"],
    "NG": ["nigeriaprocurement.gov.ng", "bpp.gov.ng"],
    "GH": ["ppa.gov.gh"],
    "KE": ["tenders.go.ke"],
    "RW": ["rppa.gov.rw"],
}

# ── Mots-clés sectoriels de SECOURS si LLM indisponible ───────────────────────
# Conservés en filet de sécurité mais le chemin nominal passe par LLM.

_SECTEURS_FALLBACK: dict[str, list[str]] = {
    "comptable":     ["audit", "expertise comptable", "commissariat aux comptes"],
    "auditeur":      ["audit externe", "audit interne", "commissariat"],
    "financier":     ["services financiers", "trésorerie", "gestion budgétaire"],
    "fiscaliste":    ["conseil fiscal", "optimisation fiscale"],
    "actuaire":      ["actuariat", "assurance", "prévoyance"],
    "juriste":       ["conseil juridique", "assistance juridique", "contentieux"],
    "avocat":        ["représentation juridique", "conseil légal"],
    "notaire":       ["actes notariés", "authentification"],
    "ingenieur":     ["génie civil", "travaux", "construction", "infrastructure"],
    "architecte":    ["architecture", "maîtrise d'œuvre", "conception"],
    "topographe":    ["topographie", "géomètre", "cadastre"],
    "informaticien": ["systèmes d'information", "développement logiciel", "infogérance"],
    "developpeur":   ["développement web", "application mobile", "ERP", "CRM"],
    "telecom":       ["télécommunications", "réseaux", "fibre optique"],
    "medecin":       ["équipements médicaux", "santé publique", "médicaments"],
    "pharmacien":    ["médicaments", "produits pharmaceutiques"],
    "enseignant":    ["formation professionnelle", "e-learning", "édition scolaire"],
    "formateur":     ["formation", "renforcement de capacités", "séminaires"],
    "logisticien":   ["logistique", "transport", "fret", "supply chain"],
    "agronome":      ["agriculture", "semences", "irrigation"],
    "environnement": ["études environnementales", "impact environnemental", "eau"],
    "communicant":   ["communication institutionnelle", "événementiel"],
    "graphiste":     ["conception graphique", "identité visuelle", "imprimerie"],
    "drh":           ["recrutement", "conseil RH"],
    "professionnel": ["services", "conseil", "études"],
}


# ── Extraction mots-clés LLM-first ────────────────────────────────────────────

async def _extraire_mots_cles_marches_llm(profil) -> tuple[list[str], str]:
    """Génère 3-5 termes de recherche pertinents pour les appels d'offres
    à partir du profil professionnel, via LLM. Retourne (termes_fr, terme_en).

    Le LLM peut produire des termes adaptés à des métiers que le dict
    statique ne couvre pas (ex. ingénieur en énergies renouvelables,
    consultant IFRS, agro-alimentaire bio…).
    """
    metier      = (getattr(profil, "metier", "") or "").strip()
    specialite  = (getattr(profil, "specialite", "") or "").strip()
    secteur_act = (getattr(profil, "secteur_activite", "") or "").strip()
    entreprise  = (getattr(profil, "entreprise", "") or "").strip()
    ctx         = getattr(profil, "contexte_metier", None) or {}

    if not any([metier, specialite, secteur_act]):
        # Profil trop vide pour LLM, fallback direct
        return _mots_cles_fallback(profil), ""

    profil_desc = (
        f"Métier : {metier or '—'}\n"
        f"Spécialité : {specialite or '—'}\n"
        f"Secteur d'activité : {secteur_act or '—'}\n"
        f"Employeur : {entreprise or '—'}\n"
        f"Contexte : {', '.join(f'{k}={v}' for k, v in ctx.items() if v)[:200] or '—'}"
    )

    prompt = (
        "Tu es expert en marchés publics francophones (Afrique de l'Ouest + "
        "Maghreb + Europe). À partir du profil professionnel ci-dessous, "
        "génère 4 termes de recherche d'appels d'offres ET 1 terme équivalent "
        "en anglais (procurement / tender).\n\n"
        f"PROFIL :\n{profil_desc}\n\n"
        "Réponds STRICTEMENT en JSON (sans markdown, sans commentaire) :\n"
        '{"termes_fr": ["terme1", "terme2", "terme3", "terme4"], '
        '"terme_en": "english tender keyword"}\n\n'
        "Règles :\n"
        "- Termes spécifiques au secteur réel du profil (pas génériques).\n"
        "- Inclure 1 terme large (ex. 'audit') + 2 spécifiques + 1 produit/service.\n"
        "- 2-5 mots max par terme. Pas de stop-words.\n"
        "- Si métier flou, retomber sur le secteur d'activité ou employeur."
    )

    try:
        from core.ia_client import ia_client, ModeIA, ModelePrioritaire
        reponse_obj = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.ANALYSE,
            forcer_modele=ModelePrioritaire.CLAUDE_HAIKU,  # → gpt-4.1-nano (cf feedback_llm_routing)
            json_attendu=True,
        )
        # ia_client.appeler renvoie un ReponseIA — récupère le contenu textuel
        txt = (
            getattr(reponse_obj, "texte", None)
            or getattr(reponse_obj, "contenu", None)
            or getattr(reponse_obj, "content", None)
            or str(reponse_obj)
        ).strip()
        import json as _json
        if txt.startswith("```"):
            txt = re.sub(r"^```\w*\s*|\s*```$", "", txt).strip()
        data = _json.loads(txt)
        termes_fr = [t.strip() for t in (data.get("termes_fr") or []) if isinstance(t, str) and t.strip()]
        terme_en  = (data.get("terme_en") or "").strip()
        if termes_fr:
            logger.info(f"[SchedulerMarches] Termes LLM user={getattr(profil, 'user_id', '?')}: {termes_fr} | EN: {terme_en}")
            return termes_fr[:4], terme_en
    except Exception as e:
        logger.warning(f"[SchedulerMarches] LLM keywords KO ({e}) → fallback dict")

    return _mots_cles_fallback(profil), ""


def _mots_cles_fallback(profil) -> list[str]:
    """Filet de sécurité hard-codé si LLM indisponible."""
    metier = (getattr(profil, "metier", "") or "professionnel").lower().replace("_", " ")
    secteur_act = (getattr(profil, "secteur_activite", "") or "").lower()
    for cle, mots in _SECTEURS_FALLBACK.items():
        if cle in metier or metier in cle:
            return mots[:3]
    return [secteur_act or metier or "services", "conseil"]


# ── Point d'entrée public ──────────────────────────────────────────────────────

async def demarrer_scheduler_marches():
    global _running
    if _running:
        return
    _running = True
    logger.info("[SchedulerMarches] Démarrage veille marchés publics (Serper-only, 3 queries enrichies)")
    asyncio.create_task(_boucle_veille_marches(), name="scheduler_marches")


async def arreter_scheduler_marches():
    global _running
    _running = False


# ── Boucle principale ─────────────────────────────────────────────────────────

async def _boucle_veille_marches():
    await asyncio.sleep(90)   # délai initial décalé du scheduler emploi
    while _running:
        try:
            await _cycle_marches_tous_users()
        except Exception as e:
            logger.error(f"[SchedulerMarches] Erreur cycle: {e}")
        await asyncio.sleep(_CYCLE_VERIFICATION)


async def _cycle_marches_tous_users():
    try:
        from core.database import async_session_maker
        from modules.pro.profil_pro import ProfilProfessionnelDB
        from sqlalchemy import select

        async with async_session_maker() as db:
            result = await db.execute(select(ProfilProfessionnelDB).where(ProfilProfessionnelDB.actif == True))
            profils = result.scalars().all()

        if not profils:
            return

        now = datetime.utcnow()
        for profil in profils:
            try:
                derniere = getattr(profil, "derniere_recherche_marches", None)
                if derniere and (now - derniere) < timedelta(hours=_FREQUENCE_DEFAUT):
                    continue
                await rechercher_marches_pour_user(user_id=profil.user_id, profil=profil)
            except Exception as e:
                logger.error(f"[SchedulerMarches] Erreur user {profil.user_id}: {e}")

    except Exception as e:
        logger.error(f"[SchedulerMarches] Erreur cycle global: {e}")


# ── Recherche principale ───────────────────────────────────────────────────────

async def rechercher_marches_pour_user(user_id: int, profil=None) -> int:
    """Pipeline complet recherche marchés pour un utilisateur :
    1. Extraction mots-clés via LLM (fallback dict si LLM KO)
    2. 3 queries Serper complémentaires
    3. Dédoublonnage + scoring + sauvegarde
    """
    pays = (getattr(profil, "pays", None) or "CM").upper()
    from modules.pro.scheduler_emploi import _info_pays
    info = _info_pays(pays)

    termes_fr, terme_en = await _extraire_mots_cles_marches_llm(profil)
    logger.info(
        f"[SchedulerMarches] user={user_id} pays={pays} ({info['nom']}) "
        f"termes_fr={termes_fr} terme_en={terme_en or '(none)'}"
    )

    # ── Débit crédits (forfait recherche marchés : 2 FCFA × 20 = 40 crédits) ──
    try:
        from modules.pro.service_credits import debiter_forfait_fcfa
        ok, _, msg = await debiter_forfait_fcfa(user_id, cout_fcfa=2.0, module="recherche_marches")
        if not ok:
            logger.warning(f"[SchedulerMarches] Crédits insuffisants user {user_id}: {msg}")
            return 0
    except Exception as e:
        logger.debug(f"[SchedulerMarches] Débit crédits ignoré: {e}")

    # 3 queries Serper en parallèle (toutes facultatives, on prend tout ce qui rentre)
    resultats = await asyncio.gather(
        _serper_query_libre(termes_fr, pays, info),
        _serper_query_site_locked(termes_fr, pays, info),
        _serper_query_anglophone(terme_en or termes_fr[0] if termes_fr else "services", pays, info),
        return_exceptions=True,
    )

    marches_bruts: list[dict] = []
    noms = ["Serper-libre", "Serper-site-locked", "Serper-EN"]
    for nom, res in zip(noms, resultats):
        if isinstance(res, list):
            logger.info(f"[SchedulerMarches] {nom} user={user_id}: {len(res)} avis")
            marches_bruts.extend(res)
        elif isinstance(res, Exception):
            logger.warning(f"[SchedulerMarches] {nom} user={user_id} ERREUR: {res}")

    if not marches_bruts:
        logger.info(f"[SchedulerMarches] user={user_id}: 0 avis sur les 3 queries — sauvegarde liste vide")
        await _sauvegarder_marches(user_id, [])
        return 0

    # Dédoublonnage par URL (clé canonique) puis titre
    seen: set[str] = set()
    uniques: list[dict] = []
    for m in marches_bruts:
        key = (m.get("url") or m.get("titre", "")).strip().lower()[:120]
        if key and key not in seen:
            seen.add(key)
            uniques.append(m)

    # Scoring pertinence simple : présence des termes profil dans titre/résumé
    uniques = _scorer_marches(uniques, termes_fr)
    uniques.sort(key=lambda m: m.get("score", 0), reverse=True)
    uniques = uniques[:_MAX_MARCHES]

    await _sauvegarder_marches(user_id, uniques)
    logger.info(f"[SchedulerMarches] user={user_id}: {len(uniques)} avis sauvegardés (scoring + dedup)")
    return len(uniques)


# ── Source unique : Serper.dev avec 3 stratégies ──────────────────────────────

def _serper_api_key() -> str:
    return os.getenv("SERPER_API_KEY", "") or os.getenv("SERPAPI_KEY", "")


async def _serper_post(query: str, info: dict, num: int = 10, restrict_month: bool = True) -> list[dict]:
    """Appel HTTP Serper /search. Retourne organic results bruts."""
    api_key = _serper_api_key()
    if not api_key or api_key.startswith("VOTRE"):
        return []
    import httpx
    body = {"q": query, "gl": info["gl"], "hl": info["hl"], "num": num}
    if restrict_month:
        body["tbs"] = "qdr:m"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            json=body,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        )
    if resp.status_code != 200:
        logger.warning(f"[SchedulerMarches] Serper HTTP {resp.status_code} q={query!r}")
        return []
    return (resp.json() or {}).get("organic", []) or []


async def _serper_query_libre(termes: list[str], pays: str, info: dict) -> list[dict]:
    """Query 1 : recherche libre, 'appel d'offres {terme} {pays}', last month."""
    if not termes:
        return []
    terme = termes[0]
    q = f"appel d'offres {terme} {info['nom']}"
    organic = await _serper_post(q, info, num=10, restrict_month=True)
    if not organic:
        # Fallback : retire le filtre temporel si rien sur le dernier mois
        organic = await _serper_post(q, info, num=10, restrict_month=False)
    return _organic_to_marches(organic, pays, info, source_label="Google", secteur=terme)


async def _serper_query_site_locked(termes: list[str], pays: str, info: dict) -> list[dict]:
    """Query 2 : 'appel d'offres {terme} (site:armp.X OR site:...)' — précision pays."""
    if not termes:
        return []
    plateformes = _PLATEFORMES_PAYS.get(pays, [])
    if not plateformes:
        return []
    terme = termes[0]
    site_q = " OR ".join(f"site:{s}" for s in plateformes[:5])
    q = f"appel d'offres {terme} ({site_q})"
    organic = await _serper_post(q, info, num=10, restrict_month=True)
    if not organic:
        organic = await _serper_post(q, info, num=10, restrict_month=False)
    return _organic_to_marches(organic, pays, info, source_label="ARMP local", secteur=terme)


async def _serper_query_anglophone(terme_en: str, pays: str, info: dict) -> list[dict]:
    """Query 3 : 'tender procurement {EN} {pays}' — couvre ONU/UN/WorldBank/etc."""
    if not terme_en:
        return []
    q = f"tender procurement {terme_en} {info['nom']}"
    organic = await _serper_post(q, info, num=8, restrict_month=True)
    if not organic:
        organic = await _serper_post(q, info, num=8, restrict_month=False)
    return _organic_to_marches(organic, pays, info, source_label="International", secteur=terme_en)


def _organic_to_marches(
    organic: list[dict], pays: str, info: dict,
    source_label: str, secteur: str,
) -> list[dict]:
    """Convertit la liste organic Serper en marches au format DB."""
    out: list[dict] = []
    for r in organic:
        titre = (r.get("title") or "").strip()
        if not titre or len(titre) < 8:
            continue
        url = r.get("link", "")
        # Skip réseaux sociaux et homepages génériques
        if any(d in url for d in ("facebook.com", "linkedin.com/in/", "twitter.com", "youtube.com")):
            continue
        plateformes = _PLATEFORMES_PAYS.get(pays, [])
        source = next((p for p in plateformes if p in url), source_label)
        out.append({
            "titre":     titre[:200],
            "organisme": _extraire_organisme(r.get("displayedLink") or r.get("displayed_link", ""), r.get("snippet", "")),
            "lieu":      info["nom"],
            "resume":    (r.get("snippet") or "")[:500],
            "url":       url,
            "source":    source,
            "date_pub":  r.get("date", "Récent"),
            "secteur":   secteur,
            "score":     0,
        })
    return out


# ── Scoring pertinence ────────────────────────────────────────────────────────

def _scorer_marches(marches: list[dict], termes: list[str]) -> list[dict]:
    """Score 0-99 = base 40 + overlap mots-clés (titre/résumé) + bonus URL."""
    if not marches or not termes:
        for m in marches:
            m["score"] = 50
        return marches
    mots = set()
    for t in termes:
        for w in re.split(r"\s+", t.lower()):
            if len(w) >= 4:
                mots.add(w)
    for m in marches:
        texte = (m.get("titre", "") + " " + m.get("resume", "")).lower()
        overlap = sum(1 for w in mots if w in texte) if mots else 0
        score = 40 + min(45, round((overlap / max(1, len(mots))) * 45))
        # Bonus URL plateforme officielle
        if "armp" in m.get("url", "") or "marchespublics" in m.get("url", ""):
            score += 8
        # Bonus si "appel d'offres" / "tender" dans le titre
        if any(k in texte for k in ("appel d'offres", "tender", "procurement", "marché public")):
            score += 5
        m["score"] = min(99, max(1, score))
    return marches


# ── Sauvegarde DB ─────────────────────────────────────────────────────────────

async def _sauvegarder_marches(user_id: int, marches: list[dict]):
    from core.database import async_session_maker
    from modules.pro.profil_pro import ProfilProfessionnelDB
    from sqlalchemy import update

    async with async_session_maker() as db:
        result = await db.execute(
            update(ProfilProfessionnelDB)
            .where(ProfilProfessionnelDB.user_id == user_id)
            .values(
                marches_publics_recents=marches,
                derniere_recherche_marches=datetime.utcnow(),
            )
        )
        await db.commit()
        if result.rowcount == 0:
            logger.error(f"[SchedulerMarches] user {user_id}: aucun profil mis à jour (introuvable ?)")
            raise RuntimeError(f"Profil user {user_id} introuvable lors de la sauvegarde des marchés")
    logger.info(f"[SchedulerMarches] {len(marches)} avis sauvegardés pour user {user_id}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extraire_organisme(displayed_link: str, snippet: str) -> str:
    """Tente d'extraire le nom de l'organisme depuis les résultats Google."""
    m = re.search(r"(minist[eè]re|direction|agence|office|commune|région|mairie)\s+[^\.,]{3,40}", snippet, re.IGNORECASE)
    if m:
        return m.group(0).strip()[:80]
    m2 = re.search(r"([a-z0-9\-]+\.[a-z]{2,4})", displayed_link)
    return m2.group(1) if m2 else "Organisme public"
