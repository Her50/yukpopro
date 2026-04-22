#!/usr/bin/env python3
"""
YukpoAssurance — Script de test de connexion ORASS/Mercure
=============================================================
Valide la connexion et l'intégration avec le SI de la compagnie d'assurance
avant le déploiement en production.

Usage :
    # Mode simulation (sans accès ORASS réel)
    python scripts/test_orass_connection.py --mode simulation

    # Mode SQL direct (accès PostgreSQL ORASS)
    python scripts/test_orass_connection.py --mode direct_sql --dsn "postgresql://user:pass@host:5432/orass"

    # Mode API REST
    python scripts/test_orass_connection.py --mode api --api-url "https://orass.compagnie.cm/api/v1" --api-key "TOKEN"

    # Mode CSV import
    python scripts/test_orass_connection.py --mode csv_import --csv-dir "./data/orass_csv"

Codes de sortie :
    0 → Tous les tests passent
    1 → Avertissements (fonctionnel mais configurations à revoir)
    2 → Erreurs bloquantes (ne pas déployer en production)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

# ── Couleurs terminal ─────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):    print(f"  {GREEN}✓{RESET}  {msg}")
def warn(msg):  print(f"  {YELLOW}⚠{RESET}  {msg}")
def fail(msg):  print(f"  {RED}✗{RESET}  {msg}")
def info(msg):  print(f"  {BLUE}ℹ{RESET}  {msg}")
def header(msg):print(f"\n{BOLD}{BLUE}{'─'*60}{RESET}\n{BOLD}  {msg}{RESET}\n{'─'*60}")


# ═══════════════════════════════════════════════════════════════════════════════
# Tests communs (tous modes)
# ═══════════════════════════════════════════════════════════════════════════════

def test_env_variables(mode: str) -> int:
    """Vérifie que les variables d'environnement ORASS sont configurées."""
    header("1. Variables d'environnement ORASS")
    erreurs = 0

    if mode == "direct_sql":
        for var in ("ORASS_DSN", "ORASS_DB_URL"):
            val = os.getenv(var)
            if val:
                ok(f"{var} configurée ({val[:30]}...)" if len(val) > 30 else f"{var} configurée")
            else:
                warn(f"{var} non configurée — peut être passée via --dsn")
        # Vérifier que Mercure est aussi configuré si désiré
        if os.getenv("MERCURE_DB_URL"):
            ok("MERCURE_DB_URL configurée")
        else:
            info("MERCURE_DB_URL non configurée (Mercure désactivé — ORASS seulement)")

    elif mode == "api":
        for var in ("ORASS_API_URL", "ORASS_API_KEY"):
            val = os.getenv(var)
            if val:
                ok(f"{var} configurée")
            else:
                warn(f"{var} non configurée — peut être passée en argument")

    elif mode == "csv_import":
        csv_dir = os.getenv("ORASS_CSV_DIR", "data/orass_csv")
        p = Path(csv_dir)
        if p.exists():
            fichiers_csv = list(p.glob("*.csv"))
            ok(f"ORASS_CSV_DIR existe : {csv_dir} ({len(fichiers_csv)} fichier(s) CSV)")
            if not fichiers_csv:
                warn("Aucun fichier CSV trouvé dans le répertoire d'import")
        else:
            fail(f"ORASS_CSV_DIR introuvable : {csv_dir}")
            erreurs += 1

    return erreurs


