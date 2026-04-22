"""
RAG Retriever — Interface de recherche unifiée pour le corpus réglementaire.

Point d'entrée unique pour tous les agents et routes API.
Combine recherche sémantique dense + filtrage par pays/domaine/métier.
Formate les résultats en contexte prêt à injecter dans le prompt IA.

Usage :
    from modules.rag.rag_retriever import rechercher_corpus_reglementaire
    contexte = rechercher_corpus_reglementaire("TVA sur les assurances", pays="CI")
"""
import logging
import re
from typing import Optional

from modules.rag.rag_embedder import rag_embedder_manager

# Extrait les numéros d'articles mentionnés dans une question
_RE_NUM_ARTICLE = re.compile(
    r"(?:article|art\.?)\s+(\d{1,4}(?:\s*(?:bis|ter|quater|nouveau))?)",
    re.IGNORECASE,
)

def _extraire_patterns_articles(question: str) -> list[str]:
    """
    Extrait les variantes textuelles d'un numéro d'article pour le lookup exact.
    Ex: "article 13 nouveau" → ["article 13 nouveau", "art. 13 nouveau", "art 13 nouveau",
                                 "Article 13", "ARTICLE 13 NOUVEAU"]
    """
    patterns = []
    for m in _RE_NUM_ARTICLE.finditer(question):
        num = m.group(1).strip()
        for prefix in ("article", "art.", "art"):
            patterns.append(f"{prefix} {num}")
    return patterns

logger = logging.getLogger("yukpo_assurance.rag.retriever")

# ─── Limites ──────────────────────────────────────────────────────────────────
MAX_CHARS_CHUNK     = 1200   # Taille max d'un chunk dans le contexte
MAX_CHARS_CONTEXTE  = 10000  # Budget total du contexte injecté dans le prompt
MAX_CHUNKS_RETOURNES = 8     # Nombre max de chunks retournés


# ══════════════════════════════════════════════════════════════════════════════
# Fonction principale
# ══════════════════════════════════════════════════════════════════════════════

def rechercher_corpus_reglementaire(
    question:       str,
    pays:           Optional[str]       = None,  # "CI", "CM", "SN"… ou None = tous
    domaine:        Optional[str]       = None,  # "fiscal", "travail"…
    doc_ids:        Optional[list[str]] = None,  # Forcer des doc_ids spécifiques
    metier:         Optional[str]       = None,  # Filtre par profil métier
    top_k:          int                 = MAX_CHUNKS_RETOURNES,
    seuil_score:    float               = 0.35,
) -> str:
    """
    Recherche les passages les plus pertinents du corpus réglementaire
    et retourne un contexte formaté pour injection dans le prompt IA.

    Retourne "" si aucun résultat pertinent trouvé.
    """
    if not question.strip():
        return ""

    # ── Résolution des filtres ────────────────────────────────────────────
    doc_ids_cibles = _resoudre_filtres(pays, domaine, doc_ids, metier)

    resultats_finaux: list[dict] = []

    # ── Pass 1 : Lookup exact par numéro d'article (prioritaire) ─────────
    # Si la question cite "article 13" / "art. 1382" etc., on cherche les
    # chunks qui contiennent littéralement ce numéro avant la recherche sémantique.
    patterns_articles = _extraire_patterns_articles(question)
    if patterns_articles:
        try:
            hits_exacts = rag_embedder_manager.rechercher_par_mots_cles(
                patterns_articles,
                doc_ids=doc_ids_cibles,
                top_k=4,
            )
            resultats_finaux.extend(hits_exacts)
        except Exception as e:
            logger.warning(f"[Retriever] Lookup article échoué : {e}")

    # ── Pass 2 : Recherche sémantique ────────────────────────────────────
    try:
        if doc_ids_cibles is not None:
            resultats_sem = rag_embedder_manager.rechercher(
                question,
                doc_ids=doc_ids_cibles,
                top_k_global=top_k,
                seuil_score=seuil_score,
            )
        else:
            resultats_sem = rag_embedder_manager.rechercher(
                question,
                top_k_global=top_k,
                seuil_score=seuil_score,
            )
        # Fusionner en évitant les doublons (même texte déjà dans les hits exacts)
        textes_exacts = {r.get("texte", "") for r in resultats_finaux}
        for r in resultats_sem:
            if r.get("texte", "") not in textes_exacts:
                resultats_finaux.append(r)
    except Exception as e:
        logger.warning(f"[Retriever] Recherche sémantique échouée : {e}")

    if not resultats_finaux:
        return ""

    # Trier : exact-match d'abord (score 0.95), puis sémantique par score
    resultats_finaux.sort(key=lambda x: x["score"], reverse=True)

    # ── Formatage contexte ────────────────────────────────────────────────
    return _formater_contexte(resultats_finaux[:top_k + 4], question)


