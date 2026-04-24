import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Globe, ChevronDown } from "lucide-react";
import { SUPPORTED_LANGUAGES } from "@/i18n";

interface Props {
  collapsed?: boolean;
}

export const LanguageSwitcher = ({ collapsed = false }: Props) => {
  const { i18n, t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const current = SUPPORTED_LANGUAGES.find((l) => l.code === i18n.language)
    ?? SUPPORTED_LANGUAGES.find((l) => l.code === i18n.language.split("-")[0])
    ?? SUPPORTED_LANGUAGES[0];

  const changeLanguage = (code: string) => {
    i18n.changeLanguage(code);
    document.documentElement.dir = SUPPORTED_LANGUAGES.find((l) => l.code === code)?.dir || "ltr";
    document.documentElement.lang = code;
    setOpen(false);
  };

  useEffect(() => {
    const dir = current.dir || "ltr";
    document.documentElement.dir = dir;
    document.documentElement.lang = current.code;
  }, [current]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title={t("language.select")}
        className={`flex items-center gap-2 w-full rounded-lg px-2 py-2 text-sm transition-colors
          hover:bg-white/10 text-slate-300 hover:text-white`}
      >
        <Globe size={16} className="flex-shrink-0" />
        {collapsed ? (
          /* En mode réduit : affiche le code langue sur 2 lettres pour identifier */
          <span className="text-[9px] font-bold uppercase tracking-wide opacity-70 -ml-0.5">
            {current.code.slice(0, 2)}
          </span>
        ) : (
          <>
            <span className="flex-1 text-left truncate">
              {current.flag} {current.label}
            </span>
            <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
          </>
        )}
      </button>

      {open && (
        <div
          className={`absolute z-50 bottom-full mb-2 ${collapsed ? "left-full ml-2" : "left-0 right-0"}
            bg-slate-800 border border-slate-600 rounded-xl shadow-xl overflow-hidden min-w-[160px]`}
        >
          <div className="px-3 py-2 border-b border-slate-700">
            <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              {t("language.select")}
            </p>
          </div>
          {SUPPORTED_LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => changeLanguage(lang.code)}
              className={`w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-colors text-left
                ${current.code === lang.code
                  ? "bg-sky-700/40 text-sky-200 font-medium"
                  : "text-slate-300 hover:bg-white/10 hover:text-white"}`}
            >
              <span className="text-base">{lang.flag}</span>
              <span className="flex-1">{lang.label}</span>
              {current.code === lang.code && (
                <span className="text-[10px] text-sky-300 font-semibold">✓</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
