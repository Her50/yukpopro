import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import fr from "./fr.json";
import en from "./en.json";
import es from "./es.json";
import pt from "./pt.json";
import ar from "./ar.json";

export const SUPPORTED_LANGUAGES = [
  { code: "fr", label: "Français",   flag: "🇫🇷", dir: "ltr" },
  { code: "en", label: "English",    flag: "🇬🇧", dir: "ltr" },
  { code: "es", label: "Español",    flag: "🇪🇸", dir: "ltr" },
  { code: "pt", label: "Português",  flag: "🇵🇹", dir: "ltr" },
  { code: "ar", label: "العربية",    flag: "🇸🇦", dir: "rtl" },
];

// Map country code → language code for auto-detection at registration
export const COUNTRY_LANGUAGE_MAP: Record<string, string> = {
  // Francophone Africa + Europe
  CM: "fr", CI: "fr", SN: "fr", TG: "fr", BJ: "fr", BF: "fr",
  ML: "fr", GA: "fr", CG: "fr", CD: "fr", MG: "fr", RW: "fr",
  MR: "fr", NE: "fr", TD: "fr", GN: "fr", CF: "fr", DJ: "fr",
  FR: "fr", BE: "fr", CH: "fr", LU: "fr", MC: "fr",
  // Arabic
  MA: "ar", TN: "ar", DZ: "ar", EG: "ar", LY: "ar", SA: "ar",
  AE: "ar", QA: "ar", KW: "ar", BH: "ar", OM: "ar", JO: "ar",
  SY: "ar", IQ: "ar", LB: "ar", YE: "ar", SD: "ar",
  // English Africa + Anglophone
  NG: "en", GH: "en", KE: "en", ZA: "en", TZ: "en", UG: "en",
  RW: "en", ET: "en", MU: "en", SL: "en", LR: "en", GM: "en",
  GB: "en", US: "en", CA: "en", AU: "en", NZ: "en", IE: "en",
  IN: "en", PK: "en", SG: "en", ZW: "en", ZM: "en", MW: "en",
  // Portuguese
  PT: "pt", BR: "pt", AO: "pt", MZ: "pt", CV: "pt", ST: "pt",
  GW: "pt", GQ: "pt",
  // Spanish
  ES: "es", MX: "es", AR: "es", CO: "es", CL: "es", PE: "es",
  VE: "es", EC: "es", BO: "es", PY: "es", UY: "es", CU: "es",
  DO: "es", GT: "es", HN: "es", SV: "es", NI: "es", CR: "es",
  PA: "es", GQ: "es",
};

export function detectLanguageFromCountry(countryCode: string): string {
  return COUNTRY_LANGUAGE_MAP[countryCode.toUpperCase()] || "fr";
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      fr: { translation: fr },
      en: { translation: en },
      es: { translation: es },
      pt: { translation: pt },
      ar: { translation: ar },
    },
    fallbackLng: "fr",
    supportedLngs: ["fr", "en", "es", "pt", "ar"],
    detection: {
      order: ["localStorage", "navigator", "htmlTag"],
      caches: ["localStorage"],
      lookupLocalStorage: "yukpo_lang",
    },
    interpolation: {
      escapeValue: false,
    },
    returnNull: false,
    returnEmptyString: false,
  });

export default i18n;
