import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type { User } from '../types';
import { authApi, tokenStore } from '../services/api';

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  isCustomer: boolean;
  isStaff: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Re-establish the session on a hard refresh.
  useEffect(() => {
    let cancelled = false;
    if (!tokenStore.get()) {
      setLoading(false);
      return;
    }
    authApi
      .me()
      .then((res) => {
        if (!cancelled) setUser(res.data);
      })
      .catch(() => {
        // Token invalid/expired — the interceptor has already cleared it.
        tokenStore.clear();
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await authApi.login({ email, password });
    tokenStore.set(data.access_token);
    const me = await authApi.me();
    setUser(me.data);
  }, []);

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      await authApi.register({ name, email, password });
      await login(email, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isCustomer: user?.role === 'customer',
      isStaff: user?.role === 'staff',
      login,
      register,
      logout,
    }),
    [user, loading, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside an AuthProvider');
  return ctx;
}