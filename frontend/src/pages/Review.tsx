import { useEffect, useState } from "react";
import CategorySelect from "../components/CategorySelect";
import { api, post, put, rub, type Category, type Suggestion, type Tx } from "../api";

type Item = { tx: Tx; suggestion: Suggestion | null };

function Card({ item, cats, reload }: { item: Item; cats: Category[]; reload: () => void }) {
  const { tx, suggestion: s } = item;
  const [pick, setPick] = useState<{ name: string; type: string }>({ name: "", type: "" });
  const [makeRule, setMakeRule] = useState(false);
  const [pattern, setPattern] = useState("");
  return (
    <div className="card review">
      <div className="row">
        <b>{tx.merchant}</b>
        <span className={`num ${Number(tx.amount) > 0 ? "pos" : ""}`}>{rub(tx.amount)}</span>
      </div>
      <div className="muted small">{tx.date.split("-").reverse().join(".")} · {tx.description}{tx.counterparty && ` · ${tx.counterparty}`}</div>
      {s && (
        <div className="suggestion">
          <div>🤖 <b>{s.category || "не ясно"}</b> <span className="muted small">уверенность {Math.round(s.confidence * 100)}%</span></div>
          <div className="small">{s.explanation}</div>
          {s.rule_pattern && <div className="muted small">правило: <code>{s.rule_pattern}</code></div>}
          <div className="row gap">
            {s.category && <button className="primary" onClick={() => post(`/api/review/${s.id}/accept`).then(reload)}>Да</button>}
            {s.category && s.rule_pattern && (
              <button onClick={() => post(`/api/review/${s.id}/accept?make_rule=true`).then(reload)}>Да + правило</button>
            )}
            <button className="link" onClick={() => post(`/api/review/${s.id}/reject`).then(reload)}>Нет</button>
          </div>
        </div>
      )}
      <div className="row gap wrap">
        <CategorySelect cats={cats} value={pick.name} onChange={(name, type) => setPick({ name, type })} />
        <label className="small"><input type="checkbox" checked={makeRule} onChange={(e) => setMakeRule(e.target.checked)} /> запомнить правилом</label>
        {makeRule && <input className="small" placeholder={`регулярка (по умолчанию «${tx.merchant}»)`} value={pattern} onChange={(e) => setPattern(e.target.value)} />}
        <button disabled={!pick.name} onClick={() =>
          put(`/api/transactions/${tx.id}`, { type: pick.type, category: pick.name, make_rule: makeRule, rule_pattern: pattern || null }).then(reload)}>
          Сохранить
        </button>
      </div>
    </div>
  );
}

export default function Review() {
  const [items, setItems] = useState<Item[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const load = () => api<Item[]>("/api/review").then(setItems);
  useEffect(() => { load(); api<Category[]>("/api/categories").then(setCats); }, []);
  const ask = () => {
    setBusy(true); setMsg("");
    post<{ created: number }>("/api/review/suggest")
      .then((r) => { setMsg(`Подсказок: ${r.created}`); load(); })
      .catch((e) => setMsg(e.message))
      .finally(() => setBusy(false));
  };
  return (
    <>
      <div className="row">
        <h2>Разбор: {items.length}</h2>
        <button disabled={busy || !items.some((i) => !i.suggestion)} onClick={ask}>{busy ? "Думаю…" : "Подсказать с AI"}</button>
      </div>
      {msg && <p className="muted">{msg}</p>}
      {items.length === 0 && <p className="muted">Всё разобрано 🎉</p>}
      {items.map((i) => <Card key={i.tx.id} item={i} cats={cats} reload={load} />)}
    </>
  );
}
