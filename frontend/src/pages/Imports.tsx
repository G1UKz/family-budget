import { useEffect, useState } from "react";
import { api, rub, type Import } from "../api";

export default function Imports() {
  const [list, setList] = useState<Import[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api<Import[]>("/api/imports").then(setList);
  useEffect(() => { load(); }, []);
  const upload = (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true); setMsg("");
    api<Import>("/api/imports", { method: "POST", body: fd })
      .then((r) => { setMsg(`${r.filename}: новых операций ${r.ops_new} из ${r.ops_total}, сверка ${r.reconciled ? "сошлась ✓" : "НЕ сошлась"}`); load(); })
      .catch((e) => setMsg(`Ошибка: ${e.message}`))
      .finally(() => setBusy(false));
  };
  return (
    <>
      <section className="card">
        <h3>Загрузить выписку</h3>
        <p className="muted small">PDF из приложения банка (сейчас поддерживается ВТБ). Повторная загрузка того же файла и пересекающиеся периоды не создают дублей.</p>
        <input type="file" accept="application/pdf" disabled={busy} onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        {msg && <p>{msg}</p>}
      </section>
      <div className="scroll">
        <table>
          <thead><tr><th>Файл</th><th>Период</th><th className="num">Поступления</th><th className="num">Расходы</th><th className="num">Остаток</th><th>Сверка</th></tr></thead>
          <tbody>
            {list.map((i) => (
              <tr key={i.id}>
                <td>{i.filename}<div className="muted small">{i.bank} · {i.uploaded_by} · {i.ops_new}/{i.ops_total}</div></td>
                <td className="nowrap">{i.period_start} — {i.period_end}</td>
                <td className="num">{rub(i.parsed_income)}{i.stated_income !== i.parsed_income && <div className="neg small">банк {rub(i.stated_income)}</div>}</td>
                <td className="num">{rub(i.parsed_expense)}{i.stated_expense !== i.parsed_expense && <div className="neg small">банк {rub(i.stated_expense)}</div>}</td>
                <td className="num">{rub(i.closing_balance)}</td>
                <td>{i.reconciled ? <span className="pos">✓</span> : <span className="neg">✗</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