# ══════════════════════════════════════════════════════════════════════════════
# Résolution des filtres
# ══════════════════════════════════════════════════════════════════════════════

def _resoudre_filtres(
    pays:     Optional[str],
    domaine:  Optional[str],
    doc_ids:  Optional[list[str]],
    metier:   Optional[str],
) -> Optional[list[str]]:
    """
    Retourne la liste des doc_ids correspondant aux filtres,
    ou None si aucun filtre (= recherche globale).
    """
    if doc_ids:
        return doc_ids  # Priorité aux doc_ids explicites

    if not pays and not domaine and not metier:
        return None  # Recherche globale

    from modules.rag.sources_registry import SOURCES
    cibles = []
    for source in SOURCES:
        if pays   and source.pays    != pays    and source.pays != "TRANSNATIONAL":
            continue
        if domaine and source.domaine != domaine:
            continue
        if metier  and metier not in source.metier_tags:
            continue
        cibles.append(source.doc_id)

    return cibles if cibles else None


# ══════════════════════════════════════════════════════════════════════════════
# Formatage contexte → prompt IA
# ══════════════════════════════════════════════════════════════════════════════

def _formater_contexte(resultats: list[dict], question: str) -> str:
    """
    Formate les chunks récupérés en bloc de contexte injecté dans le prompt.
    Même structure que le contexte CIMA pour cohérence.
    """
    parties = []
    total_chars = 0

    # Dédupliquer par texte (éviter les doublons inter-sources)
    vus = set()

    for res in resultats:
        if total_chars >= MAX_CHARS_CONTEXTE:
            break

        texte = res.get("texte", "").strip()
        if not texte or texte in vus:
            continue
        vus.add(texte)

        # Tronquer si nécessaire
        if len(texte) > MAX_CHARS_CHUNK:
            texte = texte[:MAX_CHARS_CHUNK] + "…"

        meta     = res.get("metadata", {})
        doc_id   = res.get("doc_id", "")
        score    = res.get("score", 0.0)
        nom_doc  = meta.get("nom_doc") or meta.get("nom", doc_id)
        pays     = meta.get("pays", "")
        domaine  = meta.get("domaine", "")

        # En-tête du chunk
        en_tete_parts = [f"**{nom_doc}**"]
        if pays and pays != "TRANSNATIONAL":
            en_tete_parts.append(f"Pays : {pays}")
        if domaine:
            en_tete_parts.append(f"Domaine : {domaine}")
        en_tete_parts.append(f"Pertinence : {score:.2f}")
        en_tete = " | ".join(en_tete_parts)

        bloc = f"#### {en_tete}\n{texte}"
        parties.append(bloc)
        total_chars += len(bloc)

    if not parties:
        return ""

    header = (
        "=== CORPUS RÉGLEMENTAIRE — PASSAGES PERTINENTS ===\n"
        f"Question : {question[:100]}\n"
        f"Sources : {len(parties)} passage(s) | Corpus : OHADA · SYSCOHADA · CGI · Code Travail · COBAC · Code Civil · Code Pénal · UEMOA · CEMAC\n"
        "=" * 50 + "\n"
    )
    footer = (
        "\n" + "=" * 50 + "\n"
        "INSTRUCTIONS STRICTES POUR L'IA :\n"
        "1. Cite les passages ci-dessus avec leur source EXACTE (nom du texte, article, pays).\n"
        "2. Reproduis le texte officiel TEL QUEL — sans le modifier ni le paraphraser.\n"
        "3. Tu peux ensuite apporter une ANALYSE SEPAREE, CLAIREMENT ETIQUETEE '[ANALYSE]' :\n"
        "   - Impact pratique concret pour le professionnel concerné.\n"
        "   - Articulation avec d'autres textes (OHADA vs droit national, SYSCOHADA, COBAC, UEMOA).\n"
        "   - Sanctions / conséquences du non-respect avec les montants disponibles dans le corpus.\n"
        "4. INTERDIT : Si un passage est court, reproduis-le tel quel — N'invente PAS de contenu\n"
        "   supplémentaire. N'utilise PAS tes connaissances générales pour compléter le texte.\n"
        "5. Si une information manque dans le corpus, indique EXPLICITEMENT :\n"
        "   'Cette information n'est pas dans notre corpus documentaire — consultez les textes officiels.'\n"
        "   Propose d'orienter l'utilisateur vers les sources officielles (OHADA, CRCA, etc.).\n"
        "6. Adapte le niveau de l'analyse au contexte du pays et au profil utilisateur.\n"
        "=" * 50
    )

    return header + "\n\n".join(parties) + footer


