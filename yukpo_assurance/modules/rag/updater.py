"""
RAG Updater — Orchestrateur de mise à jour automatique.

Scheduler asyncio (sans dépendance APScheduler).
Vérifie chaque source selon sa fréquence propre et orchestre :
  1. Détection de changement (downloader)
  2. Traitement PDF → chunks (pdf_processor)
  3. Re-calcul embeddings (rag_embedder)
  4. Notification (notifier)

Le scheduler tourne en arrière-plan dans le lifespan FastAPI.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from modules.rag.sources_registry import SOURCES, SourceDoc
from modules.rag.downloader import telecharger_si_change
from modules.rag.pdf_processor import traiter_pdf
from modules.rag.downloader import chemin_json_chunks
from modules.rag.rag_embedder import rag_embedder_manager
from modules.rag.notifier import rag_notifier

logger = logging.getLogger("yukpo_assurance.rag.updater")


# ══════════════════════════════════════════════════════════════════════════════
# Traitement d'une source
# ══════════════════════════════════════════════════════════════════════════════

async def traiter_source(source: SourceDoc) -> dict:
    """
    Pipeline complet pour une source :
    Détection → Téléchargement → PDF Processing → Embeddings → Notification.

    Retourne un dict de résultat pour le rapport.
    """
    logger.info(f"[Updater] Vérification : {source.doc_id} ({source.pays}/{source.domaine})")

    # ── 1. Vérifier et télécharger si changement ──────────────────────────
    result = await telecharger_si_change(source)

    if result.erreur:
        logger.warning(f"[Updater] {source.doc_id} — Erreur : {result.erreur}")
        await rag_notifier.notifier_echec(
            doc_id=source.doc_id,
            nom_doc=source.nom,
            erreur=result.erreur,
        )
        return {"doc_id": source.doc_id, "statut": "erreur", "erreur": result.erreur}

    if not result.a_change:
        logger.debug(f"[Updater] {source.doc_id} — Inchangé")
        return {"doc_id": source.doc_id, "statut": "inchange"}

    # ── 2. PDF → chunks JSON ──────────────────────────────────────────────
    metadata = {
        "nom":       source.nom,
        "pays":      source.pays,
        "zone":      source.zone,
        "domaine":   source.domaine,
        "metier_tags": source.metier_tags,
        "fiabilite": source.fiabilite.value,
        "url_source": result.url_utilisee,
        "hash":      result.hash,
        "indexe_le": datetime.utcnow().isoformat(),
    }

    nb_chunks = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: traiter_pdf(
            pdf_bytes=result.contenu,
            doc_id=source.doc_id,
            metadata=metadata,
            chemin_sortie=chemin_json_chunks(source.doc_id),
        ),
    )

    if nb_chunks == 0:
        erreur = "Extraction PDF a produit 0 chunks"
        await rag_notifier.notifier_echec(
            doc_id=source.doc_id,
            nom_doc=source.nom,
            erreur=erreur,
        )
        return {"doc_id": source.doc_id, "statut": "erreur", "erreur": erreur}

    # ── 3. Recalcul embeddings ─────────────────────────────────────────────
    rag_embedder_manager.invalider_index(source.doc_id)
    ok = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: rag_embedder_manager.charger_index(source.doc_id),
    )

    if not ok:
        erreur = "Calcul embeddings échoué"
        await rag_notifier.notifier_echec(
            doc_id=source.doc_id,
            nom_doc=source.nom,
            erreur=erreur,
        )
        return {"doc_id": source.doc_id, "statut": "erreur", "erreur": erreur}

    # ── 4. Notification succès ────────────────────────────────────────────
    logger.info(
        f"[Updater] ✅ {source.doc_id} mis à jour — "
        f"{nb_chunks} chunks | hash {result.hash[:12]}…"
    )
    await rag_notifier.notifier_mise_a_jour(
        doc_id=source.doc_id,
        nom_doc=source.nom,
        pays=source.pays,
        domaine=source.domaine,
        nb_chunks=nb_chunks,
        url=result.url_utilisee,
        hash_nouveau=result.hash,
    )

    return {
        "doc_id":    source.doc_id,
        "statut":    "mis_a_jour",
        "nb_chunks": nb_chunks,
        "hash":      result.hash,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Ingestion initiale (premier démarrage)
# ══════════════════════════════════════════════════════════════════════════════

async def ingestion_initiale(max_parallele: int = 3) -> dict:
    """
    Ingère toutes les sources qui n'ont pas encore de chunks.json sur disque.
    Exécutée une seule fois au premier démarrage.
    Parallélisme limité à max_parallele pour respecter les serveurs sources.
    """
    from modules.rag.downloader import chemin_json_chunks as cjc

    sources_manquantes = [
        s for s in SOURCES
        if not cjc(s.doc_id).exists()
    ]

    if not sources_manquantes:
        logger.info("[Updater] Ingestion initiale : toutes les sources déjà indexées")
        return {"statut": "deja_indexe", "nb_sources": len(SOURCES)}

    logger.info(
        f"[Updater] Ingestion initiale : {len(sources_manquantes)} sources à ingérer "
        f"(parallélisme : {max_parallele})"
    )

    resultats = {"mis_a_jour": 0, "erreurs": 0, "details": []}

    # Traitement par batch pour limiter la charge réseau
    for i in range(0, len(sources_manquantes), max_parallele):
        batch = sources_manquantes[i : i + max_parallele]
        taches = [traiter_source(s) for s in batch]
        resultats_batch = await asyncio.gather(*taches, return_exceptions=True)

        for res in resultats_batch:
            if isinstance(res, Exception):
                resultats["erreurs"] += 1
                logger.error(f"[Updater] Exception lors de l'ingestion : {res}")
            elif res.get("statut") == "mis_a_jour":
                resultats["mis_a_jour"] += 1
                resultats["details"].append(res)
            else:
                resultats["erreurs"] += 1
                resultats["details"].append(res)

        # Pause entre batches pour respecter les serveurs sources
        if i + max_parallele < len(sources_manquantes):
            await asyncio.sleep(2)

    logger.info(
        f"[Updater] Ingestion initiale terminée : "
        f"{resultats['mis_a_jour']} succès, {resultats['erreurs']} erreurs"
    )
    return resultats


# ══════════════════════════════════════════════════════════════════════════════
# Mise à jour forcée (API admin)
# ══════════════════════════════════════════════════════════════════════════════

async def forcer_mise_a_jour(doc_id: str) -> dict:
    """Force la mise à jour d'un document spécifique (contourne la détection de changement)."""
    from modules.rag.downloader import _charger_hashes, _sauvegarder_hashes
    source = next((s for s in SOURCES if s.doc_id == doc_id), None)
    if not source:
        return {"erreur": f"Source inconnue : {doc_id}"}

    # Supprimer le hash connu pour forcer le re-téléchargement
    hashes = _charger_hashes()
    if doc_id in hashes:
        del hashes[doc_id]
        _sauvegarder_hashes(hashes)

    return await traiter_source(source)


