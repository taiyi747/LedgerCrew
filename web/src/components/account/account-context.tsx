'use client';
import { createContext, useContext, type ReactNode } from 'react';
import type { Account } from '@/lib/account';

const AccountContext = createContext<Account | null>(null);

export function AccountProvider({ account, children }: { account: Account | null; children: ReactNode }) {
  return <AccountContext.Provider value={account}>{children}</AccountContext.Provider>;
}

/** Signed-in account, or null while signed out. */
export function useAccount(): Account | null {
  return useContext(AccountContext);
}
