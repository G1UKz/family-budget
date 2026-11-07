import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, monthName, rub, type Balance, type Month } from "../api";

type Cat = { category: string; amount: string; count: number };
type Summary = { last: Month | null; prev: Month | null; review_count: number };

function Tile({ label, value, prev, invert }: { label: string; value?: string; prev?: string; invert?: boolean }) {
  const d = value != null && prev != null ? Number(value) - Number(prev) : null;
  const good = d != null && (invert ? d < 0 : d > 0);
  return (
    <div className="tile">
      <div className="muted">{label}</div>
      <div className="big">{rub(value)}</div>
      {d != null && <div className={good ? "pos" : "neg"}>{d > 0 ? "+" : ""}{rub(d)} к прошлому</div>}
    </div>
  );
}

export default function Dashboard() {
  const [sum, setSum] = useState<Summary>();
  const [months, setMonths] = useState<Month[]>([]);
  const [month, setMonth] = useState<string>();
  const [cats, setCats] = useState<Cat[]>([]);
  const [bal, setBal] = useState<Balance[]>([]);
  const nav = useNavigate();

  useEffect(() => {
    api<Summary>("/api/reports/summary").then((s) => { setSum(s); setMonth(s.last?.month); });
    api<Month[]>("/api/reports/months").then(setMonths);
    api<Balance[]>("/api/reports/balances").then(setBal);
  }, []);
  useEffect(() => {
    if (month) api<Cat[]>(`/api/reports/categories?month=${month}`).then(setCats);
  }, [month]);

  const last = sum?.last, prev = sum?.prev;
  const max = Math.max(1, ...cats.map((c) => Number(c.amount)));
  const chart = months.map((m) => ({ month: m.month.slice(2), Доходы: +m.income, Траты: +m.expense, Отложили: +m.savings }));

  return (
    <>
      {sum && sum.review_count > 0 && (
        <div className="banner" onClick={() => nav("/review")}>Ждут разбора: {sum.review_count} операций →</div>
      )}
      <h2>{last ? monthName(last.month) : "Нет данных"}</h2>
      <div className="tiles">
        <Tile label="Доходы" value={last?.income} prev={prev?.income} />
        <Tile label="Траты" value={last?.expense} prev={prev?.expense} invert />
        <Tile label="Отложили" value={last?.savings} prev={prev?.savings} />
        <Tile label="Доходы − траты" value={last?.net} prev={prev?.net} />
      </div>

      <section className="card">
        <h3>По месяцам</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chart}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="month" />
            <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}к`} width={44} />
            <Tooltip formatter={(v: number) => rub(v)} />
            <Legend />
            <Bar dataKey="Доходы" fill="#2e7d5b" />
            <Bar dataKey="Траты" fill="#c0563f" />
            <Bar dataKey="Отложили" fill="#4a6fa5" />
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="card">
        <div className="row">
          <h3>Категории</h3>
          <select value={month} onChange={(e) => setMonth(e.target.value)}>
            {months.map((m) => <option key={m.month} value={m.month}>{monthName(m.month)}</option>)}
          </select>
        </div>
        {cats.map((c) => (
          <div key={c.category} className="catrow" onClick={() => nav(`/ops?month=${month}&category=${encodeURIComponent(c.category)}`)}>
            <span>{c.category} <span className="muted">· {c.count}</span></span>
            <span className="bar"><span style={{ width: `${(Number(c.amount) / max) * 100}%` }} /></span>
            <span className="num">{rub(c.amount)}</span>
          </div>
        ))}
      </section>

      <section className="card">
        <h3>Сверка с остатком на счетах</h3>
        <div className="scroll">
          <table>
            <thead><tr>
              <th>Месяц</th><th className="num">Начало</th><th className="num">Доходы</th><th className="num">Траты</th>
              <th className="num">Отложили</th><th className="num">Жене</th><th className="num">Разовые</th>
              <th className="num">Сдвиг дат</th><th className="num">Конец</th>
            </tr></thead>
            <tbody>
              {bal.map((b) => (
                <tr key={b.month}>
                  <td>{b.month}</td><td className="num">{rub(b.start)}</td><td className="num">{rub(b.income)}</td>
                  <td className="num">−{rub(b.expense)}</td><td className="num">−{rub(b.savings)}</td>
                  <td className="num">−{rub(b.wife)}</td><td className="num">{rub(b.capital)}</td>
                  <td className="num">{rub(Number(b.shift) + Number(b.other))}</td><td className="num"><b>{rub(b.end)}</b></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">Конец месяца — фактический остаток основного и мастер-счёта по выпискам. «Сдвиг дат» — операции, проведённые банком в другом месяце, и переводы между своими счетами.</p>
      </section>
    </>
  );
}
