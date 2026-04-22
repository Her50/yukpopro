"""
Script de réparation du corpus RAG.

Actions :
  1. Supprime les chunks corrompus (navigation web au lieu de texte légal)
  2. Indexe les PDFs locaux valides qui n'ont pas encore de chunks
  3. Force le re-téléchargement des sources dont les URLs ont été corrigées
  4. Télécharge et indexe le Code CIMA depuis droit-afrique.com

Usage :
  cd yukpo_assurance
  python scripts/reparer_rag.py              # Réparation complète
  python scripts/reparer_rag.py --dry-run    # Simuler sans modifier
  python scripts/reparer_rag.py --step 1     # Seulement nettoyer les corrompus
  python scripts/reparer_rag.py --step 2     # Seulement indexer les PDFs locaux
  python scripts/reparer_rag.py --step 3     # Seulement re-télécharger les sources corrigées
"""
import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("reparer_rag")

RAG_DIR  = Path(__file__).parent.parent / "data" / "rag_knowledge"
HASH_FILE = RAG_DIR / "hashes.json"

# ─── Sources dont les chunks sont corrompus (navigation web) ──────────────────
NAV_SCRAPE_DOCS = [
    "ohada_audcg",
    "ohada_aus",
    "ohada_auscgie",
    "ohada_actes_uniformes_page",
    "commerce_itc_trademap_ci",
    "commerce_itc_trademap_cm",
    "commerce_itc_trademap_sn",
    "commerce_omc_profils_pays",
    "marches_publics_bf",
    "marches_publics_ml",
    "marches_publics_ne",
    "normes_inrs_prevention",
    "normes_iso_26000_rse",
    "stats_cg_cnsee_publications",
    "stats_cm_ins_eesi3",
    "commerce_brvm",
]

# ─── PDFs locaux scannés (images) — supprimer et re-télécharger en HTML texte ─
SCANNED_PDF_DOCS = [
    "cc_cg_interpro",
    "cc_cm_banques",
    "cc_cm_interpro",
    "cc_ga_interpro",
    "cc_gn_interpro",
    "code_famille_sn",
    "code_travail_bf",
    "code_travail_cg",
    "code_travail_gn",
]

# ─── Sources dont l'URL a été corrigée (forcer re-téléchargement) ─────────────
SOURCES_CORRIGEES = [
    "ohada_audcg",
    "ohada_aus",
    "ohada_auscgie",
    "marches_publics_bf",
    "marches_publics_ml",
    "marches_publics_ne",
    "normes_inrs_prevention",
    "commerce_itc_trademap_ci",
    "commerce_itc_trademap_cm",
    "commerce_itc_trademap_sn",
    "code_cima_pdf",
    # PDFs scannés — re-télécharger depuis sources HTML textuelles
    "cc_cg_interpro",
    "cc_cm_banques",
    "cc_cm_interpro",
    "cc_ga_interpro",
    "cc_gn_interpro",
    "code_famille_sn",
    "code_travail_bf",
    "code_travail_cg",
    "code_travail_gn",
]


# ══════════════════════════════════════════════════════════════════════════════
# Étape 1 — Nettoyer les chunks corrompus
# ══════════════════════════════════════════════════════════════════════════════

def etape1_nettoyer_corrompus(dry_run: bool) -> int:
    """Supprime chunks.json et embeddings.npz pour les sources NAV_SCRAPE."""
    print("\n" + "=" * 70)
    print("  ÉTAPE 1 — Nettoyage des chunks corrompus (navigation web)")
    print("=" * 70)

    supprimes = 0
    for doc_id in NAV_SCRAPE_DOCS:
        dossier = RAG_DIR / doc_id
        chunks_f = dossier / "chunks.json"
        embed_f  = dossier / "embeddings.npz"

        if not chunks_f.exists():
            print(f"  [SKIP] {doc_id} — pas de chunks.json")
            continue

        # Vérifier si les chunks sont corrompus
        try:
            with open(chunks_f, encoding="utf-8") as f:
                data = json.load(f)
            chunks = data.get("chunks", [])
            sample = " ".join(c.get("texte", c.get("text", "")) for c in chunks[:3])
            nav_kw = ["Connexion", "Inscription", "[image]", "Lire la suite", "navigation", "trademap"]
            is_corrupt = any(kw in sample for kw in nav_kw) or len(sample) < 50
        except Exception:
            is_corrupt = True

        if is_corrupt:
            if dry_run:
                print(f"  [DRY] {doc_id} — supprimerais chunks.json + embeddings.npz")
            else:
                chunks_f.unlink(missing_ok=True)
                embed_f.unlink(missing_ok=True)
                print(f"  [OK]  {doc_id} — chunks.json + embeddings.npz supprimés")
            supprimes += 1
        else:
            print(f"  [OK?] {doc_id} — chunks semblent valides, aucune action")

    print(f"\n  -> {supprimes} sources nettoyées")
    return supprimes


