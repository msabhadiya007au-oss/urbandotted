import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api, setBusinessId, errText } from "@/lib/api";

const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

export function AppProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = anon
  const [meta, setMeta] = useState(null);
  const [fy, setFy] = useState(localStorage.getItem("ud_fy") || "");
  const [business, setBusiness] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const bump = useCallback(() => setRefreshKey((k) => k + 1), []);

  const loadMeta = useCallback(async (u) => {
    setBusinessId(u?.default_business_id || null);
    try {
      const { data } = await api.get("/meta");
      setMeta(data);
      setBusiness(data.businesses?.[0] || null);
      setFy((prev) => (prev && data.fy_options.includes(prev) ? prev : data.current_fy));
    } catch (e) {
      /* ignore */
    }
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      await loadMeta(data);
    } catch {
      setUser(false);
    }
  }, [loadMeta]);

  useEffect(() => {
    if (window.location.hash?.includes("session_id=")) return;
    checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    if (fy) localStorage.setItem("ud_fy", fy);
  }, [fy]);

  const onAuthed = useCallback(async (u) => {
    setUser(u);
    await loadMeta(u);
  }, [loadMeta]);

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch { /* noop */ }
    setUser(false);
    setMeta(null);
  };

  return (
    <AppContext.Provider value={{
      user, setUser, meta, fy, setFy, business, setBusiness, logout, onAuthed,
      checkAuth, refreshKey, bump, errText,
    }}>
      {children}
    </AppContext.Provider>
  );
}
