import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import fr from "./fr.json";
import en from "./en.json";
import es from "./es.json";
import pt from "./pt.json";
import ar from "./ar.json";

export const SUPPORTED_LANGUAGES = [
  { code: "fr", label: "Français",  flag: "🇫🇷", dir: "ltr" },
  { code: "en", label: "English",   flag: "🇬🇧", dir: "ltr" },
  { code: "es", label: "Español",   flag: "🇪🇸", dir: "ltr" },
  { code: "pt", label: "Português", flag: "🇵🇹", dir: "ltr" },
  { code: "ar", label: "العربية",   flag: "🇸🇦", dir: "rtl" },
];

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
      lookupLocalStorage: "yukpo_sec_lang",
    },
    interpolation: { escapeValue: false },
    returnNull: false,
    returnEmptyString: false,
  });

export default i18n;
