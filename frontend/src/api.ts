export type Tx = {
  id: number; account_id: number; date: string; processed: string | null; amount: string;
  description: string; counterparty: string; merchant: string; type: string; category: string;
  note: string; status: string; decided_by: string;
};
export type Suggestion = {
  id: number; transaction_id: number; type: string; category: string; confidence: number;
  explanation: string; rule_pattern: string; model: string; status: string;
};
export type Category = { id: number; name: string; type: string };
export type Rule = {
  id: number; priority: number; pattern: string; type: string; category: string;
  amount: string | null; weekday: number | null; note: string; enabled: boolean; origin: string;
};
export type Month = {
  month: string; income: string; expense: string; savings: string; wife: string; capital: string;
  other: string; unknown: string; net: string; savings_by_account: Record<string, string>;
};
export type Balance = Month & { start: string; end: string; shift: string };
export type Import = {
  id: number; filename: string; bank: string; account_id: number; period_start: string | null;
  period_end: string | null; opening_balance: string | null; closing_balance: string | null;
  stated_income: string | null; stated_expense: string | null; parsed_income: string;
  parsed_expense: string; reconciled: boolean; ops_total: number; ops_new: number; uploaded_by: string;
};
export type User = { id: number; username: string; display_name: string };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const r = await fetch(path, { credentials: "same-origin", ...init, headers: { ...headers, ...init.headers } });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not json */ }
    if (r.status === 401 && !path.startsWith("/api/auth/")) window.dispatchEvent(new Event("unauthorized"));
    throw new ApiError(r.status, typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json() as Promise<T>;
}

export const post = <T,>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

const fmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
export const rub = (v: string | number | null | undefined) => (v == null ? "—" : `${fmt.format(Number(v))} ₽`);
export const TYPES: Record<string, string> = {
  expense: "трата", income: "доход", refund: "возврат", internal: "внутренний", savings: "отложили",
  capital: "разовое", "?": "не ясно",
};
export const monthName = (m: string) =>
  new Date(`${m}-01`).toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
