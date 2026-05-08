import { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
  LabelList,
} from "recharts";
import { CHART } from "../chartColors";

// v2 cache key — invalidates the older 0/1/3/5/10 saved value so the new
// 0/1/3/5/7/9 bucketing takes effect for existing users.
const STORAGE_KEY = "uplift-distribution-edges-v2";
const DEFAULT_EDGES = [0, 1, 3, 5, 7, 9];

// Bar colors graduate from "warning" (sub-1.0x uplift = AI slower than alone)
// through neutral mid-range to a deeper good-zone for high-uplift sessions.
function colorForBucket(lo: number, hi: number | undefined): string {
  if (hi === 1 && lo === 0) return CHART.brick;        // 0–1x: AI made it slower
  if (hi === undefined) return CHART.sage;             // open-ended top bucket
  if (lo >= 7) return CHART.sage;                      // 7–9x
  if (lo >= 5) return CHART.dusk;                      // 5–7x
  if (lo >= 3) return CHART.steel;                     // 3–5x
  return CHART.ochre;                                  // 1–3x (mild positive)
}

function loadEdges(): number[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length >= 2 && parsed.every((n: unknown) => typeof n === "number")) {
        return parsed;
      }
    }
  } catch {}
  return DEFAULT_EDGES;
}

function saveEdges(edges: number[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(edges));
}

interface Bucket {
  label: string;
  count: number;
  color: string;
}

function buildBuckets(values: number[], edges: number[]): Bucket[] {
  const sorted = [...new Set([...edges].sort((a, b) => a - b))];
  const buckets: Bucket[] = [];

  for (let i = 0; i < sorted.length; i++) {
    const lo = sorted[i];
    const hi = sorted[i + 1];
    if (hi !== undefined) {
      const count = values.filter((v) => v >= lo && v < hi).length;
      buckets.push({ label: `${lo}–${hi}x`, count, color: colorForBucket(lo, hi) });
    } else {
      const count = values.filter((v) => v >= lo).length;
      buckets.push({ label: `${lo}x+`, count, color: colorForBucket(lo, undefined) });
    }
  }

  return buckets;
}

interface Props {
  values: number[];
  failCount: number;
  stats: { avg: number; median: number };
}

export default function UpliftDistributionChart({ values, failCount, stats }: Props) {
  const [edges, setEdges] = useState(loadEdges);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const buckets = buildBuckets(values, edges);

  const startEditing = () => {
    setDraft(edges.join(", "));
    setEditing(true);
  };

  const applyEdges = () => {
    const parsed = draft
      .split(/[,\s]+/)
      .map(Number)
      .filter((n) => !isNaN(n))
      .sort((a, b) => a - b);
    if (parsed.length >= 2) {
      // deduplicate
      const unique = [...new Set(parsed)];
      setEdges(unique);
      saveEdges(unique);
    }
    setEditing(false);
  };

  const resetEdges = () => {
    setEdges(DEFAULT_EDGES);
    saveEdges(DEFAULT_EDGES);
    setEditing(false);
  };

  return (
    <div className="chart-card">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <h3 style={{ margin: 0 }}>Uplift Distribution</h3>
        {!editing && (
          <button
            onClick={startEditing}
            style={{
              background: "none",
              border: "none",
              color: "var(--text-muted)",
              fontSize: 11,
              cursor: "pointer",
              textDecoration: "underline",
              padding: 0,
            }}
          >
            Edit buckets
          </button>
        )}
      </div>
      {editing && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>Edges:</span>
          <input
            className="search-input"
            style={{ flex: 1, fontSize: 12, padding: "3px 6px" }}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applyEdges()}
            placeholder="e.g. 0, 1, 3, 5, 10"
          />
          <button className="btn" style={{ fontSize: 11, padding: "3px 8px" }} onClick={applyEdges}>
            Apply
          </button>
          <button className="btn btn-secondary" style={{ fontSize: 11, padding: "3px 8px" }} onClick={resetEdges}>
            Reset
          </button>
        </div>
      )}
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={buckets} margin={{ top: 18, right: 12, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: CHART.axis, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: CHART.grid }}
          />
          <YAxis
            tick={{ fill: CHART.axis, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(0,0,0,0.03)" }}
            contentStyle={{
              background: "var(--bg-card)",
              border: `1px solid ${CHART.grid}`,
              borderRadius: 6,
              fontSize: 12,
            }}
            formatter={(v: number) => [v, "Sessions"]}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            <LabelList
              dataKey="count"
              position="top"
              style={{ fill: CHART.axis, fontSize: 11 }}
              formatter={(v: number) => (v > 0 ? v : "")}
            />
            {buckets.map((b, i) => (
              <Cell key={i} fill={b.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
        <span>Avg: {stats.avg}x · Median: {stats.median}x · {values.length} sessions</span>
        {failCount > 0 && (
          <span style={{ color: CHART.brick }}>
            {failCount}/{values.length + failCount} failed
          </span>
        )}
      </div>
    </div>
  );
}
