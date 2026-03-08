import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  api,
  fmt,
  OverviewData,
  UpliftSummary,
  UpliftDistribution,
  UpliftByGroup,
  JudgeOutputSummaryResponse,
  Session,
  Project,
  Organization,
  SetupState,
} from "../api.ts";
import UpliftDistributionChart from "../components/UpliftDistributionChart.tsx";
import InfoTip from "../components/InfoTip.tsx";
import JobProgress from "../components/JobProgress.tsx";

type UpliftMap = Record<string, Record<string, number>>;

function timeAgo(iso: string | null): string {
  if (!iso) return "Never";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const MODE_LABELS: Record<string, string> = {
  hub: "Hub",
  member: "Member",
};

const MODE_COLORS: Record<string, { bg: string; color: string }> = {
  hub: { bg: "#ede9fe", color: "#6d28d9" },
  member: { bg: "#fef3c7", color: "#92400e" },
};

export default function Overview() {
  const navigate = useNavigate();
  const [syncTime, setSyncTime] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [uplift, setUplift] = useState<UpliftSummary | null>(null);
  const [distribution, setDistribution] = useState<UpliftDistribution | null>(null);
  const [byScaffold, setByScaffold] = useState<UpliftByGroup[]>([]);
  const [byModel, setByModel] = useState<UpliftByGroup[]>([]);
  const [judgeOutputSummary, setJudgeOutputSummary] = useState<JudgeOutputSummaryResponse | null>(null);
  const [unjudgedCount, setUnjudgedCount] = useState<number>(0);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [upliftMap, setUpliftMap] = useState<UpliftMap>({});
  const [overviewData, setOverviewData] = useState<OverviewData | null>(null);
  const [setupState, setSetupState] = useState<SetupState | null>(null);
  const [welcomeVisible, setWelcomeVisible] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());
  const [judgeJobId, setJudgeJobId] = useState<string | null>(null);
  const [judgingAll, setJudgingAll] = useState(false);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [upliftByProject, setUpliftByProject] = useState<Record<string, number>>({});
  const [byProject, setByProject] = useState<UpliftByGroup[]>([]);

  useEffect(() => {
    api.syncStatus().then((s) => setSyncTime(s.last_synced));
    api.overview().then(setOverviewData);
    api.upliftBySession().then(setUpliftMap);
    api.unprocessedCount().then((d) => setUnjudgedCount(d.count ?? 0)).catch(() => {});
    api.getSetupState().then((s) => {
      setSetupState(s);
      if (!s.has_sessions && !s.welcome_dismissed) {
        setWelcomeVisible(true);
        setExpandedSections(new Set([0, 1, 2, 3, 4, 5]));
      }
    });
    api.upliftSummary("local").then(setUplift);
    api.upliftDistribution("llm-judge", "local").then(setDistribution);
    api.upliftByScaffold("llm-judge", "local").then(setByScaffold).catch(() => {});
    api.upliftByModel("llm-judge", "local").then(setByModel).catch(() => {});
    api.judgeOutputsSummary("local").then(setJudgeOutputSummary).catch(() => {});
    api.sessions(50, 0, { org_id: "local" }).then((d) => setSessions(d.sessions));
    api.projects().then(setProjects);
    api.organizations().then(setOrgs);
    api.upliftByProject("llm-judge", "local").then((data: UpliftByGroup[]) => {
      const map: Record<string, number> = {};
      for (const d of data) {
        if (d.project_name) map[d.project_name] = d.avg_uplift;
      }
      setUpliftByProject(map);
      setByProject(data);
    }).catch(() => {});
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await api.sync();
      const s = await api.syncStatus();
      setSyncTime(s.last_synced);
    } finally {
      setSyncing(false);
    }
  };

  const llmJudgeOutput = uplift?.outputs.find((o) => o.output_id === "llm-judge") ||
    uplift?.outputs.find((o) => o.output_id === "llm-judge-trans");

  const filteredSessions = sessions.slice(0, 5);

  return (
    <div>
      {/* A. Header row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 className="page-title" style={{ marginBottom: 0 }}>Overview</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Last synced: {timeAgo(syncTime)}
          </span>
          <button className="btn" onClick={handleSync} disabled={syncing} style={{ fontSize: 12 }}>
            {syncing ? "Syncing..." : "Sync Now"}
          </button>
          <button
            onClick={() => {
              setWelcomeVisible(true);
              setExpandedSections(new Set([0, 1, 2, 3, 4, 5]));
            }}
            title="Setup Guide"
            style={{
              width: 28,
              height: 28,
              borderRadius: "50%",
              border: "1px solid var(--border)",
              background: "none",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: 600,
              color: "var(--text-muted)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            ?
          </button>
        </div>
      </div>

      {/* Welcome / Setup Guide Modal */}
      {welcomeVisible && (
        <>
          {/* Backdrop */}
          <div
            onMouseDown={() => {
              setWelcomeVisible(false);
              if (setupState && !setupState.welcome_dismissed) api.dismissWelcome();
            }}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.5)",
              zIndex: 100,
            }}
          />
          {/* Modal card */}
          <div style={{
            position: "fixed",
            top: "5vh",
            left: "50%",
            transform: "translateX(-50%)",
            width: "min(720px, 90vw)",
            maxHeight: "90vh",
            overflowY: "auto",
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: 12,
            padding: "28px 32px",
            zIndex: 101,
            boxShadow: "0 16px 48px rgba(0,0,0,0.2)",
          }}>
            <button
              onClick={() => {
                setWelcomeVisible(false);
                if (setupState && !setupState.welcome_dismissed) api.dismissWelcome();
              }}
              style={{
                position: "absolute",
                top: 16,
                right: 16,
                background: "none",
                border: "none",
                fontSize: 22,
                cursor: "pointer",
                color: "var(--text-muted)",
                lineHeight: 1,
              }}
              aria-label="Close"
            >
              &times;
            </button>
            <h2 style={{ marginTop: 0, marginBottom: 8 }}>Welcome to Open Uplift</h2>
            <p style={{ color: "var(--text-muted)", fontSize: 14, marginBottom: 20, lineHeight: 1.6 }}>
              Open Uplift measures how much faster you work with AI coding assistants.
              It compares the time tasks actually took with an LLM estimate of how long
              they'd take without AI, giving you a concrete uplift factor.
            </p>

            {[
              {
                title: "Developer Profile",
                body: "Tell the judge about your experience level so time estimates are calibrated to you. A sentence or two about your stack and years of experience is enough.",
                link: "/settings",
                linkText: "Go to Settings",
                check: setupState?.has_profile,
              },
              {
                title: "Import Sessions",
                body: "Open Uplift reads your Claude Code session transcripts automatically when you sync. Run open-uplift sync or hit Sync in Settings to pull in your history.",
                link: "/settings",
                linkText: "Go to Settings",
                check: setupState?.has_sessions,
              },
              {
                title: "Compaction & Judging",
                body: "Each session goes through two LLM passes: compaction summarizes what happened, then a judge estimates how long it would have taken without AI. Run open-uplift sessions judge --all or use the Judge page to process sessions.",
                link: "/scripts",
                linkText: "Go to Judge",
              },
              {
                title: "Organizations",
                body: "Create an org to group sessions by team or project. Add folders to an org to assign sessions automatically. You can also join a remote org via git to share aggregate metrics with your team.",
                link: "/organizations",
                linkText: "Go to Organizations",
                check: setupState?.has_organizations,
              },
              {
                title: "Sync Settings",
                body: "Configure how often Open Uplift syncs your local sessions and pushes/pulls org data. Set up batch processing to auto-run compaction and judging on new sessions.",
                link: "/settings",
                linkText: "Go to Settings",
              },
            ].map((section, i) => (
              <div key={i} style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginTop: 10 }}>
                <div
                  onClick={() => {
                    const next = new Set(expandedSections);
                    next.has(i) ? next.delete(i) : next.add(i);
                    setExpandedSections(next);
                  }}
                  style={{
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "4px 0",
                    userSelect: "none",
                  }}
                >
                  <span style={{ fontSize: 12, color: "var(--text-muted)", width: 16, textAlign: "center" }}>
                    {expandedSections.has(i) ? "\u25BC" : "\u25B6"}
                  </span>
                  <span style={{ fontWeight: 600, fontSize: 14 }}>
                    {i + 1}. {section.title}
                  </span>
                  {section.check && (
                    <span style={{ color: "#16a34a", fontSize: 14 }} title="Done">&#10003;</span>
                  )}
                </div>
                {expandedSections.has(i) && (
                  <div style={{ paddingLeft: 24, paddingBottom: 8 }}>
                    <p style={{ color: "var(--text-muted)", fontSize: 13, lineHeight: 1.6, margin: "6px 0 10px" }}>
                      {section.body}
                    </p>
                    <Link
                      to={section.link}
                      onClick={() => setWelcomeVisible(false)}
                      style={{ fontSize: 13 }}
                    >
                      {section.linkText} &rarr;
                    </Link>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* B. Uplift Metrics */}
      <h3 style={{ margin: "0 0 12px", color: "var(--text-muted)" }}>Uplift</h3>

      {/* Stat cards */}
      <div className="stat-grid">
          <div className="stat-card">
            <div className="label">Avg Uplift<InfoTip text="Uplift = estimated time without AI / measured time with AI. Higher means more productivity gain." /></div>
            <div className="value" style={{ textAlign: "center" }}>
              {llmJudgeOutput && llmJudgeOutput.count > 0 ? `${llmJudgeOutput.avg_uplift.toFixed(2)}x` : "\u2014"}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">Sessions Measured<InfoTip text="Total number of sessions that have been evaluated by the LLM judge." /></div>
            <Link to="/sessions?has_judge=true" style={{ color: "inherit", textDecoration: "none" }}>
              <div className="value" style={{ textAlign: "center", textDecoration: "underline", textDecorationColor: "var(--border)", textUnderlineOffset: 2 }}>
                {judgeOutputSummary?.total_judged_sessions ?? 0}
              </div>
            </Link>
          </div>
          <div className="stat-card">
            <div className="label">Unjudged<InfoTip text="Sessions that have not yet been evaluated by the LLM judge. Click Judge All to run compaction and judge on these sessions." /></div>
            <Link to="/sessions?has_judge=false" style={{ color: "inherit", textDecoration: "none" }}>
              <div className="value" style={{ textAlign: "center", textDecoration: "underline", textDecorationColor: "var(--border)", textUnderlineOffset: 2 }}>
                {unjudgedCount}
              </div>
            </Link>
            {(() => {
              if (unjudgedCount <= 0 && !judgeJobId) return null;
              return judgeJobId ? (
                <JobProgress jobId={judgeJobId} onComplete={() => {
                  setJudgeJobId(null);
                  api.judgeOutputsSummary("local").then(setJudgeOutputSummary).catch(() => {});
                  api.unprocessedCount().then((d) => setUnjudgedCount(d.count ?? 0)).catch(() => {});
                  api.upliftSummary("local").then(setUplift);
                  api.overview().then(setOverviewData);
                  api.upliftDistribution("llm-judge", "local").then(setDistribution);
                  api.upliftBySession().then(setUpliftMap);
                }} />
              ) : (
                <button
                  className="btn"
                  style={{ fontSize: 11, padding: "3px 10px", marginTop: 6 }}
                  disabled={judgingAll}
                  onClick={async () => {
                    setJudgingAll(true);
                    try {
                      const res = await api.runUnprocessed();
                      if (res.job_id) {
                        setJudgeJobId(res.job_id);
                        window.dispatchEvent(new Event("job-created"));
                      }
                    } catch {
                      // ignore
                    } finally {
                      setJudgingAll(false);
                    }
                  }}
                >
                  {judgingAll ? "Starting..." : "Judge All"}
                </button>
              );
            })()}
          </div>
      </div>

      {/* Uplift charts */}
      {/* Distribution — full width */}
      {distribution && distribution.values && distribution.values.length > 0 && (() => {
        const successSummary = judgeOutputSummary?.fields.find((s: { field_name: string; value_type: string }) => s.field_name === "success" && s.value_type === "boolean");
        const failCount = successSummary ? successSummary.count - successSummary.true_count : 0;
        return (
          <div style={{ marginBottom: 16 }}>
            <UpliftDistributionChart
              values={distribution.values}
              failCount={failCount}
              stats={distribution.stats}
            />
          </div>
        );
      })()}

      {/* Scaffold + Model — side by side */}
      <div className="chart-grid" style={{ marginBottom: 24 }}>
        {byScaffold.length > 0 && (
          <div className="chart-card">
            <h3>Uplift by Scaffold</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={byScaffold}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis dataKey="scaffold" tick={{ fill: "#666", fontSize: 11 }} />
                <YAxis tick={{ fill: "#666", fontSize: 11 }} tickFormatter={(v) => `${v}x`} />
                <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e0e0e0" }} formatter={(v: number) => [`${v}x`, "Avg Uplift"]} />
                <Bar dataKey="avg_uplift" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {byModel.length > 0 && (
          <div className="chart-card">
            <h3>Uplift by Model</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={byModel}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis dataKey="model" tick={{ fill: "#666", fontSize: 11 }} tickFormatter={(v) => v?.replace("claude-", "") || "unknown"} />
                <YAxis tick={{ fill: "#666", fontSize: 11 }} tickFormatter={(v) => `${v}x`} />
                <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e0e0e0" }} formatter={(v: number) => [`${v}x`, "Avg Uplift"]} />
                <Bar dataKey="avg_uplift" fill="#ec4899" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* C. Recent Sessions */}
      <h3 style={{ margin: "0 0 12px", color: "var(--text-muted)" }}>Recent Sessions</h3>
      {filteredSessions.length > 0 ? (
        <>
          <div style={{ overflowX: "auto" }}>
          <table style={{ minWidth: 1100 }}>
            <thead>
              <tr>
                <th style={{ width: 28 }} title="Judge status"></th>
                <th>Date</th>
                <th>Project</th>
                <th>Scaffold</th>
                <th>Model</th>
                <th>Transcript</th>
                <th>Uplift</th>
                <th>Messages</th>
                <th>Tools</th>
                <th>Tokens</th>
                <th>Survey</th>
              </tr>
            </thead>
            <tbody>
              {filteredSessions.map((s) => {
                const llmJudgeUplift = upliftMap[s.session_id]?.["llm-judge"] ?? null;
                const scaffold = (s as Session & { scaffold?: string }).scaffold || s.tool_source;
                const isJudged = s.judge_current || llmJudgeUplift != null;
                const isCurrent = s.judge_current === 1;
                const isStale = isJudged && !isCurrent;
                return (
                  <tr key={s.session_id}>
                    <td style={{ textAlign: "center", padding: "0 2px" }}>
                      {isJudged ? (
                        <span
                          title={isCurrent ? "Judged (up to date)" : "Judged (stale \u2014 session has new messages)"}
                          style={{
                            display: "inline-block",
                            width: 10,
                            height: 10,
                            borderRadius: "50%",
                            background: isCurrent ? "#16a34a" : "#f59e0b",
                            opacity: isCurrent ? 1 : 0.8,
                          }}
                        />
                      ) : (
                        <span
                          title="Not judged"
                          style={{
                            display: "inline-block",
                            width: 10,
                            height: 10,
                            borderRadius: "50%",
                            border: "1.5px solid var(--border)",
                            background: "transparent",
                          }}
                        />
                      )}
                    </td>
                    <td>{new Date(s.started_at).toLocaleDateString()}</td>
                    <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>
                      {s.project_name || "\u2014"}
                    </td>
                    <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {scaffold?.replace("claude_code", "Claude Code").replace("custom:", "") || "\u2014"}
                    </td>
                    <td>{s.model_primary?.replace("claude-", "") || "\u2014"}</td>
                    <td>
                      <Link
                        to={`/sessions/${s.session_id}/transcript`}
                        className="btn btn-transcript"
                      >
                        View
                      </Link>
                    </td>
                    <td>
                      {llmJudgeUplift != null ? (
                        <Link
                          to={`/sessions/${s.session_id}/transcript#judge`}
                          style={{ color: "#16a34a", fontWeight: 500, textDecoration: "underline", textDecorationColor: "var(--border)", textUnderlineOffset: 2 }}
                        >
                          {llmJudgeUplift}x
                        </Link>
                      ) : isJudged && s.judge_success === "false" ? (
                        <Link
                          to={`/sessions/${s.session_id}/transcript#judge`}
                          title="Judge determined task failed"
                          style={{ color: "var(--text)", fontWeight: 600, textDecoration: "underline", textDecorationColor: "var(--border)", textUnderlineOffset: 2 }}
                        >
                          F
                        </Link>
                      ) : (
                        <span className="dash-disabled">&mdash;</span>
                      )}
                    </td>
                    <td>{s.message_count.toLocaleString()}</td>
                    <td>{s.tool_call_count.toLocaleString()}</td>
                    <td>
                      {s.project_name ? (
                        <Link
                          to={`/tokens?project=${encodeURIComponent(s.project_name)}${s.project_path ? `&project_path=${encodeURIComponent(s.project_path)}` : ""}`}
                          style={{ textDecoration: "underline", textDecorationColor: "var(--border)", textUnderlineOffset: 2, color: "inherit" }}
                        >
                          {fmt(s.total_input_tokens + s.total_output_tokens)}
                        </Link>
                      ) : (
                        fmt(s.total_input_tokens + s.total_output_tokens)
                      )}
                    </td>
                    <td>
                      {s.has_report ? (
                        <span className="badge-reported">Reported</span>
                      ) : (
                        <span className="dash-disabled">&mdash;</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
          <div style={{ marginTop: 8, marginBottom: 24 }}>
            <Link to="/sessions" style={{ fontSize: 13, color: "var(--text-muted)" }}>
              View all sessions &rarr;
            </Link>
          </div>
        </>
      ) : (
        <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 24 }}>No sessions yet.</p>
      )}

      {/* Uplift by Project */}
      {byProject.length > 0 && (
        <div className="chart-card" style={{ marginBottom: 24 }}>
          <h3>Uplift by Project</h3>
          <ResponsiveContainer width="100%" height={Math.max(200, byProject.length * 30)}>
            <BarChart data={byProject} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
              <XAxis type="number" tick={{ fill: "#666", fontSize: 11 }} tickFormatter={(v) => `${v}x`} />
              <YAxis dataKey="project_name" type="category" tick={{ fill: "#666", fontSize: 11 }} width={120} />
              <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e0e0e0" }} formatter={(v: number) => [`${v}x`, "Avg Uplift"]} />
              <Bar dataKey="avg_uplift" fill="#3b82f6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* D. Recent Projects */}
      <h3 style={{ margin: "0 0 12px", color: "var(--text-muted)" }}>Recent Projects</h3>
      {(() => {
        const filteredProjects = projects.slice(0, 3);
        return filteredProjects.length > 0 ? (
        <>
          <div className="project-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
            {filteredProjects.map((p) => (
              <div
                className="project-card"
                key={p.project_name}
                onClick={() => navigate(`/sessions?project=${encodeURIComponent(p.project_name)}`)}
                style={{ cursor: "pointer" }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <div className="project-name">{p.project_name}</div>
                  {p.org_name && (
                    <span style={{
                      fontSize: 10,
                      padding: "2px 6px",
                      background: p.org_is_verified ? "#dcfce7" : "#f3f4f6",
                      color: p.org_is_verified ? "#15803d" : "#6b7280",
                      borderRadius: 4,
                      fontWeight: 600,
                      whiteSpace: "nowrap",
                    }}>
                      {p.org_name}
                    </span>
                  )}
                </div>
                <div className="project-path">{p.project_path || ""}</div>
                <div className="project-stats">
                  <div className="project-stat">
                    <span className="project-stat-value" style={{ color: upliftByProject[p.project_name] ? "#16a34a" : undefined }}>
                      {upliftByProject[p.project_name] ? `${upliftByProject[p.project_name]}x` : "\u2014"}
                    </span>
                    <span className="project-stat-label">Uplift</span>
                  </div>
                  <div className="project-stat">
                    <span className="project-stat-value">{p.session_count.toLocaleString()}</span>
                    <span className="project-stat-label">Sessions</span>
                  </div>
                  <div className="project-stat">
                    <span className="project-stat-value">{fmt(p.total_tokens)}</span>
                    <span className="project-stat-label">Tokens</span>
                  </div>
                  <div className="project-stat">
                    <span className="project-stat-value">{p.total_messages.toLocaleString()}</span>
                    <span className="project-stat-label">Messages</span>
                  </div>
                </div>
                <div className="project-meta">
                  Last active: {new Date(p.last_active).toLocaleDateString()}
                </div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 8 }}>
            <Link to="/projects" style={{ fontSize: 13, color: "var(--text-muted)" }}>
              View all projects &rarr;
            </Link>
          </div>
        </>
      ) : (
        <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No projects yet.</p>
      );
      })()}

      {/* E. Organizations */}
      <h3 style={{ margin: "24px 0 12px", color: "var(--text-muted)" }}>Organizations</h3>
      {(() => {
        const recentOrgs = orgs.slice(0, 3);
        return recentOrgs.length > 0 ? (
          <>
            <div className="project-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
              {recentOrgs.map((org) => {
                const mode = org.org_mode || "hub";
                const modeStyle = MODE_COLORS[mode] || MODE_COLORS.hub;
                return (
                  <div
                    key={org.org_id}
                    className="project-card"
                    onClick={() => navigate(`/organizations/${org.org_id}`)}
                    style={{ cursor: "pointer" }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div className="project-name">{org.name}</div>
                      <span style={{
                        fontSize: 10,
                        padding: "2px 6px",
                        background: modeStyle.bg,
                        color: modeStyle.color,
                        borderRadius: 4,
                        fontWeight: 600,
                      }}>
                        {MODE_LABELS[mode] || mode}
                      </span>
                      {org.is_verified === 1 && (
                        <span style={{
                          fontSize: 10,
                          padding: "2px 6px",
                          background: "#dcfce7",
                          color: "#15803d",
                          borderRadius: 4,
                          fontWeight: 600,
                        }}>
                          Verified
                        </span>
                      )}
                    </div>
                    {org.description && (
                      <div className="project-path">{org.description}</div>
                    )}
                    <div className="project-stats" style={{ marginTop: 12 }}>
                      <div className="project-stat">
                        <span className="project-stat-value">{org.folder_count}</span>
                        <span className="project-stat-label">Folders</span>
                      </div>
                    </div>
                    <div className="project-meta">
                      Created: {new Date(org.created_at).toLocaleDateString()}
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ marginTop: 8 }}>
              <Link to="/organizations" style={{ fontSize: 13, color: "var(--text-muted)" }}>
                View all organizations &rarr;
              </Link>
            </div>
          </>
        ) : (
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No organizations yet.</p>
        );
      })()}
    </div>
  );
}