# ══════════════════════════════════════════════════════════════════════════════
# Étape 2 — Indexer les PDFs locaux valides
# ══════════════════════════════════════════════════════════════════════════════

def etape2_indexer_locaux(dry_run: bool) -> int:
    """Indexe les PDFs locaux valides qui n'ont pas encore de chunks."""
    from modules.rag.sources_registry import SOURCES
    from modules.rag.pdf_processor import traiter_pdf
    from modules.rag.rag_embedder import rag_embedder_manager

    print("\n" + "=" * 70)
    print("  ÉTAPE 2 — Indexation des PDFs locaux valides")
    print("=" * 70)

    # Construire un index sources_registry pour accéder aux métadonnées
    sources_dict = {s.doc_id: s for s in SOURCES}

    indexees = 0
    for doc_id in LOCAL_PDF_DOCS:
        dossier  = RAG_DIR / doc_id
        pdf_f    = dossier / "source.pdf"
        chunks_f = dossier / "chunks.json"
        embed_f  = dossier / "embeddings.npz"

        if not pdf_f.exists():
            print(f"  [SKIP] {doc_id} — source.pdf manquant")
            continue

        if chunks_f.exists():
            print(f"  [SKIP] {doc_id} — déjà indexé")
            continue

        pdf_size = pdf_f.stat().st_size
        if pdf_size < 10_000:
            print(f"  [SKIP] {doc_id} — PDF trop petit ({pdf_size} octets), probablement corrompu")
            continue

        if dry_run:
            print(f"  [DRY] {doc_id} — indexerais {pdf_size//1024} KB")
            continue

        print(f"  [>>]  {doc_id} — indexation {pdf_size//1024} KB…")

        # Récupérer les métadonnées du registre
        source = sources_dict.get(doc_id)
        metadata = {
            "doc_id":     doc_id,
            "nom":        source.nom if source else doc_id,
            "pays":       source.pays if source else "INCONNU",
            "zone":       source.zone if source else "NATIONAL",
            "domaine":    source.domaine if source else "general",
            "metier_tags": source.metier_tags if source else [],
            "fiabilite":  source.fiabilite.value if source else "semi_officiel",
            "url_source": source.url_principale if source else "",
            "hash":       hashlib.sha256(pdf_f.read_bytes()).hexdigest(),
            "indexe_le":  datetime.utcnow().isoformat(),
        }

        try:
            pdf_bytes = pdf_f.read_bytes()
            nb_chunks = traiter_pdf(
                pdf_bytes=pdf_bytes,
                doc_id=doc_id,
                metadata=metadata,
                chemin_sortie=chunks_f,
            )

            if nb_chunks == 0:
                print(f"  [ERR] {doc_id} — 0 chunks extraits (PDF non-texte / scanné?)")
                continue

            # Calcul des embeddings
            ok = rag_embedder_manager.charger_index(doc_id)
            if ok:
                print(f"  [OK]  {doc_id} — {nb_chunks} chunks indexés + embeddings OK")
                indexees += 1
            else:
                print(f"  [WARN] {doc_id} — {nb_chunks} chunks indexés mais embeddings ÉCHOUÉ")
                indexees += 1

        except Exception as e:
            print(f"  [ERR] {doc_id} — Exception : {e}")

    print(f"\n  -> {indexees} sources indexées")
    return indexees


# ══════════════════════════════════════════════════════════════════════════════
# Étape 3 — Re-télécharger les sources corrigées
# ══════════════════════════════════════════════════════════════════════════════

