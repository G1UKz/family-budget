import { useEffect, useState } from "react";
import CategorySelect from "../components/CategorySelect";
import { api, del, post, put, TYPES, type Category, type Rule } from "../api";

const empty = { priority: 100, pattern: "", type: "expense", category: "", amount: null, weekday: null, note: "", enabled: true };

export default function Rules() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [draft, setDraft] = useState<Omit<Rule, "id" | "origin"> & { id?: number }>(empty);
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState("");
  const load = () => api<Rule[]>("/api/rules").then(setRules);
  useEffect(() => { load(); api<Category[]>("/api/categories").then(setCats); }, []);

  const save = () => {
    const req = draft.id ? put(`/api/rules/${draft.id}`, draft) : post("/api/rules", draft);
    req.then(() => { setDraft(empty); setMsg(""); load(); }).catch((e) => setMsg(e.message));
  };
  const apply = () => post<{ checked: number; changed: number }>("/api/rules/apply")
    .then((r) => setMsg(`Проверено ${r.checked}, изменено ${r.changed}`));
  const shown = rules.filter((r) => !q || `${r.pattern} ${r.category}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <section className="card">
        <h3>{draft.id ? `Правило #${draft.id}` : "Новое правило"}</h3>
        <div className="row gap wrap">
          <input className="grow" placeholder="Регулярка по «описание | контрагент»" value={draft.pattern} onChange={(e) => setDraft({ ...draft, pattern: e.target.value })} />
          <CategorySelect cats={cats} value={draft.category} onChange={(category, type) => setDraft({ ...draft, category, type })} />
          <input style={{ width: 90 }} type="number" placeholder="сумма" value={draft.amount ?? ""} onChange={(e) => setDraft({ ...draft, amount: e.target.value || null })} />
          <input style={{ width: 70 }} type="number" placeholder="приор." value={draft.priority} onChange={(e) => setDraft({ ...draft, priority: Number(e.target.value) })} />
          <button className="primary" disabled={!draft.pattern || !draft.category} onClick={save}>Сохранить</button>
          {draft.id && <button className="link" onClick={() => setDraft(empty)}>Отмена</button>}
        </div>
        {msg && <p className="muted">{msg}</p>}
      </section>
      <div className="row">
        <input placeholder="Фильтр" value={q} onChange={(e) => setQ(e.target.value)} />
        <button onClick={apply}>Применить правила к операциям</button>
      </div>
      <div className="scroll">
        <table>
          <thead><tr><th className="num">#</th><th>Шаблон</th><th>Категория</th><th>Условия</th><th /></tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className={r.enabled ? "" : "muted"}>
                <td className="num">{r.priority}</td>
                <td><code>{r.pattern}</code>{r.origin !== "import" && <span className="chip small">{r.origin}</span>}</td>
                <td>{r.category || "?"} <span className="muted small">{TYPES[r.type]}</span></td>
                <td className="small">{r.amount && `= ${r.amount} ₽`} {r.weekday && `день ${r.weekday}`}</td>
                <td className="nowrap">
                  <button className="link" onClick={() => setDraft(r)}>изм.</button>
                  <button className="link" onClick={() => confirm("Удалить правило?") && del(`/api/rules/${r.id}`).then(load)}>✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
