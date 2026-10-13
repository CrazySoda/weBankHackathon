import { useMemo, useState } from "react";
import type { CashProjectionState } from "../api";
import { formatMoney } from "../api";
import { compactMoney } from "../ui";

/**
 * Hand-rolled SVG line chart of the daily cash balance (91 days).
 * Single series, so no legend box — the title names it. Below-zero days are
 * shaded as a status annotation (red) and carried again in the legend key.
 * Includes a crosshair + tooltip hover layer.
 */

const W = 860;
const H = 320;
const M = { top: 16, right: 20, bottom: 34, left: 76 };

const LINE = "#3987e5"; // validated series color on the dark surface
const STATUS_RED = "#e66767";
const GRID = "#1c2534";
const TEXT_DIM = "#94a3b8";
const SURFACE = "#141b24";

export default function CashChart({ projection }: { projection: CashProjectionState }) {
  const [hover, setHover] = useState<number | null>(null);

  const { xs, ys, yMin, yMax, ticks } = useMemo(() => {
    const data = projection.daily_balance_minor;
    const innerW = W - M.left - M.right;
    const innerH = H - M.top - M.bottom;
    const n = data.length;
    const xs = data.map((_, i) => M.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW));
    const rawMin = Math.min(0, ...data);
    const rawMax = Math.max(0, ...data);
    const pad = (rawMax - rawMin || 1) * 0.08;
    const yMin = rawMin - pad;
    const yMax = rawMax + pad;
    const ys = data.map(
      (v) => M.top + innerH - ((v - yMin) / (yMax - yMin)) * innerH,
    );
    // clean ticks: 4 evenly spaced values rounded to nice numbers
    const step = niceStep((yMax - yMin) / 4);
    const first = Math.ceil(yMin / step) * step;
    const tk: number[] = [];
    for (let v = first; v <= yMax; v += step) tk.push(v);
    return { xs, ys, yMin, yMax, ticks: tk };
  }, [projection]);

  const data = projection.daily_balance_minor;
  const innerW = W - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  const xOf = (day: number) => xs[Math.max(0, Math.min(data.length - 1, day))];
  const yOf = (v: number) => M.top + innerH - ((v - yMin) / (yMax - yMin)) * innerH;

  const linePath = data
    .map((_, i) => `${i === 0 ? "M" : "L"}${xs[i].toFixed(2)},${ys[i].toFixed(2)}`)
    .join(" ");

  const zeroY = yOf(0);

  // red shading spans the region where balance is below zero (status, not series)
  const belowRegions: Array<[number, number]> = [];
  let start: number | null = null;
  data.forEach((v, i) => {
    if (v < 0 && start === null) start = i;
    if (v >= 0 && start !== null) {
      belowRegions.push([start, i]);
      start = null;
    }
  });
  if (start !== null) belowRegions.push([start, data.length - 1]);

  const minPt = { x: xOf(projection.min_balance_day), y: yOf(projection.min_balance_minor) };

  const hoverDay = hover;
  const hoverVal = hoverDay !== null ? data[hoverDay] : null;

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    if (px < M.left || px > W - M.right) {
      setHover(null);
      return;
    }
    const frac = (px - M.left) / innerW;
    setHover(Math.round(frac * (data.length - 1)));
  }

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height: "auto", display: "block" }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label={`Daily cash balance over ${data.length} days; minimum ${formatMoney(
          projection.min_balance_minor,
          projection.currency,
        )} on day ${projection.min_balance_day}`}
      >
        {/* below-zero status shading */}
        {belowRegions.map(([a, b], i) => (
          <rect
            key={i}
            x={xOf(a) - (a === 0 ? 0 : 1)}
            y={M.top}
            width={Math.max(xOf(b) - xOf(a), 1)}
            height={innerH}
            fill={STATUS_RED}
            opacity={0.09}
          />
        ))}

        {/* gridlines + y ticks (hairline, solid, recessive) */}
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.left} x2={W - M.right} y1={yOf(t)} y2={yOf(t)} stroke={GRID} strokeWidth={1} />
            <text
              x={M.left - 8}
              y={yOf(t) + 3.5}
              textAnchor="end"
              fill={TEXT_DIM}
              fontSize={11}
              fontFamily="var(--mono)"
            >
              {compactMoney(t, projection.currency === "USD" ? "$" : "")}
            </text>
          </g>
        ))}

        {/* zero line (slightly stronger than grid) */}
        <line x1={M.left} x2={W - M.right} y1={zeroY} y2={zeroY} stroke={TEXT_DIM} strokeWidth={1} opacity={0.55} />

        {/* x ticks: days */}
        {xTickDays(data.length).map((d) => (
          <text
            key={d}
            x={xOf(d)}
            y={H - M.bottom + 18}
            textAnchor="middle"
            fill={TEXT_DIM}
            fontSize={11}
            fontFamily="var(--mono)"
          >
            {`d${d}`}
          </text>
        ))}

        {/* the series: 2px, round joins */}
        <path d={linePath} fill="none" stroke={LINE} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {/* min-balance marker: >=8px dot with 2px surface ring + direct label */}
        <circle cx={minPt.x} cy={minPt.y} r={6} fill={SURFACE} />
        <circle cx={minPt.x} cy={minPt.y} r={4.5} fill={projection.min_balance_minor < 0 ? STATUS_RED : LINE} />
        <text
          x={Math.min(minPt.x + 10, W - M.right - 4)}
          y={Math.max(minPt.y - 10, M.top + 12)}
          textAnchor={minPt.x > W * 0.8 ? "end" : "start"}
          fill={TEXT_DIM}
          fontSize={11}
          fontFamily="var(--mono)"
        >
          {`min ${formatMoney(projection.min_balance_minor, projection.currency)} (d${projection.min_balance_day})`}
        </text>

        {/* hover crosshair + marker */}
        {hoverDay !== null && hoverVal !== null && (
          <g>
            <line x1={xOf(hoverDay)} x2={xOf(hoverDay)} y1={M.top} y2={H - M.bottom} stroke={TEXT_DIM} strokeWidth={1} opacity={0.35} />
            <circle cx={xOf(hoverDay)} cy={yOf(hoverVal)} r={6} fill={SURFACE} />
            <circle cx={xOf(hoverDay)} cy={yOf(hoverVal)} r={4} fill={LINE} />
          </g>
        )}
      </svg>

      {/* tooltip */}
      <div style={{ minHeight: 22, marginTop: 6 }} className="mono muted">
        {hoverDay !== null && hoverVal !== null ? (
          <span>
            day {hoverDay}:{" "}
            <span style={{ color: hoverVal < 0 ? STATUS_RED : undefined }}>
              {formatMoney(hoverVal, projection.currency)}
            </span>
          </span>
        ) : (
          <span className="faint">{data.length} days · hover for daily balance</span>
        )}
      </div>

      <div className="chart-legend">
        <span className="key">
          <span className="swatch" style={{ background: LINE }} />
          daily balance
        </span>
        <span className="key">
          <span className="swatch" style={{ background: STATUS_RED }} />
          below zero ({projection.days_below_zero} {projection.days_below_zero === 1 ? "day" : "days"})
        </span>
      </div>
    </div>
  );
}

function xTickDays(n: number): number[] {
  const out: number[] = [];
  const step = Math.max(1, Math.round(n / 8));
  for (let d = 0; d < n; d += step) out.push(d);
  return out;
}

function niceStep(raw: number): number {
  const mag = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1))));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (raw <= m * mag) return m * mag;
  }
  return 10 * mag;
}
