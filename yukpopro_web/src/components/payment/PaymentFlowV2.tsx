/**
 * PaymentFlowV2 — Flow de paiement complet utilisant l'API v2.
 *
 * États : phone → provider → confirm → polling → success/error
 * Réutilisable pour abonnement, recharge, ou tout autre paiement YukpoPro.
 *
 * Responsive PWA-ready, i18n complet via t("payment.*").
 */
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Smartphone, Copy, Check, ArrowRight, Loader2,
  CheckCircle, XCircle, ExternalLink, AlertCircle, CreditCard,
} from "lucide-react";
import toast from "react-hot-toast";
import { Button } from "@/components/ui";
import {
  paiementV2Api,
  type ProviderName,
  type PaymentMethod,
  type PaymentInitiateResponse,
} from "@/api/client";
import { PaymentMethodSelector } from "./PaymentMethodSelector";

type Props = {
  type: "abonnement" | "recharge" | "service";
  planOuPack?: string;
  amount: number;
  currency?: string;
  countryCode?: string;
  defaultPhone?: string;
  customerEmail?: string;
  customerName?: string;
  metadata?: Record<string, unknown>;
  onSuccess?: (reference: string) => void;
  onCancel?: () => void;
};

type Step = "method" | "phone" | "provider" | "confirm" | "processing" | "done";
type MethodChoice = "mobile_money" | "card";

const TERMINAL_STATUSES = new Set(["success", "failed", "cancelled", "refunded", "expired"]);

