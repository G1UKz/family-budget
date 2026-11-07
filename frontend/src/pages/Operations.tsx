import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import CategorySelect from "../components/CategorySelect";
import { api, put, rub, TYPES, type Category, type Tx } from "../api";

export default function Operations() {
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<{ total: number; items: Tx[] }>({ total: 0, items: [] });
  const [cats, setCats] = useState<Category[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const q = params.get("q") ?? "", month = params.get("month") ?? "", category = params.get("category") ?? "";

  const load = () => {
    const p = new URLSearchParams({ limit: "500" });
    if (q) p.set("q", q);
    if (month) p.set("month", month);
    if (category) p.set("category", category);
    api<{ total: number; items: Tx[] }>(`/api/transactions?${p}`).then(setData);
  };
  useEffect(load, [q, month, category]);
  useEffect(() => { api<Category[]>("/api/categories").then(setCats); }, []);

  const set = (k: string, v: string) => { const p = new URLSearchParams(params); v ? p.set(k, v) : p.delete(k); setParams(p); };
  const total = data.items.reduce((s, t) => s + Number(t.amount), 0);

  return (
    <>
      <div className="row filters">
        <input placeholder="Поиск: магазин, категория, заметка" value={q} onChange={(e) => set("q", e.target.value)} />
        <input type="month" value={month} onChange={(e) => set("month", e.target.value)} />
        {category && <button className="chip" onClick={() => set("category", "")}>{category} ✕</button>}
      </div>
      <p className="muted">Найдено {data.total}, сумма {rub(total)}</p>
      <div className="scroll">
        <table>
          <thead><tr><th>Дата</th><th>Где / что</th><th>Категория</th><th className="num">Сумма</th></tr></thead>
          <tbody>
            {data.items.map((t) => (
              <tr key={t.id} className={t.status === "review" ? "warn" : ""}>
                <td className="nowrap">{t.date.split("-").reverse().join(".")}</td>
                <td><div>{t.merchant}</div>{t.note && <div className="muted small">{t.note}</div>}</td>
                <td onClick={() => setEditing(t.id)}>
                  {editing === t.id ? (
                    <CategorySelect cats={cats} value={t.category} onChange={(name, type) =>
                      put(`/api/transactions/${t.id}`, { type, category: name }).then(() => { setEditing(null); load(); })} />
                  ) : (
                    <span className="editable">{t.category || "?"} <span className="muted small">{TYPES[t.type]}</span></span>
                  )}
                </td>
                <td className={`num ${Number(t.amount) > 0 ? "pos" : ""}`}>{rub(t.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
