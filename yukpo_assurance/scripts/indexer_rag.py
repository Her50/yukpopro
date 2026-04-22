"""
Script CLI — Ingestion/mise à jour du corpus RAG.

Usage :
  python scripts/indexer_rag.py              # Indexe uniquement les sources manquantes
  python scripts/indexer_rag.py --all        # Force la réindexation de toutes les sources
  python scripts/indexer_rag.py --domaine civil penal   # Filtre par domaine
  python scripts/indexer_rag.py --pays CI CM SN         # Filtre par pays
  python scripts/indexer_rag.py --doc-id code_civil_ci  # Source unique

Options supplémentaires :
  --parallele N   Nombre de téléchargements simultanés (défaut : 3)
  --dry-run       Liste les sources à indexer sans les télécharger
"""
import argparse
import asyncio
import logging
import sys
import os
from pathlib import Path

# Ajouter le répertoire parent au PYTHONPATH pour les imports relatifs
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("indexer_rag")

# Réduire le bruit des libs tierces
for noisy in ("httpx", "httpcore", "urllib3", "PIL", "pdfminer"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


async def run(args: argparse.Namespace) -> int:
    from modules.rag.sources_registry import SOURCES
    from modules.rag.downloader import chemin_json_chunks
    from modules.rag.updater import traiter_source, forcer_mise_a_jour

    # ── Sélection des sources ──────────────────────────────────────────────
    sources = list(SOURCES)

    if args.doc_id:
        sources = [s for s in sources if s.doc_id in args.doc_id]
        if not sources:
            logger.error(f"Aucune source trouvée pour : {args.doc_id}")
            return 1

    if args.domaine:
        sources = [s for s in sources if s.domaine in args.domaine]

    if args.pays:
        pays_upper = [p.upper() for p in args.pays]
        sources = [s for s in sources if s.pays in pays_upper]

    if not args.all and not args.doc_id:
        # Par défaut : seulement les sources sans chunks.json
        sources = [s for s in sources if not chemin_json_chunks(s.doc_id).exists()]

    if not sources:
        logger.info("Aucune source à indexer (toutes déjà indexées). Utilise --all pour forcer.")
        return 0

    # ── Dry-run ────────────────────────────────────────────────────────────
    if args.dry_run:
        print(f"\n{'-'*70}")
        print(f"  DRY-RUN -- {len(sources)} sources a indexer :")
        print(f"{'-'*70}")
        for s in sources:
            statut = "[OK]     " if chemin_json_chunks(s.doc_id).exists() else "[MANQUANT]"
            print(f"  {statut} {s.doc_id:45} {s.pays:5} {s.domaine}")
        print(f"{'-'*70}\n")
        return 0

    # ── Indexation ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  INDEXATION RAG -- {len(sources)} sources")
    if args.all:
        print("  Mode : FORCE (reindexation complete)")
    else:
        print("  Mode : NOUVEAUTES (sources sans index)")
    print(f"{'='*70}\n")

    compteurs = {"succes": 0, "erreur": 0, "inchange": 0}
    erreurs_detail = []

    for i in range(0, len(sources), args.parallele):
        batch = sources[i : i + args.parallele]
        taches = []
        for s in batch:
            if args.all:
                taches.append(forcer_mise_a_jour(s.doc_id))
            else:
                taches.append(traiter_source(s))

        resultats = await asyncio.gather(*taches, return_exceptions=True)

        for s, res in zip(batch, resultats):
            if isinstance(res, Exception):
                compteurs["erreur"] += 1
                erreurs_detail.append((s.doc_id, str(res)))
                print(f"  ✗ {s.doc_id} — Exception : {res}")
            elif res.get("statut") == "mis_a_jour":
                compteurs["succes"] += 1
                chunks = res.get("nb_chunks", "?")
                print(f"  [OK] {s.doc_id} -- {chunks} chunks indexes [{s.pays}/{s.domaine}]")
            elif res.get("statut") == "inchange":
                compteurs["inchange"] += 1
                print(f"  [=] {s.doc_id} -- inchange (hash identique)")
            else:
                compteurs["erreur"] += 1
                err = res.get("erreur", "statut inconnu")
                erreurs_detail.append((s.doc_id, err))
                print(f"  [ERR] {s.doc_id} -- {err}")

        # Pause entre batches (respect serveurs sources)
        if i + args.parallele < len(sources):
            await asyncio.sleep(2)

    # ── Rapport final ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  RESULTAT : {compteurs['succes']} succes | "
          f"{compteurs['inchange']} inchanges | "
          f"{compteurs['erreur']} erreurs")
    print(f"{'='*70}")

    if erreurs_detail:
        print("\n  Erreurs détail :")
        for doc_id, err in erreurs_detail:
            print(f"    - {doc_id}: {err}")

    # Stats corpus après indexation
    try:
        from modules.rag.rag_embedder import rag_embedder_manager
        stats = rag_embedder_manager.stats()
        print(f"\n  Corpus chargé : {stats.get('nb_docs_charges', '?')} docs | "
              f"{stats.get('nb_chunks_total', '?')} chunks total")
    except Exception:
        pass

    print()
    return 0 if compteurs["erreur"] == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="Indexation du corpus RAG — YukpoAssurance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Forcer la réindexation de toutes les sources (même déjà indexées)",
    )
    parser.add_argument(
        "--domaine", nargs="+", metavar="DOM",
        help="Filtrer par domaine(s) : civil penal fiscal travail commercial …",
    )
    parser.add_argument(
        "--pays", nargs="+", metavar="PAYS",
        help="Filtrer par code(s) pays ISO : CI CM SN BJ …",
    )
    parser.add_argument(
        "--doc-id", nargs="+", metavar="ID",
        help="Indexer un ou plusieurs doc_id spécifiques",
    )
    parser.add_argument(
        "--parallele", type=int, default=3, metavar="N",
        help="Téléchargements simultanés (défaut : 3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Lister les sources sans télécharger",
    )

    args = parser.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