async def etape3_retelechargement(dry_run: bool) -> int:
    """Force le re-téléchargement des sources dont l'URL a été corrigée."""
    from modules.rag.downloader import _charger_hashes, _sauvegarder_hashes
    from modules.rag.updater import traiter_source
    from modules.rag.sources_registry import SOURCES

    print("\n" + "=" * 70)
    print("  ÉTAPE 3 — Re-téléchargement des sources avec URLs corrigées")
    print("=" * 70)

    sources_dict = {s.doc_id: s for s in SOURCES}
    succes = 0

    # Vider les hashes des sources corrigées pour forcer le re-téléchargement
    if not dry_run:
        hashes = _charger_hashes()
        for doc_id in SOURCES_CORRIGEES:
            if doc_id in hashes:
                del hashes[doc_id]
        _sauvegarder_hashes(hashes)
        print("  [OK] Hashes effacés pour les sources corrigées")

    for doc_id in SOURCES_CORRIGEES:
        source = sources_dict.get(doc_id)
        if not source:
            print(f"  [SKIP] {doc_id} — absent du registre")
            continue

        if dry_run:
            print(f"  [DRY] {doc_id} — re-téléchargerait depuis {source.url_principale[:70]}…")
            continue

        print(f"  [>>]  {doc_id} — téléchargement depuis {source.url_principale[:65]}…")
        try:
            res = await traiter_source(source)
            statut = res.get("statut", "?")
            nb = res.get("nb_chunks", "?")
            if statut == "mis_a_jour":
                print(f"  [OK]  {doc_id} — {nb} chunks | statut: {statut}")
                succes += 1
            elif statut == "inchange":
                print(f"  [=]   {doc_id} — inchangé (même hash que nouveau contenu)")
                succes += 1
            else:
                print(f"  [ERR] {doc_id} — {res.get('erreur', statut)}")
        except Exception as e:
            print(f"  [ERR] {doc_id} — Exception : {e}")

        # Pause pour ne pas surcharger les serveurs
        await asyncio.sleep(3)

    print(f"\n  -> {succes} sources re-téléchargées avec succès")
    return succes


# ══════════════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════════════

async def main(args: argparse.Namespace) -> int:
    print(f"\n{'=' * 70}")
    print("  RÉPARATION CORPUS RAG — YukpoAssurance")
    if args.dry_run:
        print("  Mode : DRY-RUN (aucune modification)")
    print(f"{'=' * 70}")

    steps = args.step or [1, 2, 3]

    if 1 in steps:
        etape1_nettoyer_corrompus(args.dry_run)
        # Supprimer aussi les source.pdf scannés pour forcer re-téléchargement
        print("\n  Suppression des source.pdf scannés...")
        hashes = {}
        hash_file = RAG_DIR / "hashes.json"
        if hash_file.exists():
            with open(hash_file, encoding="utf-8") as f:
                hashes = json.load(f)
        for doc_id in SCANNED_PDF_DOCS:
            pdf_f = RAG_DIR / doc_id / "source.pdf"
            if pdf_f.exists():
                if not args.dry_run:
                    pdf_f.unlink()
                    if doc_id in hashes:
                        del hashes[doc_id]
                    print(f"  [OK]  {doc_id} — source.pdf scanné supprimé")
                else:
                    print(f"  [DRY] {doc_id} — supprimerait source.pdf scanné")
        if not args.dry_run:
            with open(hash_file, "w", encoding="utf-8") as f:
                json.dump(hashes, f, indent=2)

    if 2 in steps:
        etape2_indexer_locaux(args.dry_run)

    if 3 in steps:
        await etape3_retelechargement(args.dry_run)

    print(f"\n{'=' * 70}")
    print("  RÉPARATION TERMINÉE")
    print(f"{'=' * 70}\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Réparation du corpus RAG")
    parser.add_argument("--dry-run", action="store_true", help="Simuler sans modifier")
    parser.add_argument(
        "--step", type=int, nargs="+", choices=[1, 2, 3],
        help="Étapes à exécuter (1=nettoyer, 2=local, 3=re-télécharger). Défaut : toutes.",
    )
    sys.exit(asyncio.run(main(parser.parse_args())))
