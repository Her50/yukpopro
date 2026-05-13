/**
 * CostConfirmModal — Modale globale de confirmation préventive des coûts crédits.
 *
 * Architecture :
 *   • Store Zustand `useCostConfirmStore` (singleton inter-app)
 *   • Composant racine `<CostConfirmModalRoot />` à monter UNE FOIS dans
 *     l'arbre React de chaque app hôte (App.tsx ou Layout.tsx).
 *   • Helper `installCostInterceptor(http)` à appeler une fois sur l'axios
 *     instance : capte les 402 type="cost_confirm_required" et déclenche
 *     la modale, puis re-joue la requête avec confirmer_cout=true si OK.
 *
 * Le composant est dimensionnellement responsive (mobile-first) et touch-
 * friendly. Compatible YukpoPro + YukpoSecrétariat (même API).
 */
import { useState } from "react";
import { create } from "zustand";
import { AlertTriangle, CreditCard, Loader2, X } from "lucide-react";

// ── Types backend (cf. core/cost_advisor.py AdvisorVerdict) ───────────────────
export interface CostVerdict {
  type: "cost_confirm_required" | "credits_insuffisants";
  plan: string;
  cout_credits_estime: number;
  cout_fcfa_estime: number;
  solde_credits_avant: number;
  solde_credits_apres_estime: number;
  quota_total: number;
  pct_solde_consomme: number;
  seuil_pct_plan: number;
  module: string;
  message_user: string;
}

// ── Store global ──────────────────────────────────────────────────────────────
interface CostConfirmState {
  verdict: CostVerdict | null;
  loading: boolean;
  onConfirm: (() => Promise<void>) | null;
  onCancel: (() => void) | null;
  ouvrir: (
    v: CostVerdict,
    onConfirm: () => Promise<void>,
    onCancel: () => void,
  ) => void;
  fermer: () => void;
  setLoading: (b: boolean) => void;
}

export const useCostConfirmStore = create<CostConfirmState>((set) => ({
  verdict: null,
  loading: false,
  onConfirm: null,
  onCancel: null,
  ouvrir: (verdict, onConfirm, onCancel) =>
    set({ verdict, onConfirm, onCancel, loading: false }),
  fermer: () => set({ verdict: null, onConfirm: null, onCancel: null, loading: false }),
  setLoading: (b) => set({ loading: b }),
}));

// ── Composant racine à monter dans App.tsx ────────────────────────────────────
export interface CostConfirmModalRootProps {
  t?: (k: string, fb?: string) => string;
  /** URL de redirection si user clique "Recharger". Défaut /abonnement. */
  hrefRecharge?: string;
}

const _tf = (_k: string, fb?: string) => fb || _k;

