import { DAYS } from "@callverse/shared";

const STEPS = ["var(--seq-100)", "var(--seq-250)", "var(--seq-400)", "var(--seq-550)", "var(--seq-700)"];

/** Day x hour grid of a staffing plan (sequential one-hue ramp, value printed in each cell). */
export function StaffingHeatmap({
  rows,
  value,
  open = [8, 22],
  highlight,
}: {
  rows: { day: number; hour: number; [key: string]: number }[];
  value: (row: any) => number;
  open?: number[];
  highlight?: (row: any) => boolean;
}) {
  const hours = Array.from({ length: open[1] - open[0] }, (_, i) => open[0] + i);
  const days = Array.from(new Set(rows.map((r) => r.day))).sort((a, b) => a - b);
  const max = Math.max(1, ...rows.filter((r) => r.hour >= open[0] && r.hour < open[1]).map(value));
  const cell = (day: number, hour: number) => rows.find((r) => r.day === day && r.hour === hour);
  return (
    <div className="overflow-x-auto">
      <table className="border-separate" style={{ borderSpacing: 2 }}>
        <thead>
          <tr>
            <th />
            {hours.map((h) => (
              <th key={h} className="px-0.5 text-[10px] font-normal text-muted">
                {h}h
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days.map((day) => (
            <tr key={day}>
              <td className="pr-2 text-xs text-muted">{DAYS[day % 7]}</td>
              {hours.map((hour) => {
                const row = cell(day, hour);
                const v = row ? value(row) : 0;
                const step = Math.min(STEPS.length - 1, Math.floor((v / max) * (STEPS.length - 1) + 0.0001));
                return (
                  <td
                    key={hour}
                    title={row ? `${DAYS[day % 7]} ${hour}:00 · ${v}` : ""}
                    className="h-7 w-8 rounded text-center text-[11px] tabular"
                    style={{
                      background: v ? STEPS[step] : "var(--surface-2)",
                      color: v ? `var(--seq-ink-${step})` : "var(--text-primary)",
                      outline: row && highlight?.(row) ? "2px solid var(--critical)" : undefined,
                      outlineOffset: -2,
                    }}
                  >
                    {v || ""}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
