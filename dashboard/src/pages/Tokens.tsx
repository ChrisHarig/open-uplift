import { useEffect, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { api, fmt, TokensByModel, TokensBySource, TokensTimeseries } from "../api.ts";
import { CHART } from "../chartColors";

export default function Tokens() {
  const [tokensTS, setTokensTS] = useState<TokensTimeseries[]>([]);
  const [byModel, setByModel] = useState<TokensByModel[]>([]);
  const [bySource, setBySource] = useState<TokensBySource[]>([]);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const projectFilter = searchParams.get("project") || "";
  const projectPath = searchParams.get("project_path") || "";
  const subfolders = searchParams.get("subfolders") === "true";

  const toggleSubfolders = () => {
    const params = new URLSearchParams(searchParams);
    if (subfolders) {
      params.delete("subfolders");
    } else {
      params.set("subfolders", "true");
    }
    setSearchParams(params);
  };

  useEffect(() => {
    const opts = projectPath ? { projectPath, subfolders } : undefined;
    api.tokensTimeseries(30, opts).then(setTokensTS);
    api.tokensByModel(opts).then(setByModel);
    api.tokensBySource(opts).then(setBySource);
  }, [projectPath, subfolders]);

  const totalTokens = byModel.reduce((s, m) => s + m.tokens, 0);

  return (
    <div>
      <Link to="/sessions" className="transcript-back">
        &larr; Sessions
      </Link>
      <h2 className="page-title">
        Tokens
        {projectFilter && (
          <span style={{ fontSize: 14, fontWeight: 400, marginLeft: 12 }}>
            filtered by <strong>{projectFilter}</strong>
            {subfolders && " + subfolders"}
            <button
              className="btn"
              style={{ marginLeft: 8, padding: "2px 8px", fontSize: 12 }}
              onClick={() => navigate("/tokens")}
            >
              Clear
            </button>
          </span>
        )}
      </h2>
      {projectPath && (
        <div style={{ marginBottom: 16 }}>
          <label className="toggle-row" style={{ display: "inline-flex" }}>
            <span className="toggle-label">Incl. subfolders</span>
            <div
              className={`toggle ${subfolders ? "toggle-on" : ""}`}
              onClick={toggleSubfolders}
            >
              <div className="toggle-knob" />
            </div>
          </label>
        </div>
      )}
      <div className="stat-grid">
        <div className="stat-card">
          <div className="label">Total Tokens</div>
          <div className="value">{fmt(totalTokens)}</div>
        </div>
        <div className="stat-card">
          <div className="label">Models Used</div>
          <div className="value">{byModel.length}</div>
        </div>
        <div className="stat-card">
          <div className="label">Applications</div>
          <div className="value">{bySource.length}</div>
        </div>
      </div>

      <div className="chart-grid">
        <div className="chart-card" style={{ gridColumn: "1 / -1" }}>
          <h3>Token Usage Over Time</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart
              data={tokensTS.map((d) => ({
                ...d,
                total: d.input_tokens + d.output_tokens + d.cache_read + d.cache_create,
              }))}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
              <XAxis
                dataKey="day"
                tick={{ fill: "#666666", fontSize: 11 }}
                tickFormatter={(v) => v.slice(5)}
              />
              <YAxis
                tick={{ fill: "#666666", fontSize: 11 }}
                tickFormatter={fmt}
              />
              <Tooltip
                contentStyle={{
                  background: "#ffffff",
                  border: "1px solid #e0e0e0",
                }}
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div style={{ background: "#fff", border: "1px solid #e0e0e0", padding: "8px 12px", fontSize: 12 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
                      <div>Total: {fmt(d.total)}</div>
                      <div style={{ color: "#666", marginTop: 4 }}>
                        <div>Input: {fmt(d.input_tokens)}</div>
                        <div>Output: {fmt(d.output_tokens)}</div>
                        <div>Cache Read: {fmt(d.cache_read)}</div>
                        <div>Cache Create: {fmt(d.cache_create)}</div>
                      </div>
                    </div>
                  );
                }}
              />
              <Line
                type="monotone"
                dataKey="total"
                stroke={CHART.ink}
                strokeWidth={2}
                dot={false}
                name="Total Tokens"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-card">
          <h3>Tokens by Model</h3>
          <ResponsiveContainer width="100%" height={Math.max(200, byModel.length * 35)}>
            <BarChart
              data={byModel.map((m) => ({
                name: m.model.replace("claude-", ""),
                tokens: m.tokens,
              }))}
              layout="vertical"
              margin={{ left: 120 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
              <XAxis
                type="number"
                tick={{ fill: "#666666", fontSize: 11 }}
                tickFormatter={fmt}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: "#666666", fontSize: 12 }}
                width={110}
              />
              <Tooltip
                contentStyle={{ background: "#ffffff", border: "1px solid #e0e0e0" }}
                formatter={(v: number) => [fmt(v), "Tokens"]}
              />
              <Bar dataKey="tokens" fill={CHART.ink} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-card">
          <h3>Tokens by Scaffold</h3>
          <ResponsiveContainer width="100%" height={Math.max(200, bySource.length * 35)}>
            <BarChart
              data={bySource.map((s) => ({
                name: s.tool_source,
                tokens: s.tokens,
              }))}
              layout="vertical"
              margin={{ left: 120 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />
              <XAxis
                type="number"
                tick={{ fill: "#666666", fontSize: 11 }}
                tickFormatter={fmt}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: "#666666", fontSize: 12 }}
                width={110}
              />
              <Tooltip
                contentStyle={{ background: "#ffffff", border: "1px solid #e0e0e0" }}
                formatter={(v: number) => [fmt(v), "Tokens"]}
              />
              <Bar dataKey="tokens" fill={CHART.ink} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
