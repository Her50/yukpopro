"""Inject `payment.*` translation block into all i18n locale files.

Targets :
  - yukpopro_web/src/i18n/*.json
  - yukpopro_mobile/src/i18n/*.json

Languages with native translations : fr, en, es, pt.
Other languages get the English block (i18next will use it as-is — better than
a missing key crash). They can be refined later by translators.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

WEB_I18N = ROOT / "yukpopro_web" / "src" / "i18n"
MOBILE_I18N = ROOT / "yukpopro_mobile" / "src" / "i18n"

PAYMENT_FR = {
    "enterPhoneTitle": "Numéro de paiement",
    "enterPhoneDesc": "Saisissez le numéro Mobile Money ou international.",
    "choosePaymentTitle": "Choisissez votre opérateur",
    "confirmTitle": "Confirmer le paiement",
    "amount": "Montant",
    "phone": "Téléphone",
    "method": "Méthode",
    "payNow": "Payer maintenant",
    "processingTitle": "Confirmez sur votre téléphone",
    "statusLabel": "Statut",
    "successTitle": "Paiement réussi",
    "successDesc": "Votre abonnement est maintenant actif.",
    "failedTitle": "Paiement non confirmé",
    "failedDesc": "Vous pouvez réessayer ou utiliser un autre moyen.",
    "tryAgain": "Réessayer",
    "errorInit": "Erreur d'initiation",
    "detectingProviders": "Détection des opérateurs disponibles...",
    "noProviders": "Aucun opérateur détecté. Saisissez votre numéro.",
    "showManualFallback": "Aucun opérateur ne fonctionne ? Mode manuel",
    "providers": {
        "mtn_momo": "MTN Mobile Money",
        "orange_money": "Orange Money",
        "campay": "Campay",
        "wave": "Wave",
        "cinetpay": "CinetPay",
        "flutterwave": "Flutterwave",
        "notchpay": "NotchPay",
        "stripe": "Carte bancaire (Stripe)",
        "paypal": "PayPal",
        "legacy_manual": "Validation manuelle",
    },
}

PAYMENT_EN = {
    "enterPhoneTitle": "Payment number",
    "enterPhoneDesc": "Enter your Mobile Money or international number.",
    "choosePaymentTitle": "Choose your provider",
    "confirmTitle": "Confirm payment",
    "amount": "Amount",
    "phone": "Phone",
    "method": "Method",
    "payNow": "Pay now",
    "processingTitle": "Confirm on your phone",
    "statusLabel": "Status",
    "successTitle": "Payment successful",
    "successDesc": "Your subscription is now active.",
    "failedTitle": "Payment not confirmed",
    "failedDesc": "You can try again or use another payment method.",
    "tryAgain": "Try again",
    "errorInit": "Initiation error",
    "detectingProviders": "Detecting available providers...",
    "noProviders": "No provider detected. Please enter your number.",
    "showManualFallback": "No provider works? Manual mode",
    "providers": {
        "mtn_momo": "MTN Mobile Money",
        "orange_money": "Orange Money",
        "campay": "Campay",
        "wave": "Wave",
        "cinetpay": "CinetPay",
        "flutterwave": "Flutterwave",
        "notchpay": "NotchPay",
        "stripe": "Credit card (Stripe)",
        "paypal": "PayPal",
        "legacy_manual": "Manual validation",
    },
}

PAYMENT_ES = {
    "enterPhoneTitle": "Número de pago",
    "enterPhoneDesc": "Introduzca su número Mobile Money o internacional.",
    "choosePaymentTitle": "Elija su operador",
    "confirmTitle": "Confirmar pago",
    "amount": "Importe",
    "phone": "Teléfono",
    "method": "Método",
    "payNow": "Pagar ahora",
    "processingTitle": "Confirme en su teléfono",
    "statusLabel": "Estado",
    "successTitle": "Pago exitoso",
    "successDesc": "Su suscripción está activa.",
    "failedTitle": "Pago no confirmado",
    "failedDesc": "Puede intentarlo de nuevo o usar otro método.",
    "tryAgain": "Intentar de nuevo",
    "errorInit": "Error de inicio",
    "detectingProviders": "Detectando proveedores disponibles...",
    "noProviders": "Ningún proveedor detectado. Introduzca su número.",
    "showManualFallback": "¿Ningún proveedor funciona? Modo manual",
    "providers": PAYMENT_EN["providers"],
}

PAYMENT_PT = {
    "enterPhoneTitle": "Número de pagamento",
    "enterPhoneDesc": "Insira o número Mobile Money ou internacional.",
    "choosePaymentTitle": "Escolha o seu operador",
    "confirmTitle": "Confirmar pagamento",
    "amount": "Valor",
    "phone": "Telefone",
    "method": "Método",
    "payNow": "Pagar agora",
    "processingTitle": "Confirme no seu telefone",
    "statusLabel": "Estado",
    "successTitle": "Pagamento bem-sucedido",
    "successDesc": "A sua subscrição está ativa.",
    "failedTitle": "Pagamento não confirmado",
    "failedDesc": "Pode tentar novamente ou usar outro método.",
    "tryAgain": "Tentar novamente",
    "errorInit": "Erro de iniciação",
    "detectingProviders": "A detetar fornecedores...",
    "noProviders": "Nenhum fornecedor detetado.",
    "showManualFallback": "Nenhum fornecedor funciona? Modo manual",
    "providers": PAYMENT_EN["providers"],
}

LANG_MAP: dict[str, dict] = {
    "fr": PAYMENT_FR,
    "en": PAYMENT_EN,
    "es": PAYMENT_ES,
    "pt": PAYMENT_PT,
    # Autres langues : fallback EN (i18next gère le fallbackLng)
    "de": PAYMENT_EN, "it": PAYMENT_EN, "ar": PAYMENT_EN, "ru": PAYMENT_EN,
    "hi": PAYMENT_EN, "sw": PAYMENT_EN, "ha": PAYMENT_EN, "tr": PAYMENT_EN,
    "am": PAYMENT_EN, "ln": PAYMENT_EN, "wo": PAYMENT_EN, "zh": PAYMENT_EN,
    "ff": PAYMENT_EN, "bm": PAYMENT_EN, "yo": PAYMENT_EN, "ig": PAYMENT_EN,
}


def patch_dir(dirpath: Path) -> int:
    if not dirpath.exists():
        print(f"  ⚠ {dirpath} introuvable — skip")
        return 0
    count = 0
    for json_path in dirpath.glob("*.json"):
        lang = json_path.stem
        block = LANG_MAP.get(lang, PAYMENT_EN)
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  ❌ {json_path.name}: {exc}")
            continue
        data["payment"] = block
        json_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        count += 1
        print(f"  ✓ {json_path.name} ({lang})")
    return count


if __name__ == "__main__":
    print(f"\n→ Web i18n: {WEB_I18N}")
    n_web = patch_dir(WEB_I18N)
    print(f"\n→ Mobile i18n: {MOBILE_I18N}")
    n_mob = patch_dir(MOBILE_I18N)
    print(f"\n✅ Total : {n_web + n_mob} fichiers patchés ({n_web} web, {n_mob} mobile)")