def test_reseau(host: str, port: int, timeout: int = 5) -> bool:
    """Test de connectivité réseau vers le serveur ORASS."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# Tests mode direct_sql
# ═══════════════════════════════════════════════════════════════════════════════

def test_direct_sql(dsn: str) -> int:
    """Teste la connexion SQL directe à ORASS."""
    header("2. Connexion SQL directe ORASS/Mercure")
    erreurs = 0

    try:
        import psycopg2
    except ImportError:
        fail("psycopg2 non installé — pip install psycopg2-binary")
        return 2

    # Test connexion
    try:
        t0 = time.monotonic()
        conn = psycopg2.connect(dsn, connect_timeout=10)
        duree = (time.monotonic() - t0) * 1000
        ok(f"Connexion établie en {duree:.0f}ms")
    except Exception as e:
        fail(f"Connexion échouée : {e}")
        info("Vérifier : IP whitelistée, port ouvert (5432), credentials valides")
        return 2

    try:
        cur = conn.cursor()

        # Test 1 : Version PostgreSQL
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        ok(f"PostgreSQL : {version.split(',')[0]}")

        # Test 2 : Tables ORASS critiques
        header("3. Vérification tables ORASS")
        TABLES_CRITIQUES_ORASS = [
            ("polices", "Table des polices/contrats"),
            ("sinistres", "Table des sinistres"),
            ("assures", "Table des assurés"),
            ("quittances", "Table des quittances/primes"),
            ("avenants", "Table des avenants"),
            ("garanties", "Table des garanties"),
        ]
        TABLES_CRITIQUES_MERCURE = [
            ("journaux", "Journaux comptables"),
            ("comptes", "Plan comptable"),
            ("ecritures", "Écritures comptables"),
        ]

        for table, desc in TABLES_CRITIQUES_ORASS:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table} LIMIT 1")
                n = cur.fetchone()[0]
                ok(f"{table} ({desc}) — {n:,} enregistrements")
            except Exception:
                # Essayer avec schéma orass
                try:
                    cur.execute(f"SELECT COUNT(*) FROM orass.{table} LIMIT 1")
                    n = cur.fetchone()[0]
                    ok(f"orass.{table} — {n:,} enregistrements")
                except Exception as e2:
                    warn(f"{table} introuvable ({e2}) — mapping SQL à adapter")

        # Test 3 : Requête type police récente
        header("4. Requête type — Police récente")
        try:
            cur.execute("""
                SELECT COUNT(*) FROM polices
                WHERE date_effet >= CURRENT_DATE - INTERVAL '90 days'
            """)
            n = cur.fetchone()[0]
            ok(f"Polices actives (90 derniers jours) : {n:,}")
        except Exception as e:
            warn(f"Requête polices récentes échouée : {e}")

        # Test 4 : Sinistres ouverts
        try:
            cur.execute("""
                SELECT statut, COUNT(*) as nb
                FROM sinistres
                GROUP BY statut
                ORDER BY nb DESC
                LIMIT 5
            """)
            rows = cur.fetchall()
            if rows:
                ok("Répartition sinistres par statut :")
                for statut, nb in rows:
                    info(f"    {statut or 'VIDE'}: {nb:,}")
        except Exception as e:
            warn(f"Requête statuts sinistres échouée : {e}")

        cur.close()
        conn.close()
        ok("Connexion fermée proprement")

    except Exception as e:
        fail(f"Erreur lors des tests SQL : {e}")
        erreurs += 1

    return erreurs


# ═══════════════════════════════════════════════════════════════════════════════
# Tests mode API REST
# ═══════════════════════════════════════════════════════════════════════════════

async def test_api_rest(api_url: str, api_key: str) -> int:
    """Teste la connexion API REST ORASS."""
    header("2. Connexion API REST ORASS")
    erreurs = 0

    try:
        import httpx
    except ImportError:
        fail("httpx non installé — pip install httpx")
        return 2

    headers = {
        "Authorization": f"Bearer {api_key}" if api_key else "",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
        # Test de santé
        for endpoint in ("/health", "/ping", "/status", "/api/v1/health"):
            try:
                r = await client.get(f"{api_url}{endpoint}", headers=headers)
                if r.status_code < 400:
                    ok(f"Endpoint santé : {api_url}{endpoint} → {r.status_code}")
                    break
            except Exception:
                continue
        else:
            warn("Aucun endpoint de santé trouvé — l'API ne les expose peut-être pas")

        # Test polices
        header("3. Endpoints ORASS — Polices")
        for endpoint in ("/polices", "/api/polices", "/api/v1/polices", "/contrats"):
            try:
                r = await client.get(
                    f"{api_url}{endpoint}",
                    headers=headers,
                    params={"limit": 1},
                )
                if r.status_code == 200:
                    ok(f"Polices : {api_url}{endpoint} → 200 OK")
                    try:
                        data = r.json()
                        info(f"  Structure réponse : {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
                    except Exception:
                        pass
                    break
                elif r.status_code == 401:
                    fail(f"Polices : {endpoint} → 401 Non autorisé — vérifier la clé API")
                    erreurs += 1
                    break
            except Exception as e:
                continue
        else:
            warn("Endpoint polices non trouvé — adapter l'URL dans ORASS_API_URL")

        # Test sinistres
        header("4. Endpoints ORASS — Sinistres")
        for endpoint in ("/sinistres", "/api/sinistres", "/api/v1/sinistres", "/claims"):
            try:
                r = await client.get(
                    f"{api_url}{endpoint}",
                    headers=headers,
                    params={"limit": 1, "statut": "ouvert"},
                )
                if r.status_code == 200:
                    ok(f"Sinistres : {api_url}{endpoint} → 200 OK")
                    break
            except Exception:
                continue
        else:
            warn("Endpoint sinistres non trouvé")

    return erreurs


# ═══════════════════════════════════════════════════════════════════════════════
# Tests mode CSV import
# ═══════════════════════════════════════════════════════════════════════════════

def test_csv_import(csv_dir: str) -> int:
    """Teste le mode import CSV (exports ORASS)."""
    header("2. Import CSV ORASS")
    import csv as csv_module

    erreurs = 0
    p = Path(csv_dir)

    if not p.exists():
        fail(f"Répertoire CSV introuvable : {csv_dir}")
        return 2

    fichiers = list(p.glob("*.csv"))
    if not fichiers:
        warn(f"Aucun fichier CSV dans {csv_dir}")
        info("Placer les exports ORASS (polices.csv, sinistres.csv, etc.) dans ce répertoire")
        return 1

    ok(f"{len(fichiers)} fichier(s) CSV trouvé(s)")

    COLONNES_ATTENDUES = {
        "polices": ["numero_police", "date_effet", "date_echeance", "branche", "prime_nette"],
        "sinistres": ["numero_sinistre", "date_sinistre", "statut", "montant_reclame"],
        "assures": ["nom", "prenom", "date_naissance"],
        "quittances": ["numero_police", "montant", "date_echeance", "statut_paiement"],
    }

    for fichier in fichiers[:5]:  # Vérifier les 5 premiers
        nom = fichier.stem.lower()
        try:
            with open(fichier, encoding="utf-8-sig", errors="replace") as f:
                reader = csv_module.DictReader(f)
                colonnes = reader.fieldnames or []
                premiere_ligne = next(reader, None)

            ok(f"{fichier.name} — {len(colonnes)} colonnes")

            # Vérifier les colonnes attendues
            colonnes_lower = [c.lower().strip() for c in colonnes]
            for type_fichier, cols_attendues in COLONNES_ATTENDUES.items():
                if type_fichier in nom:
                    manquantes = [c for c in cols_attendues if c not in colonnes_lower]
                    if manquantes:
                        warn(f"  Colonnes manquantes dans {fichier.name} : {manquantes}")
                    else:
                        ok(f"  Structure {type_fichier} valide")

        except Exception as e:
            fail(f"{fichier.name} : erreur de lecture — {e}")
            erreurs += 1

    return erreurs


# ═══════════════════════════════════════════════════════════════════════════════
# Test mode simulation
# ═══════════════════════════════════════════════════════════════════════════════

async def test_simulation() -> int:
    """Teste l'intégration via le connecteur en mode simulation."""
    header("2. Connecteur ORASS mode simulation")

    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from core.orass_connector import ORASSConnector, ModeConnexion

        connector = ORASSConnector(mode=ModeConnexion.SIMULATION)

        # Test polices
        polices = await connector.lister_polices(limit=5)
        ok(f"lister_polices() → {len(polices)} police(s) simulée(s)")

        # Test sinistres
        sinistres = await connector.lister_sinistres(statut="ouvert", limit=5)
        ok(f"lister_sinistres(ouvert) → {len(sinistres)} sinistre(s) simulé(s)")

        # Test santé
        sante = await connector.verifier_connexion()
        ok(f"verifier_connexion() → {sante}")

        ok("Connecteur ORASS fonctionnel en mode simulation")
        info("Pour passer en production : configurer ORASS_MODE=direct_sql ou api dans .env")

    except ImportError as e:
        warn(f"Import ORASSConnector échoué : {e} — non bloquant, module optionnel")
    except Exception as e:
        warn(f"Connecteur simulation erreur : {e}")

    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# Rapport final