# ══════════════════════════════════════════════════════════════════════════════
# Recherche structurée par profil métier
# ══════════════════════════════════════════════════════════════════════════════

# Mapping profil métier → domaines prioritaires
_METIER_DOMAINES: dict[str, list[str]] = {
    # ── Comptabilité / Finance ──────────────────────────────────────────────────
    "comptable":             ["fiscal", "comptabilite", "commercial"],
    "fiscaliste":            ["fiscal", "commercial"],
    "auditeur":              ["fiscal", "comptabilite", "commercial"],
    "daf":                   ["fiscal", "comptabilite", "banque", "commercial"],
    "DAF":                   ["fiscal", "comptabilite", "banque", "commercial"],
    # ── RH / Social ────────────────────────────────────────────────────────────
    "drh":                   ["conventions_collectives", "travail", "civil"],
    "DRH":                   ["conventions_collectives", "travail", "civil"],
    "gestionnaire_rh":       ["conventions_collectives", "travail"],
    # ── Juridique ──────────────────────────────────────────────────────────────
    "juriste":               ["civil", "penal", "commercial", "travail", "conventions_collectives", "marches_publics"],
    "avocat":                ["civil", "penal", "commercial", "travail", "conventions_collectives", "marches_publics"],
    "notaire":               ["civil", "commercial", "fiscal"],
    "juriste_entreprise":    ["civil", "commercial", "travail", "conventions_collectives", "fiscal"],
    # ── Banque / Finance de marché ─────────────────────────────────────────────
    "banquier":              ["banque", "fiscal", "commercial"],
    "analyste_credit":       ["banque", "fiscal"],
    "trader":                ["banque", "commercial"],
    "gestionnaire_actifs":   ["banque", "fiscal", "commercial"],
    "financier":             ["banque", "fiscal", "comptabilite"],
    # ── Ingénierie / BTP ───────────────────────────────────────────────────────
    "ingenieur":             ["marches_publics", "commercial", "minier"],
    "architecte":            ["marches_publics", "commercial"],
    "chef_projet":           ["marches_publics", "commercial"],
    "conducteur_travaux":    ["marches_publics", "commercial"],
    # ── Commerce / Business ────────────────────────────────────────────────────
    "commercial":            ["commercial", "fiscal"],
    "directeur_commercial":  ["commercial", "fiscal", "marches_publics"],
    "entrepreneur":          ["commercial", "fiscal", "travail"],
    "consultant":            ["commercial", "fiscal"],
    "acheteur":              ["marches_publics", "commercial"],
    "acheteur_public":       ["marches_publics"],
    # ── Data / Statistiques ────────────────────────────────────────────────────
    "daa":                   ["fiscal", "commercial", "comptabilite"],
    "data_analyst":          ["fiscal", "commercial", "comptabilite"],
    "data_scientist":        ["fiscal", "commercial", "comptabilite"],
    "statisticien":          ["fiscal", "commercial"],
    # ── Santé ──────────────────────────────────────────────────────────────────
    "medecin":               ["sante"],
    "pharmacien":            ["sante"],
    # ── Nouveaux métiers Afrique francophone ───────────────────────────────────
    "charge_projets_ong":    ["commercial", "travail", "fiscal"],
    "coordinateur_ong":      ["commercial", "travail", "fiscal"],
    "charge_programme":      ["commercial", "travail"],
    "responsable_microfinance": ["banque", "fiscal", "travail"],
    "credit_officer":        ["banque", "fiscal"],
    "agent_microfinance":    ["banque", "fiscal"],
    "transitaire":           ["commercial", "fiscal"],
    "douanier":              ["commercial", "fiscal"],
    "agent_transit":         ["commercial", "fiscal"],
    # ── Assurance ──────────────────────────────────────────────────────────────
    "assureur":              ["civil", "penal", "commercial"],  # CIMA géré séparément
}


