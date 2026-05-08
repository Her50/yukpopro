"""Outil de diagnostic — extrait les valeurs encore en FR (= identiques à fr.json)
dans chaque langue cible, pour pouvoir les traduire en lot.

Usage : python _extract_fallbacks.py [lang]
        Défaut : produit 5 fichiers _fallbacks_<lang>.json pour en/es/pt/ar/de
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
TARGET_LANGS = ["en", "es", "pt", "ar", "de"]


def flatten(d: dict, prefix: str = "") -> dict:
    out = {}
    for k, v in d.items():
        full = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, full + "."))
        else:
            out[full] = v
    return out


def unflatten(flat: dict) -> dict:
    out: dict = {}
    for k, v in flat.items():
        parts = k.split(".")
        cur = out
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    return out


def main():
    fr = flatten(json.loads((ROOT / "fr.json").read_text(encoding="utf-8")))
    langs = sys.argv[1:] or TARGET_LANGS
    for lang in langs:
        other = flatten(json.loads((ROOT / f"{lang}.json").read_text(encoding="utf-8")))
        fallbacks = {k: fr[k] for k in fr if other.get(k) == fr[k]}
        out_file = ROOT / f"_fallbacks_{lang}.json"
        out_file.write_text(
            json.dumps(unflatten(fallbacks), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  {lang}: {len(fallbacks)} cles ecrites dans {out_file.name}")


if __name__ == "__main__":
    main()
