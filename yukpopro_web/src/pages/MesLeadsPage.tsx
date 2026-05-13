/**
 * MesLeadsPage — YukpoPro
 *
 * Wrapper qui monte <LeadsDashboard> de @yukpo/leads-dashboard.
 * La même page existe côté yukposecretariat_web — toutes deux affichent
 * les leads capturés par les landings publiées du user connecté.
 *
 * Endpoints consommés (via http injecté) :
 *   GET    /api/v1/pro/landing-leads
 *   GET    /api/v1/pro/landing-publications
 *   PATCH  /api/v1/pro/landing-leads/{id}
 *   GET    /api/v1/pro/landing-leads/export.csv
 */
import { LeadsDashboard } from "@yukpo/leads-dashboard";
import { useTranslation } from "react-i18next";
import { http } from "@/api/client";

export const MesLeadsPage = () => {
  const { t } = useTranslation();
  return <LeadsDashboard http={http} t={t as any} />;
};
