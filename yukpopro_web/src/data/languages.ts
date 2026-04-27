import { normalize } from './countries'

export interface Language {
  code: string
  name: string
  native: string
}

export const LANGUAGES: Language[] = [
  { code: 'af', name: 'Afrikaans', native: 'Afrikaans' },
  { code: 'sq', name: 'Albanais', native: 'Shqip' },
  { code: 'de', name: 'Allemand', native: 'Deutsch' },
  { code: 'am', name: 'Amharique', native: 'አማርኛ' },
  { code: 'en', name: 'Anglais', native: 'English' },
  { code: 'ar', name: 'Arabe', native: 'العربية' },
  { code: 'hy', name: 'Arménien', native: 'Հայերեն' },
  { code: 'az', name: 'Azéri', native: 'Azərbaycan' },
  { code: 'eu', name: 'Basque', native: 'Euskara' },
  { code: 'bn', name: 'Bengali', native: 'বাংলা' },
  { code: 'be', name: 'Biélorusse', native: 'Беларуская' },
  { code: 'my', name: 'Birman', native: 'မြန်မာ' },
  { code: 'bs', name: 'Bosniaque', native: 'Bosanski' },
  { code: 'bg', name: 'Bulgare', native: 'Български' },
  { code: 'ca', name: 'Catalan', native: 'Català' },
  { code: 'zh', name: 'Chinois', native: '中文' },
  { code: 'ko', name: 'Coréen', native: '한국어' },
  { code: 'hr', name: 'Croate', native: 'Hrvatski' },
  { code: 'da', name: 'Danois', native: 'Dansk' },
  { code: 'es', name: 'Espagnol', native: 'Español' },
  { code: 'et', name: 'Estonien', native: 'Eesti' },
  { code: 'fi', name: 'Finnois', native: 'Suomi' },
  { code: 'fr', name: 'Français', native: 'Français' },
  { code: 'gl', name: 'Galicien', native: 'Galego' },
  { code: 'cy', name: 'Gallois', native: 'Cymraeg' },
  { code: 'ka', name: 'Géorgien', native: 'ქართული' },
  { code: 'el', name: 'Grec', native: 'Ελληνικά' },
  { code: 'gu', name: 'Gujarati', native: 'ગુજરાતી' },
  { code: 'ha', name: 'Haoussa', native: 'Hausa' },
  { code: 'he', name: 'Hébreu', native: 'עברית' },
  { code: 'hi', name: 'Hindi', native: 'हिन्दी' },
  { code: 'hu', name: 'Hongrois', native: 'Magyar' },
  { code: 'ig', name: 'Igbo', native: 'Igbo' },
  { code: 'id', name: 'Indonésien', native: 'Bahasa Indonesia' },
  { code: 'ga', name: 'Irlandais', native: 'Gaeilge' },
  { code: 'is', name: 'Islandais', native: 'Íslenska' },
  { code: 'it', name: 'Italien', native: 'Italiano' },
  { code: 'ja', name: 'Japonais', native: '日本語' },
  { code: 'jv', name: 'Javanais', native: 'Basa Jawa' },
  { code: 'kn', name: 'Kannada', native: 'ಕನ್ನಡ' },
  { code: 'kk', name: 'Kazakh', native: 'Қазақ' },
  { code: 'km', name: 'Khmer', native: 'ខ្មែរ' },
  { code: 'rw', name: 'Kinyarwanda', native: 'Kinyarwanda' },
  { code: 'ky', name: 'Kirghize', native: 'Кыргызча' },
  { code: 'ku', name: 'Kurde', native: 'Kurdî' },
  { code: 'lo', name: 'Laotien', native: 'ລາວ' },
  { code: 'la', name: 'Latin', native: 'Latina' },
  { code: 'lv', name: 'Letton', native: 'Latviešu' },
  { code: 'lt', name: 'Lituanien', native: 'Lietuvių' },
  { code: 'lb', name: 'Luxembourgeois', native: 'Lëtzebuergesch' },
  { code: 'mk', name: 'Macédonien', native: 'Македонски' },
  { code: 'ms', name: 'Malais', native: 'Bahasa Melayu' },
  { code: 'ml', name: 'Malayalam', native: 'മലയാളം' },
  { code: 'mt', name: 'Maltais', native: 'Malti' },
  { code: 'mi', name: 'Maori', native: 'Māori' },
  { code: 'mr', name: 'Marathi', native: 'मराठी' },
  { code: 'mn', name: 'Mongol', native: 'Монгол' },
  { code: 'ne', name: 'Népalais', native: 'नेपाली' },
  { code: 'no', name: 'Norvégien', native: 'Norsk' },
  { code: 'or', name: 'Odia', native: 'ଓଡ଼ିଆ' },
  { code: 'ur', name: 'Ourdou', native: 'اردو' },
  { code: 'uz', name: 'Ouzbek', native: 'Oʻzbek' },
  { code: 'ps', name: 'Pachto', native: 'پښتو' },
  { code: 'pa', name: 'Pendjabi', native: 'ਪੰਜਾਬੀ' },
  { code: 'fa', name: 'Persan', native: 'فارسی' },
  { code: 'fil', name: 'Philippin', native: 'Filipino' },
  { code: 'pl', name: 'Polonais', native: 'Polski' },
  { code: 'pt', name: 'Portugais', native: 'Português' },
  { code: 'ro', name: 'Roumain', native: 'Română' },
  { code: 'ru', name: 'Russe', native: 'Русский' },
  { code: 'sr', name: 'Serbe', native: 'Српски' },
  { code: 'sn', name: 'Shona', native: 'ChiShona' },
  { code: 'sd', name: 'Sindhi', native: 'سنڌي' },
  { code: 'si', name: 'Singhalais', native: 'සිංහල' },
  { code: 'sk', name: 'Slovaque', native: 'Slovenčina' },
  { code: 'sl', name: 'Slovène', native: 'Slovenščina' },
  { code: 'so', name: 'Somali', native: 'Soomaali' },
  { code: 'sv', name: 'Suédois', native: 'Svenska' },
  { code: 'sw', name: 'Swahili', native: 'Kiswahili' },
  { code: 'tg', name: 'Tadjik', native: 'Тоҷикӣ' },
  { code: 'ta', name: 'Tamoul', native: 'தமிழ்' },
  { code: 'cs', name: 'Tchèque', native: 'Čeština' },
  { code: 'te', name: 'Télougou', native: 'తెలుగు' },
  { code: 'th', name: 'Thaï', native: 'ไทย' },
  { code: 'ti', name: 'Tigrigna', native: 'ትግርኛ' },
  { code: 'tr', name: 'Turc', native: 'Türkçe' },
  { code: 'tk', name: 'Turkmène', native: 'Türkmen' },
  { code: 'uk', name: 'Ukrainien', native: 'Українська' },
  { code: 'vi', name: 'Vietnamien', native: 'Tiếng Việt' },
  { code: 'xh', name: 'Xhosa', native: 'isiXhosa' },
  { code: 'yo', name: 'Yoruba', native: 'Yorùbá' },
  { code: 'zu', name: 'Zoulou', native: 'isiZulu' },
]

export function findLanguage(code: string): Language | undefined {
  return LANGUAGES.find((l) => l.code === code)
}

export function searchLanguages(q: string): Language[] {
  const n = normalize(q.trim())
  if (!n) return LANGUAGES
  return LANGUAGES.filter((l) =>
    normalize(l.name).includes(n) ||
    normalize(l.native).includes(n) ||
    l.code.toLowerCase().includes(n)
  )
}