export const CostConfirmModalRoot = ({
  t = _tf, hrefRecharge = "/abonnement",
}: CostConfirmModalRootProps = {}) => {
  const { verdict, loading, onConfirm, onCancel, fermer, setLoading } =
    useCostConfirmStore();

  if (!verdict) return null;

  const isBlock = verdict.type === "credits_insuffisants";
  const handleConfirm = async () => {
    if (!onConfirm) return fermer();
    setLoading(true);
    try {
      await onConfirm();
    } finally {
      fermer();
    }
  };
  const handleCancel = () => {
    if (onCancel) onCancel();
    fermer();
  };

  return (
    <div
      className="fixed inset-0 z-[10000] bg-slate-900/70 backdrop-blur-sm
                 flex items-end md:items-center justify-center p-0 md:p-4"
      onClick={loading ? undefined : handleCancel}
    >
      <div
        className="bg-white w-full md:max-w-md rounded-t-2xl md:rounded-2xl
                   shadow-2xl p-5 md:p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 mb-4">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center
                            ${isBlock ? "bg-rose-100" : "bg-amber-100"}`}>
            {isBlock
              ? <CreditCard className="w-5 h-5 text-rose-600" />
              : <AlertTriangle className="w-5 h-5 text-amber-600" />}
          </div>
          <div className="flex-grow">
            <h2 className="font-bold text-lg text-slate-900">
              {isBlock
                ? t("cost.titre_block", "Crédits insuffisants")
                : t("cost.titre_confirm", "Cette opération va consommer beaucoup de crédits")}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {t("cost.plan_label", "Plan")} : <span className="font-medium">{verdict.plan}</span>
            </p>
          </div>
          {!loading && (
            <button onClick={handleCancel}
                    className="text-slate-400 hover:text-slate-700 p-1">
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        <p className="text-sm text-slate-700 mb-4">{verdict.message_user}</p>

        <div className="bg-slate-50 rounded-lg p-3 mb-4 grid grid-cols-2 gap-2 text-sm">
          <Stat label={t("cost.cout", "Coût estimé")}
                valeur={`${verdict.cout_credits_estime} cr`}
                sous={`~${verdict.cout_fcfa_estime} FCFA`} />
          <Stat label={t("cost.solde", "Solde actuel")}
                valeur={`${verdict.solde_credits_avant} cr`} />
          <Stat label={t("cost.apres", "Solde après")}
                valeur={`${Math.max(0, verdict.solde_credits_apres_estime)} cr`}
                tone={isBlock ? "rose" : "default"} />
          <Stat label={t("cost.pct", "Du solde")}
                valeur={`${Math.min(999, verdict.pct_solde_consomme)}%`}
                tone={isBlock ? "rose" : "amber"} />
        </div>

        <div className="flex flex-col-reverse md:flex-row gap-2">
          {isBlock ? (
            <>
              <button onClick={handleCancel}
                      className="flex-1 px-4 py-2.5 rounded-lg bg-slate-100
                                 hover:bg-slate-200 text-sm font-medium min-h-[44px]">
                {t("cost.fermer", "Fermer")}
              </button>
              <a href={hrefRecharge}
                 className="flex-1 inline-flex items-center justify-center gap-2
                            px-4 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700
                            text-white text-sm font-medium shadow min-h-[44px]">
                <CreditCard className="w-4 h-4" />
                {t("cost.recharger", "Recharger")}
              </a>
            </>
          ) : (
            <>
              <button onClick={handleCancel} disabled={loading}
                      className="flex-1 px-4 py-2.5 rounded-lg bg-slate-100
                                 hover:bg-slate-200 text-sm font-medium
                                 disabled:opacity-50 min-h-[44px]">
                {t("cost.annuler", "Annuler")}
              </button>
              <a href={hrefRecharge}
                 className="flex-1 inline-flex items-center justify-center gap-2
                            px-4 py-2.5 rounded-lg bg-amber-100 hover:bg-amber-200
                            text-amber-900 text-sm font-medium min-h-[44px]">
                <CreditCard className="w-4 h-4" />
                {t("cost.recharger", "Recharger")}
              </a>
              <button onClick={handleConfirm} disabled={loading}
                      className="flex-1 inline-flex items-center justify-center gap-2
                                 px-4 py-2.5 rounded-lg bg-violet-600 hover:bg-violet-700
                                 disabled:opacity-50 text-white text-sm font-medium
                                 shadow min-h-[44px]">
                {loading
                  ? <Loader2 className="w-4 h-4 animate-spin" />
                  : null}
                {t("cost.continuer", "Continuer")}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const Stat = ({ label, valeur, sous, tone = "default" }: {
  label: string; valeur: string; sous?: string;
  tone?: "default" | "amber" | "rose";
}) => {
  const tones = {
    default: "text-slate-900",
    amber: "text-amber-900",
    rose: "text-rose-900",
  };
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`text-lg font-bold ${tones[tone]}`}>{valeur}</div>
      {sous && <div className="text-[11px] text-slate-500">{sous}</div>}
    </div>
  );
};

// ── Interceptor axios — installer 1 fois sur l'instance http de l'app ────────
type AxiosLike = {
  interceptors: {
    response: { use: (onOk: any, onErr: any) => any };
  };
  request: (cfg: any) => Promise<any>;
};

export const installCostInterceptor = (http: AxiosLike) => {
  http.interceptors.response.use(
    (r: any) => r,
    async (err: any) => {
      const detail = err?.response?.data?.detail;
      const status = err?.response?.status;

      // 402 cost_confirm_required → ouvre la modale, re-joue si OK
      if (status === 402 && detail && typeof detail === "object"
          && detail.type === "cost_confirm_required") {
        const verdict: CostVerdict = detail;
        return new Promise((resolve, reject) => {
          useCostConfirmStore.getState().ouvrir(
            verdict,
            async () => {
              try {
                const cfg = { ...err.config };
                // Ajoute confirmer_cout=true dans le body JSON
                let body: any = {};
                try { body = JSON.parse(cfg.data || "{}"); }
                catch { body = cfg.data || {}; }
                body.confirmer_cout = true;
                cfg.data = JSON.stringify(body);
                const r = await http.request(cfg);
                resolve(r);
              } catch (e) { reject(e); }
            },
            () => reject(err),
          );
        });
      }

      // 402 credits_insuffisants (object) — affiche la modale "block"
      if (status === 402 && detail && typeof detail === "object"
          && detail.type === "credits_insuffisants") {
        useCostConfirmStore.getState().ouvrir(
          detail as CostVerdict, async () => {}, () => {},
        );
      }
      return Promise.reject(err);
    },
  );
};
