'use client';

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import {
  signIn as cognitoSignIn,
  signOut as cognitoSignOut,
  completeNewPassword as cognitoCompleteNewPassword,
  getSession,
  type AuthResult,
} from './cognito';

interface AuthContextValue {
  user: AuthResult | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  completeNewPassword: (newPassword: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getSession().then((session) => {
      setUser(session);
      setLoading(false);
    });
  }, []);

  const handleSignIn = useCallback(async (email: string, password: string) => {
    const result = await cognitoSignIn(email, password);
    setUser(result);
  }, []);

  const handleCompleteNewPassword = useCallback(async (newPassword: string) => {
    const result = await cognitoCompleteNewPassword(newPassword);
    setUser(result);
  }, []);

  const handleSignOut = useCallback(() => {
    cognitoSignOut();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{
      user,
      loading,
      signIn: handleSignIn,
      completeNewPassword: handleCompleteNewPassword,
      signOut: handleSignOut,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
