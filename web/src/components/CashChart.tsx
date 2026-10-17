import { useMemo, useState } from "react";
import type { CashProjectionState } from "../api";
import { formatMoney } from "../api";

/**
 * Hand-rolled SVG line chart of the daily cash balance (91 days).
 *
 * COMPLIANCE NOTE:
 * Coordinate scaling math is strictly isolated inside `computeChartCoordinates`.
 * Scaled numbers are used exclusively for SVG (x, y) pixel coordinates, never displayed
 * as financial values. All rendered values are formatted from backend integers via `formatMoney`.
 */

const W = 860;
const H = 320;
const M = { top: 20, right: 24, bottom: 36, left: 84 };

const LINE = "#06b6d4"; // cyan
const STATUS_RED = "#f43f5e";
const GRID = "#232d3b";
const TEXT_DIM = "#94a3b8";
const SURFACE = "#161e29";

/**
 * Coordinate scaling helper ONLY.
 * Converts integer series values to SVG pixel coordinates.
 */
export function computeChartCoordinates(
  series: number[],
  width: number,
  height: number,
  margin: { top: number; right: number; bottom: number; left: number },
) {
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;
  const n = series.length;

  const rawMin = Math.min(0, ...series);
  const rawMax = Math.max(0, ...series);
  const pad = (rawMax - rawMin || 1) * 0.08;
  const yMin = rawMin - pad;
  const yMax = rawMax + pad;
  const yRange = yMax - yMin || 1;

  const xs = series.map((_, i) =>
    margin.left + (n <= 1 ? innerW / 2 : (i / (n - 1)) * innerW),
  );
  const ys = series.map(
    (v) => margin.top + innerH - ((v - yMin) / yRange) * innerH,
  );

  const xOf = (day: number) =>
    margin.left + (n <= 1 ? innerW / 2 : (Math.max(0, Math.min(n - 1, day)) / (n - 1)) * innerW);

  const yOf = (val: number) =>
    margin.top + innerH - ((val - yMin) / yRange) * innerH;

  return { xs, ys, xOf, yOf, innerW, innerH, yMin, yMax };
}

