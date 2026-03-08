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
} from "recharts";

const STORAGE_KEY = "uplift-distribution-edges";
const DEFAULT_EDGES = [0, 1, 3, 5, 10];

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
  const sorted = [...edges].sort((a, b) => a - b);
  const buckets: Bucket[] = [];

  for (let i = 0; i < sorted.length; i++) {
    const lo = sorted[i];
    const hi = sorted[i + 1];
    if (hi !== undefined) {
      const count = values.filter((v) => v >= lo && v < hi).length;
      const color = lo === 0 && hi === 1 ? "#dc2626" : "#3b82f6";
      buckets.push({ label: `${lo}-${hi}x`, count, color });
    } else {
      const count = values.filter((v) => v >= lo).length;
      buckets.push({ label: `${lo}x+`, count, color: "#16a34a" });
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
      <ResponsiveContainer width="100%" height={250}>
        <BarChart data={buckets}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
          <XAxis dataKey="label" tick={{ fill: "#666", fontSize: 11 }} />
          <YAxis tick={{ fill: "#666", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: "#fff", border: "1px solid #e0e0e0" }}
            formatter={(v: number) => [v, "Sessions"]}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {buckets.map((b, i) => (
              <Cell key={i} fill={b.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginTop: 8 }}>
        <span>Avg: {stats.avg}x | Median: {stats.median}x | {values.length} sessions</span>
        {failCount > 0 && (
          <span style={{ color: "#dc2626" }}>
            {failCount}/{values.length + failCount} failed
          </span>
        )}
      </div>
    </div>
  );
}