export const PaymentFlowV2 = ({
  type, planOuPack, amount, currency = "XAF", countryCode,
  defaultPhone = "", customerEmail, customerName, metadata,
  onSuccess, onCancel,
}: Props) => {
  const { t } = useTranslation();
  const [step, setStep] = useState<Step>("method");
  const [methodChoice, setMethodChoice] = useState<MethodChoice | undefined>();
  const [phone, setPhone] = useState(defaultPhone);
  const [provider, setProvider] = useState<ProviderName | undefined>();
  const [response, setResponse] = useState<PaymentInitiateResponse | null>(null);
  const [pollStatus, setPollStatus] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const pollTimer = useRef<number | undefined>();

  const inferredMethod = (p: ProviderName | undefined): PaymentMethod => {
    if (p === "stripe" || p === "paypal") return p === "paypal" ? "paypal" : "card";
    return "mobile_money";
  };

  const handleInitiate = async () => {
    if (!provider) return;
    setLoading(true);
    try {
      const res = await paiementV2Api.initier({
        type, plan_ou_pack: planOuPack, amount, currency,
        customer_phone: phone,
        customer_email: customerEmail,
        customer_name: customerName,
        country_code: countryCode,
        method: inferredMethod(provider),
        preferred_provider: provider,
        return_url: `${window.location.origin}/abonnement?status=success`,
        cancel_url: `${window.location.origin}/abonnement?status=cancelled`,
        metadata,
      });
      setResponse(res);
      if (res.payment_url) {
        // Redirection externe (Stripe Checkout, PayPal, CinetPay, Flutterwave...)
        window.location.href = res.payment_url;
        return;
      }
      setStep("processing");
      startPolling(res.reference);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || t("payment.errorInit", "Erreur d'initiation"));
    } finally {
      setLoading(false);
    }
  };

  const startPolling = (ref: string) => {
    let attempts = 0;
    const tick = async () => {
      attempts += 1;
      try {
        const data = await paiementV2Api.statut(ref);
        setPollStatus(data.status);
        if (TERMINAL_STATUSES.has(data.status)) {
          setStep("done");
          if (data.status === "success" && onSuccess) onSuccess(ref);
          return;
        }
      } catch {
        // ignore, continue polling
      }
      if (attempts < 60) {
        pollTimer.current = window.setTimeout(tick, 5000);
      } else {
        setStep("done");
        setPollStatus("expired");
      }
    };
    tick();
  };

  useEffect(() => () => { if (pollTimer.current) window.clearTimeout(pollTimer.current); }, []);

  const copyRef = () => {
    if (!response?.reference) return;
    navigator.clipboard.writeText(response.reference);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  // ─── Step 0 : Méthode (Mobile Money vs Carte Bancaire) ───
  if (step === "method") {
    const choose = (m: MethodChoice) => {
      setMethodChoice(m);
      setProvider(undefined);
      if (m === "card") setStep("provider");
      else setStep("phone");
    };
    return (
      <div className="space-y-4">
        <h3 className="text-lg font-semibold">
          {t("payment.chooseMethodTitle", "Comment souhaitez-vous payer ?")}
        </h3>
        <p className="text-sm text-gray-600">
          {t("payment.chooseMethodDesc", "Sélectionnez votre mode de paiement.")}
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => choose("mobile_money")}
            className={[
              "flex items-center gap-3 p-4 rounded-xl border-2 transition text-left",
              "hover:shadow-md hover:border-indigo-400",
              methodChoice === "mobile_money" ? "border-indigo-600 ring-2 ring-indigo-200" : "border-gray-200",
            ].join(" ")}
          >
            <span className="w-12 h-12 rounded-full flex items-center justify-center bg-emerald-500 text-white shrink-0">
              <Smartphone className="w-6 h-6" />
            </span>
            <span>
              <span className="block font-semibold">
                {t("payment.methodMobileMoney", "Mobile Money")}
              </span>
              <span className="block text-xs text-gray-500">
                {t("payment.methodMobileMoneyDesc", "MTN MoMo, Orange Money, Wave…")}
              </span>
            </span>
          </button>
          <button
            type="button"
            onClick={() => choose("card")}
            className={[
              "flex items-center gap-3 p-4 rounded-xl border-2 transition text-left",
              "hover:shadow-md hover:border-indigo-400",
              methodChoice === "card" ? "border-indigo-600 ring-2 ring-indigo-200" : "border-gray-200",
            ].join(" ")}
          >
            <span className="w-12 h-12 rounded-full flex items-center justify-center bg-violet-600 text-white shrink-0">
              <CreditCard className="w-6 h-6" />
            </span>
            <span>
              <span className="block font-semibold">
                {t("payment.methodCard", "Carte bancaire")}
              </span>
              <span className="block text-xs text-gray-500">
                {t("payment.methodCardDesc", "Visa, Mastercard, PayPal")}
              </span>
            </span>
          </button>
        </div>
        {onCancel && (
          <div className="flex justify-end pt-2">
            <Button variant="ghost" onClick={onCancel}>{t("common.cancel", "Annuler")}</Button>
          </div>
        )}
      </div>
    );
  }

  // ─── Step 1 : Téléphone ───
  if (step === "phone") {
    return (
      <div className="space-y-4">
        <h3 className="text-lg font-semibold">{t("payment.enterPhoneTitle", "Numéro de paiement")}</h3>
        <p className="text-sm text-gray-600">
          {t("payment.enterPhoneDesc", "Saisissez le numéro Mobile Money ou international.")}
        </p>
        <div className="flex gap-2">
          <input
            type="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+237 670 00 00 00"
            className="flex-1 px-4 py-3 border-2 rounded-xl text-lg"
            autoFocus
          />
        </div>
        <div className="flex gap-2 justify-end pt-2">
          <Button variant="ghost" onClick={() => setStep("method")}>
            {t("common.back", "Retour")}
          </Button>
          <Button
            disabled={!phone || phone.length < 8}
            onClick={() => setStep("provider")}
          >
            {t("common.next", "Suivant")} <ArrowRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </div>
    );
  }

  // ─── Step 2 : Provider ───
  if (step === "provider") {
    const title = methodChoice === "card"
      ? t("payment.chooseCardTitle", "Choisissez votre processeur")
      : t("payment.choosePaymentTitle", "Choisissez votre opérateur");
    return (
      <div className="space-y-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        <PaymentMethodSelector
          customerPhone={phone}
          countryCode={countryCode}
          selected={provider}
          onSelect={setProvider}
          methodFilter={methodChoice}
        />
        <div className="flex gap-2 justify-end pt-2">
          <Button
            variant="ghost"
            onClick={() => setStep(methodChoice === "card" ? "method" : "phone")}
          >
            {t("common.back", "Retour")}
          </Button>
          <Button
            disabled={!provider}
            onClick={() => setStep(methodChoice === "card" ? "confirm" : "confirm")}
          >
            {t("common.next", "Suivant")} <ArrowRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      </div>
    );
  }

  // ─── Step 3 : Confirmation ───
  if (step === "confirm") {
    return (
      <div className="space-y-4">
        <h3 className="text-lg font-semibold">{t("payment.confirmTitle", "Confirmer le paiement")}</h3>
        <div className="bg-gray-50 dark:bg-gray-800 p-4 rounded-xl space-y-2 text-sm">
          <div className="flex justify-between"><span>{t("payment.amount", "Montant")}</span><strong>{amount.toLocaleString()} {currency}</strong></div>
          {methodChoice !== "card" && (
            <div className="flex justify-between"><span>{t("payment.phone", "Téléphone")}</span><strong>{phone}</strong></div>
          )}
          <div className="flex justify-between"><span>{t("payment.method", "Méthode")}</span><strong>{provider}</strong></div>
        </div>
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={() => setStep("provider")}>{t("common.back", "Retour")}</Button>
          <Button onClick={handleInitiate} disabled={loading}>
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : t("payment.payNow", "Payer maintenant")}
          </Button>
        </div>
      </div>
    );
  }

  // ─── Step 4 : Processing (USSD push, attente confirmation) ───
  if (step === "processing") {
    return (
      <div className="text-center space-y-4 py-6">
        <Loader2 className="w-12 h-12 animate-spin mx-auto text-indigo-600" />
        <h3 className="text-lg font-semibold">{t("payment.processingTitle", "Confirmez sur votre téléphone")}</h3>
        {response?.ussd_instructions && (
          <p className="text-sm text-gray-700 max-w-md mx-auto bg-yellow-50 border border-yellow-200 rounded-lg p-3">
            <Smartphone className="inline w-4 h-4 mr-1" />
            {response.ussd_instructions}
          </p>
        )}
        {response?.reference && (
          <div className="inline-flex items-center gap-2 bg-gray-100 px-3 py-2 rounded-lg text-sm">
            <span className="font-mono">{response.reference}</span>
            <button onClick={copyRef} className="text-indigo-600 hover:text-indigo-800">
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
        )}
        <p className="text-xs text-gray-500">
          {t("payment.statusLabel", "Statut")} : <strong>{pollStatus || "pending"}</strong>
        </p>
      </div>
    );
  }

  // ─── Step 5 : Done ───
  const success = pollStatus === "success";
  return (
    <div className="text-center space-y-4 py-6">
      {success ? (
        <CheckCircle className="w-16 h-16 mx-auto text-emerald-500" />
      ) : (
        <XCircle className="w-16 h-16 mx-auto text-red-500" />
      )}
      <h3 className="text-xl font-semibold">
        {success
          ? t("payment.successTitle", "Paiement réussi 🎉")
          : t("payment.failedTitle", "Paiement non confirmé")}
      </h3>
      <p className="text-sm text-gray-600 max-w-md mx-auto">
        {success
          ? t("payment.successDesc", "Votre abonnement est maintenant actif.")
          : t("payment.failedDesc", "Vous pouvez réessayer ou utiliser un autre moyen de paiement.")}
      </p>
      {response?.reference && (
        <p className="text-xs font-mono text-gray-500">{response.reference}</p>
      )}
      {!success && response?.error_message && (
        <p className="text-sm text-red-600 flex items-center justify-center gap-1">
          <AlertCircle className="w-4 h-4" /> {response.error_message}
        </p>
      )}
      <div className="flex gap-2 justify-center pt-2">
        {!success && (
          <Button onClick={() => { setStep("method"); setResponse(null); setPollStatus(""); }}>
            {t("payment.tryAgain", "Réessayer")}
          </Button>
        )}
        {success && onSuccess && (
          <Button onClick={() => onSuccess(response?.reference || "")}>
            {t("common.continue", "Continuer")}
          </Button>
        )}
      </div>
    </div>
  );
};
