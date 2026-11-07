import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api, post, type User } from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Operations from "./pages/Operations";
import Review from "./pages/Review";
import Rules from "./pages/Rules";
import Imports from "./pages/Imports";

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api<User>("/api/auth/me").then(setUser).catch(() => setUser(null));
    const onUnauth = () => setUser(null);
    window.addEventListener("unauthorized", onUnauth);
    return () => window.removeEventListener("unauthorized", onUnauth);
  }, []);

  if (user === undefined) return <div className="center muted">Загрузка…</div>;
  if (user === null) return <Login onLogin={setUser} />;

  return (
    <div className="shell">
      <header className="top">
        <span className="brand">Бюджет</span>
        <nav>
          <NavLink to="/" end>Обзор</NavLink>
          <NavLink to="/ops">Операции</NavLink>
          <NavLink to="/review">Разбор</NavLink>
          <NavLink to="/import">Выписки</NavLink>
          <NavLink to="/rules">Правила</NavLink>
        </nav>
        <button className="link" onClick={() => post("/api/auth/logout").then(() => setUser(null))}>
          {user.display_name || user.username} · выйти
        </button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/ops" element={<Operations />} />
          <Route path="/review" element={<Review />} />
          <Route path="/import" element={<Imports />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}
