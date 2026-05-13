/**
 * TrackingSettingsPanel — Onglet "Tracking & Email automation" partagé
 * YukpoPro + YukpoSecrétariat.
 *
 * 3 sections :
 *   1. Pixels (FB / GA4 / TikTok / Snap / Clarity) + Plausible toggle
 *   2. Newsletter (Brevo / Mailchimp) — provider + API key + list_id
 *   3. Auto-reply J+0 / J+3 / J+7 — templates email modifiables
 */
import { useEffect, useState } from "react";
import {
  Activity, BarChart3, BellRing, Check, Loader2, Mail,
  Save, Settings as SettingsIcon, Trash2,
} from "lucide-react";

export interface TrackingSettingsPanelProps {
  http: {
    get:  (url: string, config?: any) => Promise<any>;
    put:  (url: string, data?: any, config?: any) => Promise<any>;
  };
  t?: (key: string, fallback?: string) => string;
}

interface TrackingSettings {
  plausible_actif: boolean;
  fb_pixel_id?: string | null;
  ga4_measurement_id?: string | null;
  tiktok_pixel_id?: string | null;
  snap_pixel_id?: string | null;
  clarity_project_id?: string | null;
  newsletter_provider?: string | null;
  newsletter_list_id?: string | null;
  newsletter_api_key_set?: boolean;
}

interface FollowupSettings {
  j0: { actif: boolean; sujet: string | null; corps: string | null };
  j3: { actif: boolean; sujet: string | null; corps: string | null };
  j7: { actif: boolean; sujet: string | null; corps: string | null };
}

const _tf = (_k: string, fb?: string) => fb || _k;

