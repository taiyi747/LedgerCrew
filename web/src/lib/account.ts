import { api } from './api';
export type Account = { id: string; username: string; role: 'customer' | 'owner' };
export type Trial = { order_no: string; user_id: string; username: string; plan_id: 'FREE'; plan_name: string; amount_cents: number; payment_status: 'not_required'; status: 'pending'; created_at: string };
export const accountApi = {
  me: () => api<Account>('/auth/me'),
  login: (username: string, password: string) => api<Account>('/auth/login', { method:'POST', body:JSON.stringify({username,password}) }),
  register: (username: string, password: string, confirm_password: string) => api<Account>('/auth/register', { method:'POST', body:JSON.stringify({username,password,confirm_password}) }),
  trial: (request_id: string) => api<Trial>('/auth/trial', { method:'POST', body:JSON.stringify({request_id}) }),
  logout: () => api('/auth/logout', {method:'POST'}),
};
// Only the existing customer page can be used as a return destination.
export function uploadDestination(value: string | null) {
  if (!value) return '/upload/';
  try { const url = new URL(value, 'https://ledgercrew.invalid');
    return url.origin === 'https://ledgercrew.invalid' && url.pathname === '/upload/' ? url.pathname + url.search + url.hash : '/upload/';
  } catch { return '/upload/'; }
}