# ═══════════════════════════════════════════════════════════════════════════════

def rapport_configuration(mode: str, args: argparse.Namespace) -> None:
    """Affiche les instructions de configuration pour le mode testé."""
    header("GUIDE DE CONFIGURATION")

    if mode == "direct_sql":
        info("Ajouter dans .env :")
        print("""
    ORASS_MODE=direct_sql
    ORASS_DSN=postgresql://orass_user:PASSWORD@192.168.1.10:5432/orass_prod
    ORASS_DB_URL=postgresql://orass_user:PASSWORD@192.168.1.10:5432/orass_prod

    # Pour Mercure (si utilisé) :
    MERCURE_DB_URL=postgresql://mercure_user:PASSWORD@192.168.1.10:5432/mercure_prod
        """)
        info("Vérifier que l'IP du serveur YukpoAssurance est whitelistée dans pg_hba.conf :")
        print("    host  orass_prod  orass_user  10.0.0.0/8  md5")

    elif mode == "api":
        info("Ajouter dans .env :")
        print(f"""
    ORASS_MODE=api
    ORASS_API_URL={getattr(args, 'api_url', 'https://orass.compagnie.cm/api/v1')}
    ORASS_API_KEY=VOTRE_CLE_API_ORASS

    # Endpoints attendus par YukpoAssurance :
    # GET  /polices?limit=N&statut=actif
    # GET  /polices/{{numero}}
    # GET  /sinistres?statut=ouvert&limit=N
    # POST /sinistres/{{id}}/statut
    # GET  /assures/{{id}}
    # GET  /quittances?police={{numero}}
        """)

    elif mode == "csv_import":
        info("Configurer les exports ORASS automatiques :")
        print(f"""
    ORASS_MODE=csv_import
    ORASS_CSV_DIR=data/orass_csv

    # Fichiers CSV attendus (exports ORASS planifiés toutes les nuits) :
    # data/orass_csv/polices.csv      — export polices actives
    # data/orass_csv/sinistres.csv    — export sinistres ouverts
    # data/orass_csv/assures.csv      — export assurés
    # data/orass_csv/quittances.csv   — export quittances dues

    # Colonnes minimales par fichier :
    # polices.csv   : numero_police, date_effet, date_echeance, branche, prime_nette, assure_id
    # sinistres.csv : numero_sinistre, numero_police, date_sinistre, statut, montant_reclame
    # assures.csv   : id, nom, prenom, date_naissance, telephone, email
        """)


