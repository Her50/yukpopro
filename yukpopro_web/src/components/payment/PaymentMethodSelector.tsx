/**
 * PaymentMethodSelector
 * ---------------------
 * Composant réutilisable (web + adaptable mobile) qui :
 *   1. Détecte automatiquement les providers disponibles pour le numéro/pays
 *   2. Affiche MTN MoMo + Orange Money en priorité (si CM/CI/etc.)
 *   3. Propose Stripe/PayPal pour cartes internationales
 *   4. Tombe sur le mode manuel si aucun provider API n'est dispo
 *
 * Responsive : mobile-first (grid-cols-2 → md:grid-cols-3).
 * i18n : toutes les chaînes via t("payment.*").
 */
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Smartphone, CreditCard, Wallet, Building2, Loader2 } from "lucide-react";
import { paiementV2Api, type ProviderName } from "@/api/client";

type Props = {
  customerPhone: string;
  countryCode?: string;
  onSelect: (provider: ProviderName) => void;
  selected?: ProviderName;
  disabled?: boolean;
};

const PROVIDER_META: Record<ProviderName, {
  icon: typeof Smartphone;
  brandColor: string;
  i18nKey: string;
}> = {
  mtn_momo:     { icon: Smartphone, brandColor: "bg-yellow-400 text-black",      i18nKey: "payment.providers.mtn_momo" },
  orange_money: { icon: Smartphone, brandColor: "bg-orange-500 text-white",       i18nKey: "payment.providers.orange_money" },
  campay:       { icon: Smartphone, brandColor: "bg-emerald-500 text-white",      i18nKey: "payment.providers.campay" },
  wave:         { icon: Smartphone, brandColor: "bg-blue-500 text-white",         i18nKey: "payment.providers.wave" },
  cinetpay:     { icon: Wallet,     brandColor: "bg-indigo-600 text-white",       i18nKey: "payment.providers.cinetpay" },
  flutterwave:  { icon: Wallet,     brandColor: "bg-amber-600 text-white",        i18nKey: "payment.providers.flutterwave" },
  notchpay:     { icon: Wallet,     brandColor: "bg-purple-600 text-white",       i18nKey: "payment.providers.notchpay" },
  stripe:       { icon: CreditCard, brandColor: "bg-violet-600 text-white",       i18nKey: "payment.providers.stripe" },
  paypal:       { icon: CreditCard, brandColor: "bg-blue-700 text-white",         i18nKey: "payment.providers.paypal" },
  legacy_manual:{ icon: Building2,  brandColor: "bg-gray-600 text-white",         i18nKey: "payment.providers.legacy_manual" },
};

export const PaymentMethodSelector = ({
  customerPhone,
  countryCode,
  onSelect,
  selected,
  disabled,
}: Props) => {
  const { t } = useTranslation();
  const [providers, setProviders] = useState<ProviderName[]>([]);
  const [loading, setLoading] = useState(false);
  const [showManual, setShowManual] = useState(false);

  useEffect(() => {
    if (!customerPhone || customerPhone.length < 6) {
      setProviders([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    paiementV2Api
      .providersDispo(customerPhone, countryCode)
      .then((res) => {
        if (cancelled) return;
        setProviders(res.providers);
      })
      .catch(() => {
        if (cancelled) return;
        setProviders([]);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [customerPhone, countryCode]);

  const visible = useMemo(
    () => (showManual ? [...providers, "legacy_manual" as ProviderName] : providers),
    [providers, showManual],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8 text-gray-500">
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        {t("payment.detectingProviders", "Détection des opérateurs disponibles...")}
      </div>
    );
  }

  if (visible.length === 0) {
    return (
      <div className="text-center py-6 text-gray-500">
        {t("payment.noProviders", "Aucun opérateur détecté. Saisissez votre numéro.")}
      </div>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {visible.map((p) => {
          const meta = PROVIDER_META[p];
          const Icon = meta.icon;
          const isSel = selected === p;
          return (
            <button
              key={p}
              type="button"
              disabled={disabled}
              onClick={() => onSelect(p)}
              className={[
                "flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition",
                "hover:shadow-md disabled:opacity-50 disabled:cursor-not-allowed",
                isSel ? "border-indigo-600 ring-2 ring-indigo-200" : "border-gray-200",
              ].join(" ")}
            >
              <span className={`w-10 h-10 rounded-full flex items-center justify-center ${meta.brandColor}`}>
                <Icon className="w-5 h-5" />
              </span>
              <span className="text-xs font-medium text-center leading-tight">
                {t(meta.i18nKey, p)}
              </span>
            </button>
          );
        })}
      </div>

      {!showManual && (
        <button
          type="button"
          onClick={() => setShowManual(true)}
          className="mt-3 text-xs text-gray-500 hover:text-gray-700 underline"
        >
          {t("payment.showManualFallback", "Aucun opérateur ne fonctionne ? Mode manuel")}
        </button>
      )}
    </div>
  );
};
