import type { Category } from "../api";

export default function CategorySelect({ cats, value, onChange }: {
  cats: Category[]; value: string; onChange: (name: string, type: string) => void;
}) {
  const groups = Object.entries(
    cats.reduce<Record<string, Category[]>>((acc, c) => ((acc[c.type] ??= []).push(c), acc), {}),
  );
  return (
    <select value={value} onChange={(e) => {
      const c = cats.find((x) => x.name === e.target.value);
      onChange(e.target.value, c?.type ?? "?");
    }}>
      <option value="">— категория —</option>
      {groups.map(([t, cs]) => (
        <optgroup key={t} label={t}>
          {cs.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
        </optgroup>
      ))}
    </select>
  );
}
