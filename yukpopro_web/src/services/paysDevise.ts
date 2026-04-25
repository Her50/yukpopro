/**
 * paysDevise — Mapping pays → devise pour affichages informatifs.
 *
 * Usage : formatAmount(montant, pays) → "1 250 000 FCFA" / "$1,250" / "₦450,000"
 *
 * ATTENTION : N'utilise PAS ce helper pour l'abonnement / wallet (paiement
 * mobile money en XAF/XOF uniquement).
 */

type DeviseInfo = { code: string; symbole: string; sep: string };

export const PAYS_DEVISE: Record<string, DeviseInfo> = {
  // CEMAC (XAF)
  CM: { code: "XAF", symbole: "FCFA", sep: " " },
  GA: { code: "XAF", symbole: "FCFA", sep: " " },
  CG: { code: "XAF", symbole: "FCFA", sep: " " },
  TD: { code: "XAF", symbole: "FCFA", sep: " " },
  CF: { code: "XAF", symbole: "FCFA", sep: " " },
  GQ: { code: "XAF", symbole: "FCFA", sep: " " },
  // UEMOA (XOF)
  SN: { code: "XOF", symbole: "FCFA", sep: " " },
  CI: { code: "XOF", symbole: "FCFA", sep: " " },
  BF: { code: "XOF", symbole: "FCFA", sep: " " },
  ML: { code: "XOF", symbole: "FCFA", sep: " " },
  NE: { code: "XOF", symbole: "FCFA", sep: " " },
  TG: { code: "XOF", symbole: "FCFA", sep: " " },
  BJ: { code: "XOF", symbole: "FCFA", sep: " " },
  GW: { code: "XOF", symbole: "FCFA", sep: " " },
  // Afrique anglophone / autres
  NG: { code: "NGN", symbole: "₦", sep: "," },
  GH: { code: "GHS", symbole: "GH₵", sep: "," },
  KE: { code: "KES", symbole: "KSh", sep: "," },
  TZ: { code: "TZS", symbole: "TSh", sep: "," },
  UG: { code: "UGX", symbole: "USh", sep: "," },
  RW: { code: "RWF", symbole: "RF", sep: "," },
  ET: { code: "ETB", symbole: "Br", sep: "," },
  ZA: { code: "ZAR", symbole: "R", sep: " " },
  EG: { code: "EGP", symbole: "E£", sep: "," },
  MA: { code: "MAD", symbole: "DH", sep: " " },
  DZ: { code: "DZD", symbole: "DA", sep: " " },
  TN: { code: "TND", symbole: "DT", sep: " " },
  AO: { code: "AOA", symbole: "Kz", sep: " " },
  MZ: { code: "MZN", symbole: "MT", sep: " " },
  CD: { code: "CDF", symbole: "FC", sep: " " },
  MG: { code: "MGA", symbole: "Ar", sep: " " },
  MU: { code: "MUR", symbole: "Rs", sep: "," },
  // Hors Afrique
  FR: { code: "EUR", symbole: "€", sep: " " },
  BE: { code: "EUR", symbole: "€", sep: " " },
  DE: { code: "EUR", symbole: "€", sep: "." },
  ES: { code: "EUR", symbole: "€", sep: "." },
  IT: { code: "EUR", symbole: "€", sep: "." },
  PT: { code: "EUR", symbole: "€", sep: "." },
  GB: { code: "GBP", symbole: "£", sep: "," },
  US: { code: "USD", symbole: "$", sep: "," },
  CA: { code: "CAD", symbole: "CA$", sep: "," },
  CH: { code: "CHF", symbole: "CHF", sep: " " },
  CN: { code: "CNY", symbole: "¥", sep: "," },
  IN: { code: "INR", symbole: "₹", sep: "," },
  JP: { code: "JPY", symbole: "¥", sep: "," },
  BR: { code: "BRL", symbole: "R$", sep: "." },
  AE: { code: "AED", symbole: "AED", sep: "," },
  SA: { code: "SAR", symbole: "SAR", sep: "," },
  TR: { code: "TRY", symbole: "₺", sep: "." },
  RU: { code: "RUB", symbole: "₽", sep: " " },
};

const DEFAUT: DeviseInfo = { code: "XAF", symbole: "FCFA", sep: " " };
const PREFIXES = new Set(["€", "$", "£", "¥", "₦", "₹", "₽", "₺", "R$", "CA$", "GH₵"]);

export function getDevise(pays?: string | null): DeviseInfo {
  if (!pays) return DEFAUT;
  return PAYS_DEVISE[pays.trim().toUpperCase()] ?? DEFAUT;
}

export function formatAmount(montant: number | null | undefined, pays?: string | null): string {
  if (montant == null || isNaN(Number(montant))) return "—";
  const { symbole, sep } = getDevise(pays);
  const n = Number(montant);
  const formatted =
    n === Math.trunc(n)
      ? Math.trunc(n).toLocaleString("en-US").replace(/,/g, sep)
      : n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace(/,/g, sep);
  return PREFIXES.has(symbole) ? `${symbole}${formatted}` : `${formatted} ${symbole}`;
}