# ══════════════════════════════════════════════════════════════════════════════
# Scheduler asyncio
# ══════════════════════════════════════════════════════════════════════════════

class RAGScheduler:
    """
    Scheduler asyncio pour la vérification périodique des sources.
    Chaque source est vérifiée selon sa fréquence propre (check_freq_heures).
    """

    def __init__(self):
        self._tache:     Optional[asyncio.Task] = None
        self._actif:     bool = False
        # Prochaine vérification par source : doc_id → datetime
        self._prochaine: dict[str, datetime] = {}

    def demarrer(self) -> None:
        """Lance le scheduler en arrière-plan."""
        if self._actif:
            return
        self._actif = True
        # Planifier les premières vérifications avec délai initial
        # (laisser l'application démarrer avant la première vérification)
        now = datetime.utcnow()
        for source in SOURCES:
            # Première vérif dans 10 min + offset par source pour étaler la charge
            offset_min = SOURCES.index(source) * 2  # 2 min entre chaque source
            self._prochaine[source.doc_id] = now + timedelta(
                minutes=10 + offset_min
            )
        self._tache = asyncio.create_task(self._boucle())
        logger.info(
            f"[RAGScheduler] Démarré — {len(SOURCES)} sources surveillées. "
            f"Première vérification dans ~10 min."
        )

    async def arreter(self) -> None:
        """Arrête proprement le scheduler."""
        self._actif = False
        if self._tache and not self._tache.done():
            self._tache.cancel()
            try:
                await self._tache
            except asyncio.CancelledError:
                pass
        logger.info("[RAGScheduler] Arrêté")

    async def _boucle(self) -> None:
        """Boucle principale : vérifie les sources dont l'heure est venue."""
        while self._actif:
            try:
                now = datetime.utcnow()
                sources_a_verifier = [
                    s for s in SOURCES
                    if self._prochaine.get(s.doc_id, now) <= now
                ]

                if sources_a_verifier:
                    logger.info(
                        f"[RAGScheduler] {len(sources_a_verifier)} source(s) "
                        f"à vérifier cette heure"
                    )
                    # Traitement séquentiel pour ne pas surcharger les serveurs
                    for source in sources_a_verifier:
                        if not self._actif:
                            break
                        try:
                            await traiter_source(source)
                        except Exception as e:
                            logger.error(
                                f"[RAGScheduler] Exception sur {source.doc_id} : {e}"
                            )
                        # Planifier la prochaine vérification
                        self._prochaine[source.doc_id] = (
                            datetime.utcnow()
                            + timedelta(hours=source.check_freq_heures)
                        )
                        # Pause entre sources pour respecter les serveurs
                        await asyncio.sleep(5)

                # Rapport hebdomadaire (tous les lundis à 06:00 UTC)
                if now.weekday() == 0 and now.hour == 6 and now.minute < 60:
                    await self._rapport_hebdomadaire()

                # Vérifier toutes les 60 secondes
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[RAGScheduler] Erreur boucle : {e}")
                await asyncio.sleep(60)

    async def _rapport_hebdomadaire(self) -> None:
        """Génère et envoie le rapport hebdomadaire."""
        stats = rag_embedder_manager.stats()
        rapport = {
            "nb_docs":         stats["nb_docs_charges"],
            "nb_chunks_total": stats["nb_chunks_total"],
            "mis_a_jour":      0,   # Compteur reset chaque semaine
            "inchanges":       stats["nb_docs_charges"],
            "echecs":          len(SOURCES) - stats["nb_docs_charges"],
        }
        await rag_notifier.notifier_rapport_hebdo(rapport)

    def prochaines_verifications(self) -> dict:
        """Retourne les prochaines vérifications planifiées (pour l'API admin)."""
        return {
            doc_id: dt.isoformat()
            for doc_id, dt in sorted(
                self._prochaine.items(),
                key=lambda x: x[1],
            )
        }


# ─── Singleton ────────────────────────────────────────────────────────────────
rag_scheduler = RAGScheduler()
