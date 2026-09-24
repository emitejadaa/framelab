import { createContext, useContext } from "react";

const PortalContext = createContext<HTMLElement | null>(null);

export const PortalProvider = PortalContext.Provider;

/** Element inside `.fl-root` where menus, tooltips and drag ghosts must be portalled. */
export function usePortalContainer(): HTMLElement | null {
  return useContext(PortalContext);
}
