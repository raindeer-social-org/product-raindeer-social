"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

const TOKEN_STORAGE_KEY = "raindeer.auth.token";

interface AuthContextValue {
  /** The bearer token, or null when signed out. */
  token: string | null;
  /** True until the initial localStorage read completes. */
  isLoading: boolean;
  login: (token: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const stored = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    setToken(stored);
    setIsLoading(false);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      isLoading,
      login: (newToken: string) => {
        window.localStorage.setItem(TOKEN_STORAGE_KEY, newToken);
        setToken(newToken);
      },
      logout: () => {
        window.localStorage.removeItem(TOKEN_STORAGE_KEY);
        setToken(null);
      },
    }),
    [token, isLoading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