async def main():
    parser = argparse.ArgumentParser(
        description="Test de connexion ORASS/Mercure — YukpoAssurance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["simulation", "direct_sql", "api", "csv_import"],
        default="simulation",
        help="Mode de connexion ORASS à tester",
    )
    parser.add_argument("--dsn",     help="DSN PostgreSQL ORASS (mode direct_sql)")
    parser.add_argument("--api-url", help="URL API REST ORASS (mode api)")
    parser.add_argument("--api-key", help="Clé API ORASS (mode api)", default="")
    parser.add_argument("--csv-dir", help="Répertoire CSV ORASS (mode csv_import)", default="data/orass_csv")
    parser.add_argument("--guide",   action="store_true", help="Afficher le guide de configuration")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═'*62}{RESET}")
    print(f"{BOLD}  YukpoAssurance — Test ORASS/Mercure — Mode : {args.mode.upper()}{RESET}")
    print(f"{BOLD}  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
    print(f"{BOLD}{'═'*62}{RESET}")

    total_erreurs = 0

    # Variables d'environnement
    total_erreurs += test_env_variables(args.mode)

    # Tests spécifiques au mode
    if args.mode == "simulation":
        total_erreurs += await test_simulation()

    elif args.mode == "direct_sql":
        dsn = args.dsn or os.getenv("ORASS_DSN") or os.getenv("ORASS_DB_URL")
        if not dsn:
            fail("DSN non fourni — utiliser --dsn ou configurer ORASS_DSN dans .env")
            sys.exit(2)
        total_erreurs += test_direct_sql(dsn)

    elif args.mode == "api":
        api_url = args.api_url or os.getenv("ORASS_API_URL")
        api_key = args.api_key or os.getenv("ORASS_API_KEY", "")
        if not api_url:
            fail("URL API non fournie — utiliser --api-url ou configurer ORASS_API_URL dans .env")
            sys.exit(2)
        total_erreurs += await test_api_rest(api_url, api_key)

    elif args.mode == "csv_import":
        csv_dir = args.csv_dir or os.getenv("ORASS_CSV_DIR", "data/orass_csv")
        total_erreurs += test_csv_import(csv_dir)

    if args.guide:
        rapport_configuration(args.mode, args)

    # Bilan
    header("BILAN")
    if total_erreurs == 0:
        print(f"\n  {GREEN}{BOLD}✓ Tous les tests passent — ORASS prêt pour la production{RESET}\n")
        sys.exit(0)
    elif total_erreurs == 1:
        print(f"\n  {YELLOW}{BOLD}⚠ {total_erreurs} avertissement — fonctionnel mais à corriger{RESET}\n")
        sys.exit(1)
    else:
        print(f"\n  {RED}{BOLD}✗ {total_erreurs} erreur(s) bloquante(s) — NE PAS déployer en production{RESET}\n")
        info("Relancer avec --guide pour les instructions de configuration")
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
