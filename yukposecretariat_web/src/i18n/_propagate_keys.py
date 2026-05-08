"""
Propage la structure de fr.json vers toutes les autres langues, en :
- conservant les traductions existantes (deep merge)
- ajoutant les clés manquantes avec la valeur FR comme fallback

Usage : python _propagate_keys.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent
SOURCE = ROOT / "fr.json"
OTHER_LANGS = ["en", "es", "pt", "ar", "de", "zh", "sw", "ha", "ru", "hi", "tr", "wo", "ln", "am"]


def deep_merge_fallback(source: dict, target: dict) -> dict:
    """Pour chaque clé de source : si manquante dans target → on copie source.
    Si présente dans les deux et c'est un dict → récursion. Sinon → on garde target."""
    for k, v in source.items():
        if k not in target:
            target[k] = v
        elif isinstance(v, dict) and isinstance(target[k], dict):
            target[k] = deep_merge_fallback(v, target[k])
        # sinon : on garde la traduction existante
    return target


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))

    for lang in OTHER_LANGS:
        path = ROOT / f"{lang}.json"
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
        else:
            existing = {}
        merged = deep_merge_fallback(source, existing)
        path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  {lang}.json — {len(json.dumps(merged))} chars")

    print(f"OK — {len(OTHER_LANGS)} fichiers mis à jour avec fr.json comme source")


if __name__ == "__main__":
    main()