export const TrackingSettingsPanel = ({ http, t = _tf }: TrackingSettingsPanelProps) => {
  const [tracking, setTracking] = useState<TrackingSettings>({ plausible_actif: true });
  const [followup, setFollowup] = useState<FollowupSettings>({
    j0: { actif: false, sujet: "", corps: "" },
    j3: { actif: false, sujet: "", corps: "" },
    j7: { actif: false, sujet: "", corps: "" },
  });
  const [newApiKey, setNewApiKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedTick, setSavedTick] = useState(0);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      http.get("/pro/tracking-settings").then(r => r.data),
      http.get("/pro/landing-followup-settings").then(r => r.data),
    ])
      .then(([tr, fu]) => {
        setTracking({
          plausible_actif: tr.plausible_actif ?? true,
          fb_pixel_id: tr.fb_pixel_id || "",
          ga4_measurement_id: tr.ga4_measurement_id || "",
          tiktok_pixel_id: tr.tiktok_pixel_id || "",
          snap_pixel_id: tr.snap_pixel_id || "",
          clarity_project_id: tr.clarity_project_id || "",
          newsletter_provider: tr.newsletter_provider || "",
          newsletter_list_id: tr.newsletter_list_id || "",
          newsletter_api_key_set: !!tr.newsletter_api_key_set,
        });
        setFollowup(fu);
      })
      .catch((e: any) => setErreur(e?.response?.data?.detail || e?.message))
      .finally(() => setLoading(false));
  }, [http]);

  const sauver = async () => {
    setSaving(true); setErreur(null);
    try {
      const trackingPayload: any = { ...tracking };
      // API key : si l'utilisateur a tapé une nouvelle valeur, envoyer
      if (newApiKey.trim()) trackingPayload.newsletter_api_key = newApiKey.trim();
      // Sinon ne pas l'écraser → ne pas envoyer le champ
      delete trackingPayload.newsletter_api_key_set;
      await http.put("/pro/tracking-settings", trackingPayload);
      await http.put("/pro/landing-followup-settings", followup);
      setSavedTick(t => t + 1);
      setNewApiKey("");
      setTracking(prev => ({
        ...prev,
        newsletter_api_key_set: !!(newApiKey.trim() || prev.newsletter_api_key_set),
      }));
    } catch (e: any) {
      setErreur(e?.response?.data?.detail || e?.message || "Erreur");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="w-6 h-6 animate-spin text-violet-600" />
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <SettingsIcon className="w-6 h-6 text-violet-600" />
        <h1 className="text-2xl md:text-3xl font-bold">
          {t("tracking.titre", "Tracking & Email automation")}
        </h1>
      </div>

      {/* Pixels + Plausible */}
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-violet-600" />
          {t("tracking.section_pixels", "Analytics & Pixels publicitaires")}
        </h2>
        <p className="text-xs text-slate-600 mb-4">
          {t("tracking.aide_pixels",
             "Ces IDs sont injectés dans le <head> de toutes vos landings publiées.")}
        </p>

        <label className="flex items-center gap-2 text-sm mb-4">
          <input
            type="checkbox" checked={tracking.plausible_actif}
            onChange={e => setTracking({ ...tracking, plausible_actif: e.target.checked })}
            className="w-4 h-4"
          />
          {t("tracking.plausible", "Activer Plausible Analytics (gratuit, RGPD)")}
        </label>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Champ
            label="Facebook / Meta Pixel ID"
            placeholder="1234567890123"
            value={tracking.fb_pixel_id || ""}
            onChange={v => setTracking({ ...tracking, fb_pixel_id: v })}
          />
          <Champ
            label="Google Analytics 4 (G-XXXXXXX)"
            placeholder="G-XXXXXXX"
            value={tracking.ga4_measurement_id || ""}
            onChange={v => setTracking({ ...tracking, ga4_measurement_id: v })}
          />
          <Champ
            label="TikTok Pixel ID"
            placeholder="CXXXXXXXXXXXXXX"
            value={tracking.tiktok_pixel_id || ""}
            onChange={v => setTracking({ ...tracking, tiktok_pixel_id: v })}
          />
          <Champ
            label="Snap Pixel ID"
            placeholder="00000000-0000-0000-0000-000000000000"
            value={tracking.snap_pixel_id || ""}
            onChange={v => setTracking({ ...tracking, snap_pixel_id: v })}
          />
          <Champ
            label="Microsoft Clarity Project ID"
            placeholder="ab12cd34ef"
            value={tracking.clarity_project_id || ""}
            onChange={v => setTracking({ ...tracking, clarity_project_id: v })}
          />
        </div>
      </section>

      {/* Newsletter */}
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          <Mail className="w-5 h-5 text-violet-600" />
          {t("tracking.section_newsletter", "Inscription newsletter")}
        </h2>
        <p className="text-xs text-slate-600 mb-4">
          {t("tracking.aide_newsletter",
             "Si configuré, vos landings affichent un champ d'inscription "
             + "qui pousse les emails vers votre Brevo / Mailchimp.")}
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Select
            label="Provider"
            value={tracking.newsletter_provider || ""}
            options={[
              { value: "", label: "— Désactivé —" },
              { value: "brevo", label: "Brevo (ex-Sendinblue)" },
              { value: "mailchimp", label: "Mailchimp" },
            ]}
            onChange={v => setTracking({ ...tracking, newsletter_provider: v })}
          />
          <Champ
            label="List ID"
            placeholder={tracking.newsletter_provider === "mailchimp"
                         ? "abc123def" : "12"}
            value={tracking.newsletter_list_id || ""}
            onChange={v => setTracking({ ...tracking, newsletter_list_id: v })}
          />
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              API Key
              {tracking.newsletter_api_key_set && (
                <span className="text-xs ml-2 text-emerald-700">
                  <Check className="w-3 h-3 inline" /> configurée
                </span>
              )}
            </label>
            <input
              type="password"
              value={newApiKey} onChange={e => setNewApiKey(e.target.value)}
              placeholder={tracking.newsletter_api_key_set
                           ? "•••••••• (laisser vide pour conserver)"
                           : "Coller la clé API"}
              className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm
                         min-h-[44px]"
            />
          </div>
        </div>
      </section>

      {/* Follow-up J+0/J+3/J+7 */}
      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="font-semibold mb-3 flex items-center gap-2">
          <BellRing className="w-5 h-5 text-violet-600" />
          {t("tracking.section_followup", "Auto-replies & relances email")}
        </h2>
        <p className="text-xs text-slate-600 mb-4">
          {t("tracking.aide_followup",
             "Variables disponibles : {nom}, {email}, {message}, {slug}.")}
        </p>
        {(["j0", "j3", "j7"] as const).map(j => (
          <FollowupBlock
            key={j} jour={j} val={followup[j]}
            t={t}
            onChange={f => setFollowup({ ...followup, [j]: f })}
          />
        ))}
      </section>

      {erreur && (
        <div className="bg-rose-50 border border-rose-200 text-rose-900 rounded-lg p-3 text-sm">
          {erreur}
        </div>
      )}

      <div className="flex items-center justify-end gap-3 sticky bottom-2 bg-slate-50/80 backdrop-blur-md rounded-xl p-3 border border-slate-200">
        {savedTick > 0 && (
          <span className="text-sm text-emerald-700 inline-flex items-center gap-1">
            <Check className="w-4 h-4" /> {t("tracking.sauve", "Enregistré")}
          </span>
        )}
        <button
          onClick={sauver} disabled={saving}
          className="inline-flex items-center gap-2 px-5 py-2 rounded-lg
                     bg-violet-600 hover:bg-violet-700 text-white text-sm
                     font-medium shadow disabled:opacity-50 min-h-[44px]"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {t("tracking.sauver", "Sauvegarder")}
        </button>
      </div>
    </div>
  );
};