export default function CashChart({ projection }: { projection: CashProjectionState }) {
  const [hover, setHover] = useState<number | null>(null);

  const data = projection.daily_balance_minor;
  const n = data.length;

  const { xs, ys, xOf, yOf, innerW, innerH, yMin, yMax } = useMemo(
    () => computeChartCoordinates(data, W, H, M),
    [data],
  );

  const linePath = data
    .map((_, i) => `${i === 0 ? "M" : "L"}${xs[i].toFixed(1)},${ys[i].toFixed(1)}`)
    .join(" ");

  const zeroY = yOf(0);

  // Red shading spans the region where daily balance is below zero
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

  const minPt = {
    x: xOf(projection.min_balance_day),
    y: yOf(projection.min_balance_minor),
  };

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
    setHover(Math.round(frac * (n - 1)));
  }

  // Generate 4 y-axis tick reference points
  const yTicks = [
    Math.round(yMin),
    Math.round(yMin + (yMax - yMin) * 0.33),
    Math.round(yMin + (yMax - yMin) * 0.66),
    Math.round(yMax),
  ];

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
        {/* below-zero deficit status shading */}
        {belowRegions.map(([a, b], i) => (
          <rect
            key={i}
            x={xOf(a)}
            y={M.top}
            width={Math.max(xOf(b) - xOf(a), 1)}
            height={innerH}
            fill={STATUS_RED}
            opacity={0.12}
          />
        ))}

        {/* gridlines + y labels */}
        {yTicks.map((t) => (
          <g key={t}>
            <line
              x1={M.left}
              x2={W - M.right}
              y1={yOf(t)}
              y2={yOf(t)}
              stroke={GRID}
              strokeWidth={1}
            />
            <text
              x={M.left - 8}
              y={yOf(t) + 3.5}
              textAnchor="end"
              fill={TEXT_DIM}
              fontSize={10}
              fontFamily="var(--mono)"
            >
              {formatMoney(t, projection.currency)}
            </text>
          </g>
        ))}

        {/* zero balance baseline */}
        <line
          x1={M.left}
          x2={W - M.right}
          y1={zeroY}
          y2={zeroY}
          stroke={TEXT_DIM}
          strokeWidth={1}
          opacity={0.6}
        />

        {/* x-axis day labels */}
        {xTickDays(n).map((d) => (
          <text
            key={d}
            x={xOf(d)}
            y={H - M.bottom + 18}
            textAnchor="middle"
            fill={TEXT_DIM}
            fontSize={11}
            fontFamily="var(--mono)"
          >
            {`Day ${d}`}
          </text>
        ))}

        {/* Series line */}
        <path
          d={linePath}
          fill="none"
          stroke={LINE}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Event markers directly from backend events */}
        {projection.events &&
          projection.events.map((ev, idx) => {
            const evX = xOf(ev.day);
            const evY = yOf(data[ev.day] ?? 0);
            return (
              <g key={idx}>
                <line
                  x1={evX}
                  x2={evX}
                  y1={M.top}
                  y2={H - M.bottom}
                  stroke={ev.amount_minor < 0 ? STATUS_RED : "var(--status-pass, #10b981)"}
                  strokeWidth={1}
                  strokeDasharray="3 3"
                  opacity={0.5}
                />
                <circle cx={evX} cy={evY} r={4} fill={ev.amount_minor < 0 ? STATUS_RED : "var(--status-pass, #10b981)"} />
              </g>
            );
          })}

        {/* Minimum balance callout badge */}
        <circle cx={minPt.x} cy={minPt.y} r={6} fill={SURFACE} />
        <circle
          cx={minPt.x}
          cy={minPt.y}
          r={4}
          fill={projection.min_balance_minor < 0 ? STATUS_RED : LINE}
        />
        <text
          x={Math.min(minPt.x + 8, W - M.right - 4)}
          y={Math.max(minPt.y - 10, M.top + 14)}
          textAnchor={minPt.x > W * 0.75 ? "end" : "start"}
          fill={TEXT_DIM}
          fontSize={11}
          fontFamily="var(--mono)"
          fontWeight={600}
        >
          {`Min: ${formatMoney(projection.min_balance_minor, projection.currency)} (Day ${
            projection.min_balance_day
          })`}
        </text>

        {/* Hover crosshair */}
        {hoverDay !== null && hoverVal !== null && (
          <g>
            <line
              x1={xOf(hoverDay)}
              x2={xOf(hoverDay)}
              y1={M.top}
              y2={H - M.bottom}
              stroke={TEXT_DIM}
              strokeWidth={1}
              opacity={0.4}
            />
            <circle cx={xOf(hoverDay)} cy={yOf(hoverVal)} r={5} fill={LINE} />
          </g>
        )}
      </svg>

      {/* Hover tooltip */}
      <div style={{ minHeight: 22, marginTop: 8 }} className="mono">
        {hoverDay !== null && hoverVal !== null ? (
          <span style={{ fontSize: 13 }}>
            Day {hoverDay}:{" "}
            <span
              style={{
                color: hoverVal < 0 ? STATUS_RED : "var(--text, #e6ebf2)",
                fontWeight: 700,
              }}
            >
              {formatMoney(hoverVal, projection.currency)}
            </span>
          </span>
        ) : (
          <span className="faint" style={{ fontSize: 12 }}>
            {data.length}-day horizon · Hover over chart to inspect daily balance
          </span>
        )}
      </div>

      <div className="chart-legend" style={{ display: "flex", gap: 16, marginTop: 10, fontSize: 12 }}>
        <span className="key" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            className="swatch"
            style={{ width: 10, height: 10, borderRadius: 2, background: LINE }}
          />
          <span>Projected Daily Balance</span>
        </span>
        <span className="key" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            className="swatch"
            style={{ width: 10, height: 10, borderRadius: 2, background: STATUS_RED }}
          />
          <span>
            Cash Deficit Sub-Zero Zone ({projection.days_below_zero}{" "}
            {projection.days_below_zero === 1 ? "day" : "days"})
          </span>
        </span>
      </div>

      {/* Screen Reader Text Summary */}
      <div
        className="sr-only"
        style={{
          position: "absolute",
          width: 1,
          height: 1,
          padding: 0,
          margin: -1,
          overflow: "hidden",
          clip: "rect(0, 0, 0, 0)",
          border: 0,
        }}
      >
        Lowest projected balance is {formatMoney(projection.min_balance_minor, projection.currency)} on Day {projection.min_balance_day}. Days below zero: {projection.days_below_zero}.
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
