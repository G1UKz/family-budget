import { useState, type FormEvent } from "react";
import { post, type User } from "../api";

export default function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [f, setF] = useState({ username: "", password: "", code: "" });
  const [err, setErr] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    post<User>("/api/auth/login", f).then(onLogin).catch((e) => setErr(e.status === 429 ? "Слишком много попыток" : "Неверный вход"));
  };
  return (
    <form className="login card" onSubmit={submit}>
      <h1>Семейный бюджет</h1>
      <input placeholder="Логин" autoComplete="username" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} />
      <input placeholder="Пароль" type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
      <input placeholder="Код из приложения" inputMode="numeric" autoComplete="one-time-code" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} />
      <button className="primary">Войти</button>
      {err && <p className="error">{err}</p>}
    </form>
  );
}