const Champ = ({ label, value, onChange, placeholder }: {
  label: string; value: string;
  onChange: (v: string) => void; placeholder?: string;
}) => (
  <div>
    <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
    <input
      type="text" value={value} onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm
                 min-h-[44px]"
    />
  </div>
);

const Select = ({ label, value, options, onChange }: {
  label: string; value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) => (
  <div>
    <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
    <select
      value={value} onChange={e => onChange(e.target.value)}
      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm
                 min-h-[44px]"
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </div>
);

const FollowupBlock = ({ jour, val, t, onChange }: {
  jour: "j0" | "j3" | "j7";
  val: { actif: boolean; sujet: string | null; corps: string | null };
  t: (k: string, fb?: string) => string;
  onChange: (v: typeof val) => void;
}) => {
  const labels: Record<typeof jour, { titre: string; aide: string }> = {
    j0: {
      titre: t("tracking.j0_titre", "J+0 — Auto-reply visiteur"),
      aide: t("tracking.j0_aide", "Envoyé dès qu'un lead est capturé."),
    },
    j3: {
      titre: t("tracking.j3_titre", "J+3 — Relance lead non lu"),
      aide: t("tracking.j3_aide", "Envoyé si le marchand n'a pas traité le lead."),
    },
    j7: {
      titre: t("tracking.j7_titre", "J+7 — Dernière relance"),
      aide: t("tracking.j7_aide", "Envoyé si le lead reste non contacté."),
    },
  };
  return (
    <div className="border border-slate-200 rounded-lg p-3 mb-3">
      <label className="flex items-center gap-2 text-sm font-medium mb-1">
        <input
          type="checkbox" checked={val.actif}
          onChange={e => onChange({ ...val, actif: e.target.checked })}
          className="w-4 h-4"
        />
        {labels[jour].titre}
      </label>
      <p className="text-xs text-slate-500 mb-2">{labels[jour].aide}</p>
      {val.actif && (
        <>
          <input
            type="text" placeholder="Sujet de l'email"
            value={val.sujet || ""}
            onChange={e => onChange({ ...val, sujet: e.target.value })}
            className="w-full px-3 py-2 mb-2 rounded-lg border border-slate-300 text-sm
                       min-h-[44px]"
          />
          <textarea
            placeholder="Corps de l'email (variables : {nom}, {email}, {message}, {slug})"
            value={val.corps || ""}
            onChange={e => onChange({ ...val, corps: e.target.value })}
            rows={4}
            className="w-full px-3 py-2 rounded-lg border border-slate-300 text-sm"
          />
        </>
      )}
    </div>
  );
};