def rechercher_pour_metier(
    question: str,
    metier:   str,
    pays:     Optional[str] = None,
    top_k:    int = 8,
) -> str:
    """
    Recherche globale pilotée par le contexte de la question.
    Le profil métier n'applique aucun filtre dur : il ajoute un boost de 10 %
    sur les domaines prioritaires pour ce métier (tie-breaking uniquement).
    Un DRH qui pose une question fiscale verra les CGI ; un comptable qui
    demande une clause de licenciement verra les codes du travail.
    """
    from modules.rag.sources_registry import SOURCES

    # ── 1. Résolution du filtre pays (seul filtre dur conservé) ──────────────
    doc_ids_pays: Optional[list[str]] = None
    if pays:
        doc_ids_pays = [
            s.doc_id for s in SOURCES
            if s.pays == pays or s.pays == "TRANSNATIONAL"
        ]

    # ── 2. Recherche sémantique globale ───────────────────────────────────────
    candidats = rag_embedder_manager.rechercher(
        question,
        doc_ids=doc_ids_pays,
        top_k_global=top_k * 3,   # pool large avant le boost
        seuil_score=0.28,
    )

    if not candidats:
        return ""

    # ── 3. Boost soft pour les domaines prioritaires du métier (+10 %) ────────
    domaines_prioritaires = set(_METIER_DOMAINES.get(metier, []))
    if domaines_prioritaires:
        domaine_par_doc = {s.doc_id: s.domaine for s in SOURCES}
        candidats = [
            {**r, "score": r["score"] * 1.10}
            if domaine_par_doc.get(r.get("doc_id", "")) in domaines_prioritaires
            else r
            for r in candidats
        ]

    candidats.sort(key=lambda x: x["score"], reverse=True)
    return _formater_contexte(candidats[:top_k], question)


# ══════════════════════════════════════════════════════════════════════════════
# Statistiques disponibilité
# ══════════════════════════════════════════════════════════════════════════════

def stats_corpus() -> dict:
    """Retourne les statistiques du corpus réglementaire chargé."""
    stats = rag_embedder_manager.stats()

    from modules.rag.sources_registry import SOURCES, PAYS_COUVERTS
    return {
        **stats,
        "pays_couverts":   PAYS_COUVERTS,
        "total_sources":   len(SOURCES),
        "sources_indexees": list(stats["index_charges"].keys()),
    }
