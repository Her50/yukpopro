import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import AsyncStorage from '@react-native-async-storage/async-storage'

import fr from './fr.json'
import en from './en.json'
import es from './es.json'
import pt from './pt.json'
import ar from './ar.json'
import de from './de.json'
import zh from './zh.json'
import sw from './sw.json'
import ha from './ha.json'
import ru from './ru.json'
import hi from './hi.json'
import tr from './tr.json'
import wo from './wo.json'
import ln from './ln.json'
import am from './am.json'

const STORAGE_KEY = 'sec_lang'

export const SUPPORTED_LANGUAGES = [
  { code: 'fr', label: 'Français', flag: '🇫🇷', dir: 'ltr' },
  { code: 'en', label: 'English', flag: '🇬🇧', dir: 'ltr' },
  { code: 'es', label: 'Español', flag: '🇪🇸', dir: 'ltr' },
  { code: 'pt', label: 'Português', flag: '🇧🇷', dir: 'ltr' },
  { code: 'ar', label: 'العربية', flag: '🇸🇦', dir: 'rtl' },
  { code: 'de', label: 'Deutsch', flag: '🇩🇪', dir: 'ltr' },
  { code: 'zh', label: '中文', flag: '🇨🇳', dir: 'ltr' },
  { code: 'sw', label: 'Kiswahili', flag: '🇹🇿', dir: 'ltr' },
  { code: 'ha', label: 'Hausa', flag: '🇳🇬', dir: 'ltr' },
  { code: 'ru', label: 'Русский', flag: '🇷🇺', dir: 'ltr' },
  { code: 'hi', label: 'हिन्दी', flag: '🇮🇳', dir: 'ltr' },
  { code: 'tr', label: 'Türkçe', flag: '🇹🇷', dir: 'ltr' },
  { code: 'wo', label: 'Wolof', flag: '🇸🇳', dir: 'ltr' },
  { code: 'ln', label: 'Lingala', flag: '🇨🇩', dir: 'ltr' },
  { code: 'am', label: 'አማርኛ', flag: '🇪🇹', dir: 'ltr' },
]

i18n.use(initReactI18next).init({
  resources: {
    fr: { translation: fr }, en: { translation: en }, es: { translation: es },
    pt: { translation: pt }, ar: { translation: ar }, de: { translation: de },
    zh: { translation: zh }, sw: { translation: sw }, ha: { translation: ha },
    ru: { translation: ru }, hi: { translation: hi }, tr: { translation: tr },
    wo: { translation: wo }, ln: { translation: ln }, am: { translation: am },
  },
  lng: 'fr',
  fallbackLng: 'fr',
  supportedLngs: ['fr', 'en', 'es', 'pt', 'ar', 'de', 'zh', 'sw', 'ha', 'ru', 'hi', 'tr', 'wo', 'ln', 'am'],
  interpolation: { escapeValue: false },
  returnNull: false,
  returnEmptyString: false,
})

AsyncStorage.getItem(STORAGE_KEY).then(lng => {
  if (lng && i18n.language !== lng) i18n.changeLanguage(lng)
}).catch(() => {})

export const setAppLanguage = async (lng: string) => {
  await i18n.changeLanguage(lng)
  await AsyncStorage.setItem(STORAGE_KEY, lng)
}

export default i18n
