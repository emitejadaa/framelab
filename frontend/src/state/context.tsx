import { createContext, useContext } from "react";
import { useStore } from "zustand";
import type { AppState, AppStore } from "./store";

const StoreContext = createContext<AppStore | null>(null);

export const StoreProvider = StoreContext.Provider;

export function useAppStore<T>(selector: (state: AppState) => T): T {
  const store = useContext(StoreContext);
  if (!store) throw new Error("useAppStore must be used inside <StoreProvider>");
  return useStore(store, selector);
}
