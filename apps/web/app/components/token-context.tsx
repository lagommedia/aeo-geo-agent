'use client';

import { createContext, useContext, useEffect, useState } from 'react';

const TokenContext = createContext<string>('');

export function TokenProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState('');

  useEffect(() => {
    function refresh() {
      setToken(localStorage.getItem('dc_token') || '');
    }
    refresh();
    window.addEventListener('dc-auth', refresh);
    return () => window.removeEventListener('dc-auth', refresh);
  }, []);

  return <TokenContext.Provider value={token}>{children}</TokenContext.Provider>;
}

export function useToken() {
  return useContext(TokenContext);
}
