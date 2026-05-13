/**
 * Bouton + modale "Publier landing" partagé YukpoPro + YukpoSecrétariat.
 *
 * Affiché à la fin du message succès dans le chat. Demande slug
 * (sous-domaine *.yukpomnang.com) + plan, POST publier, affiche URL
 * partageable + QR PNG téléchargeable.
 */
import { useState } from "react";
import { Check, Copy, Globe, Loader2, QrCode, Send } from "lucide-react";

export interface PublierLandingButtonProps {
  /** ID du fichier HTML retourné par /pro/landing-page/generer. */
  fichierId: string;
  /** Fonction qui POST /pro/landing-page/publier — injectée par l'app. */
  publier: (req: {
    fichier_id: string; slug: string;
    plan?: "free" | "pro" | "business";
    footer_custom?: string;
  }) => Promise<{
    ok: boolean; site_id: string; slug: string;
    url_public: string; qr_png_b64: string;
    plan: string; is_new: boolean;
  }>;
  /** Plan actuel de l'utilisateur (récupéré côté app hôte). */
  plan?: "free" | "pro" | "business";
  /** Traduction t(key, fallback). */
  t?: (key: string, fallback?: string) => string;
  /** Style compact (boutonn'l) ou plein (panneau). */
  variant?: "inline" | "full";
}

const _tf = (_k: string, fb?: string) => fb || _k;

export const PublierLandingButton = ({
  fichierId, publier, plan = "free", t = _tf, variant = "inline",
}: PublierLandingButtonProps) => {
  const [open, setOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const [footerCustom, setFooterCustom] = useState("");
  const [loading, setLoading] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [result, setResult] = useState<Awaited<ReturnType<typeof publier>> | null>(null);
  const [copied, setCopied] = useState(false);

  const slugNormalise = slug.toLowerCase().replace(/[^a-z0-9-]/g, "-").replace(/^-+|-+$/g, "");
  const slugValide = /^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$/.test(slugNormalise);

  const onPublier = async () => {
    setErreur(null);
    if (!slugValide) {
      setErreur(t("landing.publier.erreur_slug",
                  "Slug invalide : 3-40 caractères, a-z 0-9 -"));
      return;
    }
    setLoading(true);
    try {
      const res = await publier({
        fichier_id: fichierId,
        slug: slugNormalise,
        plan,
        footer_custom: footerCustom.trim() || undefined,
      });
      setResult(res);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || "Erreur inconnue";
      setErreur(String(detail).slice(0, 200));
    } finally {
      setLoading(false);
    }
  };

  const copierUrl = () => {
    if (!result?.url_public) return;
    navigator.clipboard?.writeText(result.url_public).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => { /* ignore */ });
  };

  if (!open && !result) {
    return (
      <button
        onClick={() => setOpen(true)}
        className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg
                    bg-violet-600 hover:bg-violet-700 text-white text-sm
                    font-medium shadow-md min-h-[44px]
                    ${variant === "full" ? "w-full justify-center" : ""}`}
      >
        <Send className="w-4 h-4" />
        {t("landing.publier.bouton", "Publier en ligne")}
      </button>
    );
  }

  if (result) {
    return (
      <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 max-w-md">
        <div className="flex items-center gap-2 mb-3">
          <Check className="w-5 h-5 text-emerald-700" />
          <h3 className="font-semibold text-emerald-900">
            {t("landing.publier.succes", "Landing publiée !")}
          </h3>
        </div>
        <div className="bg-white rounded-lg p-3 flex items-center justify-between gap-2 mb-3 border border-emerald-100">
          <a
            href={result.url_public} target="_blank" rel="noopener"
            className="text-violet-700 hover:underline text-sm font-medium truncate flex-grow"
          >
            <Globe className="w-4 h-4 inline mr-1 opacity-60" />
            {result.url_public}
          </a>
          <button
            onClick={copierUrl}
            className="text-xs px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 inline-flex items-center gap-1 min-h-[36px]"
          >
            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            {copied ? t("landing.publier.copie", "Copié") : t("landing.publier.copier", "Copier")}
          </button>
        </div>
        {result.qr_png_b64 && (
          <details className="mt-2">
            <summary className="text-sm cursor-pointer text-slate-700 inline-flex items-center gap-1">
              <QrCode className="w-4 h-4" />
              {t("landing.publier.voir_qr", "Voir le QR code")}
            </summary>
            <div className="mt-2 bg-white p-3 rounded-lg border border-emerald-100 text-center">
              <img
                src={result.qr_png_b64} alt="QR code"
                className="mx-auto w-40 h-40 object-contain"
              />
              <a
                href={result.qr_png_b64} download={`qr-${result.slug}.png`}
                className="inline-block mt-2 text-xs text-violet-700 hover:underline"
              >
                {t("landing.publier.telecharger_qr", "Télécharger le QR")}
              </a>
            </div>
          </details>
        )}
        <p className="text-xs text-slate-600 mt-3">
          {t("landing.publier.suite",
             "Les leads capturés apparaîtront dans")} {" "}
          <a href="/mes-leads" className="text-violet-700 hover:underline font-medium">
            {t("landing.publier.mes_leads", "Mes Leads")}
          </a>.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 max-w-md shadow-sm">
      <h3 className="font-semibold mb-3 text-slate-900">
        {t("landing.publier.titre_modale", "Publier la landing")}
      </h3>
      <label className="block text-sm font-medium text-slate-700 mb-1">
        {t("landing.publier.slug_label", "Sous-domaine souhaité")}
      </label>
      <div className="flex items-center bg-slate-50 rounded-lg border border-slate-300 mb-1">
        <input
          type="text" value={slug}
          onChange={e => setSlug(e.target.value)}
          placeholder="ma-boutique-douala"
          className="flex-grow px-3 py-2 bg-transparent text-sm outline-none min-h-[44px]"
          autoFocus
        />
        <span className="px-3 text-sm text-slate-500 whitespace-nowrap">
          .yukpomnang.com
        </span>
      </div>
      <p className="text-xs text-slate-500 mb-3">
        {t("landing.publier.slug_hint",
           "Lettres, chiffres, tirets (3-40 caractères)")}
      </p>

      {(plan === "pro" || plan === "business") && (
        <>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            {t("landing.publier.footer_label", "Footer perso (optionnel)")}
          </label>
          <textarea
            value={footerCustom}
            onChange={e => setFooterCustom(e.target.value)}
            placeholder={t("landing.publier.footer_placeholder",
                           "Mentions légales, copyright, etc.")}
            className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm mb-3"
            rows={2} maxLength={500}
          />
        </>
      )}

      {erreur && (
        <div className="bg-rose-50 border border-rose-200 text-rose-900 rounded-lg p-2 mb-3 text-xs">
          {erreur}
        </div>
      )}

      <div className="flex items-center gap-2">
        <button
          onClick={onPublier} disabled={loading || !slugValide}
          className="flex-grow inline-flex items-center justify-center gap-2
                     px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700
                     disabled:opacity-50 disabled:cursor-not-allowed
                     text-white text-sm font-medium shadow-md min-h-[44px]"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          {loading
            ? t("landing.publier.en_cours", "Déploiement Netlify…")
            : t("landing.publier.confirmer", "Publier maintenant")}
        </button>
        <button
          onClick={() => setOpen(false)}
          className="px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm min-h-[44px]"
        >
          {t("landing.publier.annuler", "Annuler")}
        </button>
      </div>
    </div>
  );
};
