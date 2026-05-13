/**
 * PublierLandingPage — YukpoPro
 *
 * Page dédiée affichant le composant <PublierLandingButton> en mode "full"
 * pour publier une landing déjà générée (depuis le chat). Récupère le
 * fichier_id en paramètre d'URL.
 */
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";
import { PublierLandingButton } from "@yukpo/leads-dashboard";
import { generateurApi } from "@/api/client";
import { useAuthStore } from "@/store";

export const PublierLandingPage = () => {
  const { t } = useTranslation();
  const { fichierId } = useParams<{ fichierId: string }>();
  const { user } = useAuthStore();
  const plan = ((user as any)?.plan || "free") as "free" | "pro" | "business";

  if (!fichierId) {
    return <div className="p-6 text-center text-rose-700">fichier_id manquant.</div>;
  }

  return (
    <div className="p-4 md:p-6 max-w-2xl mx-auto">
      <Link
        to="/chat"
        className="inline-flex items-center gap-1 text-sm text-slate-600 hover:text-slate-900 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        {t("commun.retour_chat", "Retour au chat")}
      </Link>
      <h1 className="text-2xl md:text-3xl font-bold mb-2">
        {t("landing.publier.page_titre", "Publier votre landing")}
      </h1>
      <p className="text-sm text-slate-600 mb-6">
        {t("landing.publier.page_sous_titre",
           "Choisissez un sous-domaine custom et déployez en un clic sur Netlify.")}
      </p>
      <PublierLandingButton
        fichierId={fichierId}
        publier={generateurApi.publierLanding}
        plan={plan}
        t={t as any}
        variant="full"
      />
    </div>
  );
};
