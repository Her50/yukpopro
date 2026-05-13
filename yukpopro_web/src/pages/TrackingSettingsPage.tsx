/**
 * TrackingSettingsPage — YukpoPro
 *
 * Page /tracking-settings qui monte le panneau partagé Tracking & Email
 * automation pour configurer pixels (FB/GA4/TikTok/Snap/Clarity),
 * newsletter (Brevo/Mailchimp) et templates email J+0/J+3/J+7.
 */
import { TrackingSettingsPanel } from "@yukpo/leads-dashboard";
import { useTranslation } from "react-i18next";
import { http } from "@/api/client";

export const TrackingSettingsPage = () => {
  const { t } = useTranslation();
  return <TrackingSettingsPanel http={http} t={t as any} />;
};
