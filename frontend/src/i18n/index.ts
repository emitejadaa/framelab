import i18next, { type i18n } from "i18next";
import en from "./locales/en.json";
import es from "./locales/es.json";

export type Lang = "es" | "en";

export function pickLanguage(pref: unknown, navigatorLangs: readonly string[]): Lang {
  if (pref === "es" || pref === "en") return pref;
  for (const tag of navigatorLangs) {
    const base = tag.toLowerCase().split("-")[0];
    if (base === "es" || base === "en") return base;
  }
  return "en";
}

/** A private i18next instance per mounted UI (no global singleton). */
export function createI18n(lang: Lang): i18n {
  const instance = i18next.createInstance();
  void instance.init({
    lng: lang,
    fallbackLng: "en",
    resources: { en: { translation: en }, es: { translation: es } },
    interpolation: { escapeValue: false },
    initAsync: false,
  });
  return instance;
}
