import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import fr from "./fr.json";
import en from "./en.json";
import es from "./es.json";
import pt from "./pt.json";
import ar from "./ar.json";
import de from "./de.json";
import zh from "./zh.json";
import sw from "./sw.json";
import ha from "./ha.json";
import ru from "./ru.json";
import hi from "./hi.json";
import tr from "./tr.json";
import wo from "./wo.json";
import ln from "./ln.json";
import am from "./am.json";

export const SUPPORTED_LANGUAGES = [
  { code: "fr", label: "Français",   flag: "🇫🇷", dir: "ltr" },
  { code: "en", label: "English",    flag: "🇬🇧", dir: "ltr" },
  { code: "es", label: "Español",    flag: "🇪🇸", dir: "ltr" },
  { code: "pt", label: "Português",  flag: "🇧🇷", dir: "ltr" },
  { code: "ar", label: "العربية",    flag: "🇸🇦", dir: "rtl" },
  { code: "de", label: "Deutsch",    flag: "🇩🇪", dir: "ltr" },
  { code: "zh", label: "中文",        flag: "🇨🇳", dir: "ltr" },
  { code: "sw", label: "Kiswahili",  flag: "🇹🇿", dir: "ltr" },
  { code: "ha", label: "Hausa",      flag: "🇳🇬", dir: "ltr" },
  { code: "ru", label: "Русский",    flag: "🇷🇺", dir: "ltr" },
  { code: "hi", label: "हिन्दी",      flag: "🇮🇳", dir: "ltr" },
  { code: "tr", label: "Türkçe",     flag: "🇹🇷", dir: "ltr" },
  { code: "wo", label: "Wolof",      flag: "🇸🇳", dir: "ltr" },
  { code: "ln", label: "Lingala",    flag: "🇨🇩", dir: "ltr" },
  { code: "am", label: "አማርኛ",       flag: "🇪🇹", dir: "ltr" },
];

// Map country code → language code for auto-detection at registration
export const COUNTRY_LANGUAGE_MAP: Record<string, string> = {
  // Francophone Africa + Europe
  CM: "fr", CI: "fr", TG: "fr", BJ: "fr", BF: "fr",
  ML: "fr", GA: "fr", CG: "fr", MG: "fr",
  MR: "fr", NE: "fr", TD: "fr", GN: "fr", CF: "fr", DJ: "fr",
  FR: "fr", BE: "fr", CH: "fr", LU: "fr", MC: "fr",
  // Arabic
  MA: "ar", TN: "ar", DZ: "ar", EG: "ar", LY: "ar", SA: "ar",
  AE: "ar", QA: "ar", KW: "ar", BH: "ar", OM: "ar", JO: "ar",
  SY: "ar", IQ: "ar", LB: "ar", YE: "ar", SD: "ar",
  // English Africa + Anglophone
  GH: "en", ZA: "en", UG: "en",
  MU: "en", SL: "en", LR: "en", GM: "en",
  GB: "en", US: "en", CA: "en", AU: "en", NZ: "en", IE: "en",
  PK: "en", SG: "en", ZW: "en", ZM: "en", MW: "en",
  // Portuguese
  PT: "pt", BR: "pt", AO: "pt", MZ: "pt", CV: "pt", ST: "pt",
  GW: "pt", GQ: "pt",
  // Spanish
  ES: "es", MX: "es", AR: "es", CO: "es", CL: "es", PE: "es",
  VE: "es", EC: "es", BO: "es", PY: "es", UY: "es", CU: "es",
  DO: "es", GT: "es", HN: "es", SV: "es", NI: "es", CR: "es",
  PA: "es",
  // German
  DE: "de", AT: "de",
  // Chinese
  CN: "zh", TW: "zh", HK: "zh",
  // Swahili (East Africa)
  TZ: "sw", KE: "sw",
  // Hausa (West Africa)
  NG: "ha",
  // Russian
  RU: "ru", BY: "ru", KZ: "ru", UA: "ru",
  // Hindi
  IN: "hi",
  // Turkish
  TR: "tr",
  // Wolof (Senegal)
  SN: "wo",
  // Lingala (DRC/Congo)
  CD: "ln",
  // Amharic (Ethiopia)
  ET: "am", RW: "fr",
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
      de: { translation: de },
      zh: { translation: zh },
      sw: { translation: sw },
      ha: { translation: ha },
      ru: { translation: ru },
      hi: { translation: hi },
      tr: { translation: tr },
      wo: { translation: wo },
      ln: { translation: ln },
      am: { translation: am },
    },
    lng: "fr",
    fallbackLng: "fr",
    supportedLngs: ["fr", "en", "es", "pt", "ar", "de", "zh", "sw", "ha", "ru", "hi", "tr", "wo", "ln", "am"],
    detection: {
      order: ["localStorage"],
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
