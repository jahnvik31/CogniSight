import { createContext, useContext } from "solid-js";

// The /api/status poll, shared by the layout (status dot), Live, and Device.
export const StatusContext = createContext();

export function useStatus() {
  return useContext(StatusContext);
}
