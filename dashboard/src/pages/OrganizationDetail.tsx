import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";
import { api, fmt, OrgDetail, OrgAnalytics, OrgMembership, OrgHubInfo, OrgRemoteAggregate, UpliftDistribution, UpliftByGroup, Project, UnpushedSession, SharingConfig } from "../api.ts";
import UpliftDistributionChart from "../components/UpliftDistributionChart.tsx";
import InfoTip from "../components/InfoTip.tsx";
import JobProgress from "../components/JobProgress.tsx";

const MODE_LABELS: Record<string, string> = {
  hub: "Hub",
  member: "Member",
};

const MODE_COLORS: Record<string, { bg: string; color: string }> = {
  hub: { bg: "#ede9fe", color: "#6d28d9" },
  member: { bg: "#fef3c7", color: "#92400e" },
};

export default function OrganizationDetail() {
  const { orgId } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const [org, setOrg] = useState<OrgDetail | null>(null);
  const [analytics, setAnalytics] = useState<OrgAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Uplift chart data
  const [distribution, setDistribution] = useState<UpliftDistribution | null>(null);
  const [byScaffold, setByScaffold] = useState<UpliftByGroup[]>([]);
  const [byModel, setByModel] = useState<UpliftByGroup[]>([]);
  const [byProject, setByProject] = useState<UpliftByGroup[]>([]);
  const [remoteAggregate, setRemoteAggregate] = useState<OrgRemoteAggregate | null>(null);
  const [upliftByMember, setUpliftByMember] = useState<{member_name: string; avg_uplift: number; sessions: number}[]>([]);

  // Org membership / hub data
  const [membership, setMembership] = useState<OrgMembership | null>(null);
  const [sharingConfig, setSharingConfig] = useState<SharingConfig | null>(null);
  const [pushing, setPushing] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [pushResult, setPushResult] = useState<string | null>(null);
  const [pullResult, setPullResult] = useState<string | null>(null);
  const [pullConfig, setPullConfig] = useState<SharingConfig | null>(null);

  // Hub info
  const [hubInfo, setHubInfo] = useState<OrgHubInfo | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  // Hub sessions
  const [hubSessions, setHubSessions] = useState<Record<string, unknown>[]>([]);

  // Add folder state
  const [showAddFolder, setShowAddFolder] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedFolders, setSelectedFolders] = useState<string[]>([]);
  const [addingFolders, setAddingFolders] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Member removal
  const [removingMember, setRemovingMember] = useState<string | null>(null);

  // Unpushed sessions preview (member view)
  const [unpushedSessions, setUnpushedSessions] = useState<UnpushedSession[]>([]);
  const [unpushedTotal, setUnpushedTotal] = useState(0);
  const [unpushedLastPush, setUnpushedLastPush] = useState<string | null>(null);
  const [unjudgedCount, setUnjudgedCount] = useState(0);
  const [staleCount, setStaleCount] = useState(0);
  const [judgingBeforePush, setJudgingBeforePush] = useState(false);
  const [batchJobId, setBatchJobId] = useState<string | null>(null);

  const load = () => {
    if (!orgId) return;
    api.organizationDetail(orgId).then(setOrg).catch((e) => setError(e.message));
    api.organizationAnalytics(orgId).then(setAnalytics).catch(() => {});
    api.upliftDistribution("llm-judge", orgId).then(setDistribution).catch(() => {});
    api.upliftByScaffold("llm-judge", orgId).then(setByScaffold).catch(() => {});
    api.upliftByModel("llm-judge", orgId).then(setByModel).catch(() => {});
    api.upliftByProject("llm-judge", orgId).then(setByProject).catch(() => {});
    api.organizationRemoteAggregate(orgId).then(setRemoteAggregate).catch(() => {});
    api.organizationHubInfo(orgId).then(setHubInfo).catch(() => {});
    api.hubSessions(orgId).then(setHubSessions).catch(() => {});
    api.organizationUpliftByMember(orgId).then(setUpliftByMember).catch(() => {});
    api.orgMemberships().then((memberships) => {
      const m = memberships.find((ms) => ms.org_id === orgId);
      setMembership(m || null);
      if (m?.sharing_config) {
        try { setSharingConfig(JSON.parse(m.sharing_config)); } catch { /* ignore */ }
      }
    }).catch(() => {});
    api.unpushedSessions(orgId).then((data) => {
      setUnpushedSessions(data.sessions);
      setUnpushedTotal(data.total);
      setUnpushedLastPush(data.last_push_at);
      setUnjudgedCount(data.unjudged_count ?? 0);
      setStaleCount(data.stale_count ?? 0);
    }).catch(() => {});
    api.pullConfig(orgId).then((data) => {
      if (data.pull_config) setPullConfig(data.pull_config);
    }).catch(() => {});
  };

  useEffect(load, [orgId]);

  const handleRemoveFolder = async (folderPath: string) => {
    if (!orgId) return;
    await api.removeOrgFolders(orgId, [folderPath]);
    load();
  };

  const openAddFolder = () => {
    setShowAddFolder(true);
    setSelectedFolders([]);
    setAddError(null);
    api.projects().then(setProjects);
  };

  const handleAddFolders = async () => {
    if (!orgId || selectedFolders.length === 0) return;
    setAddingFolders(true);
    setAddError(null);
    try {
      await api.addOrgFolders(orgId, selectedFolders);
      setShowAddFolder(false);
      load();
    } catch (e) {
      setAddError((e as Error).message);
    } finally {
      setAddingFolders(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedCode(text);
      setTimeout(() => setCopiedCode(null), 2000);
    });
  };

  const goToSettings = () => navigate(`/organizations/${orgId}/settings`);

  const handleDeleteMember = async (memberName: string) => {
    if (!orgId || !confirm(`Remove member "${memberName}"? Their pushed data will also be removed.`)) return;
    setRemovingMember(memberName);
    try {
      await api.deleteHubMember(orgId, memberName);
      load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setRemovingMember(null);
    }
  };

  if (error) return <div className="empty">{error}</div>;
  if (!org) return <div className="empty">Loading...</div>;

  const existingPaths = new Set(org.folders.map((f) => f.folder_path));
  const isHubAdmin = hubInfo && hubInfo.members.length > 0;
  const activeInvite = hubInfo?.invites.filter((i) => !i.revoked_at)[0] ?? null;
  const mode = org.org_mode || "hub";
  const modeStyle = MODE_COLORS[mode] || MODE_COLORS.hub;
  const hasFolders = org.folders.length > 0;
  const showLocal = (mode === "hub" && hasFolders) || mode === "member";
  const showHub = mode === "hub";
  const isMember = mode === "member";

  const adminName = hubInfo?.members.find(m => m.role === "admin")?.member_name ?? "Admin";

  const mergedUpliftByMember = (() => {
    const base = Array.isArray(upliftByMember) ? upliftByMember : [];
    if (!showHub) return base;
    const result = [...base];
    if (showLocal && analytics && analytics.uplift.count && analytics.uplift.count > 0) {
      result.unshift({
        member_name: adminName,
        avg_uplift: Math.round(analytics.uplift.avg_uplift * 100) / 100,
        sessions: analytics.uplift.count,
      });
    }
    return result;
  })();

  const orgTotal = (() => {
    if (mode !== "hub" || mergedUpliftByMember.length === 0) return null;
    let totalSessions = 0;
    let weightedSum = 0;
    for (const m of mergedUpliftByMember) {
      totalSessions += m.sessions;
      weightedSum += m.avg_uplift * m.sessions;
    }
    if (totalSessions === 0) return null;
    return { avg: weightedSum / totalSessions, count: totalSessions };
  })();

  return (
    <div>
      {/* Top bar with back link + settings gear */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <Link to="/organizations" className="transcript-back">
          &larr; Organizations
        </Link>
        <button
          className="btn btn-secondary"
          style={{ padding: "4px 10px", fontSize: 12 }}
          onClick={goToSettings}
          title="Settings"
        >
          Settings
        </button>
      </div>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <h2 className="page-title" style={{ margin: 0 }}>{org.name}</h2>
        <span
          style={{
            fontSize: 11,
            padding: "2px 8px",
            background: modeStyle.bg,
            color: modeStyle.color,
            borderRadius: 4,
            fontWeight: 600,
          }}
        >
          {MODE_LABELS[mode] || mode}
        </span>
        {org.is_verified === 1 && (
          <span
            style={{
              fontSize: 11,
              padding: "2px 8px",
              background: "#dcfce7",
              color: "#15803d",
              borderRadius: 4,
              fontWeight: 600,
            }}
          >
            Verified
          </span>
        )}
      </div>
      {org.description && (
        <p style={{ color: "var(--text-muted)", fontSize: 14, marginBottom: 24 }}>
          {org.description}
        </p>
      )}

      {/* Stat cards — mode-aware */}
      <div className="stat-grid">
        {/* Card 1: Uplift */}
        <div className="stat-card">
          <div className="label">Uplift<InfoTip text="Uplift = estimated time without AI / measured time with AI." /></div>
          <div style={{ display: "flex", alignItems: "stretch" }}>
            {showLocal && (
              <div style={{ flex: 1, textAlign: "center" }}>
                {(showHub || isMember) && <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Local</div>}
                <div className="value" style={{ color: analytics && analytics.uplift.count > 0 ? "#16a34a" : undefined }}>
                  {analytics && analytics.uplift.count > 0 ? `${analytics.uplift.avg_uplift.toFixed(2)}x` : "\u2014"}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{analytics?.uplift.count ?? 0} sessions</div>
              </div>
            )}
            {showHub && orgTotal && (
              <>
                {showLocal && <div style={{ width: 1, background: "var(--border)", margin: "0 8px" }} />}
                <div style={{ flex: 1, textAlign: "center" }}>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Org Total</div>
                  <div className="value" style={{ color: "#8b5cf6" }}>
                    {`${orgTotal.avg.toFixed(2)}x`}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                    {orgTotal.count} sessions
                  </div>
                </div>
              </>
            )}
            {showHub && !showLocal && !orgTotal && (
              <div style={{ flex: 1, textAlign: "center" }}>
                <div className="value">{"\u2014"}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>0 sessions</div>
              </div>
            )}
            {isMember && remoteAggregate?.aggregate && (
              <>
                <div style={{ width: 1, background: "var(--border)", margin: "0 8px" }} />
                <div style={{ flex: 1, textAlign: "center" }}>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Total</div>
                  <div className="value" style={{ color: "#8b5cf6" }}>
                    {remoteAggregate.aggregate.avg_uplift_factor != null
                      ? `${remoteAggregate.aggregate.avg_uplift_factor.toFixed(2)}x`
                      : "N/A"}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                    {remoteAggregate.aggregate.total_sessions ?? 0} sessions
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Hub with folders or member: show local sessions card */}
        {showLocal && (
          <div className="stat-card">
            <div className="label">Local Sessions<InfoTip text="Total local sessions in this org's folders." /></div>
            <div className="value" style={{ textAlign: "center" }}>{org.stats.total_sessions.toLocaleString()}</div>
          </div>
        )}

        {/* Hub mode: Pushed Sessions card */}
        {showHub && (
          <div className="stat-card">
            <div className="label">
              Pushed Sessions
              <InfoTip text={org.pushed_aggregate_only ? "Aggregate stats from this many sessions across members." : "Sessions received from members."} />
            </div>
            <div className="value" style={{ textAlign: "center" }}>{org.pushed_sessions_count ?? 0}</div>
            {org.pushed_aggregate_only && (
              <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2, textAlign: "center" }}>aggregated</div>
            )}
          </div>
        )}

        {/* Member mode: Sessions Unpushed card */}
        {isMember && (
          <div className="stat-card">
            <div className="label">Sessions Unpushed<InfoTip text="Sessions updated since last push." /></div>
            <div className="value" style={{ textAlign: "center" }}>{org.unpushed_count ?? 0}</div>
          </div>
        )}
      </div>

      {/* ===== HUB VIEW ===== */}

      {/* Hub admin: Team section with Copy Invite Code button */}
      {showHub && isHubAdmin && (
        <>
          <h3 style={{ margin: "32px 0 12px", color: "var(--text-muted)" }}>Team</h3>
          <div className="chart-card" style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <div style={{ fontWeight: 500, fontSize: 14 }}>
                Members ({hubInfo.members.length})
              </div>
              {activeInvite && (
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 11, padding: "4px 10px" }}
                  onClick={() => copyToClipboard(activeInvite.invite_code)}
                >
                  {copiedCode === activeInvite.invite_code ? "Copied!" : "Copy Invite Code"}
                </button>
              )}
            </div>
            <table>
              <thead>
                <tr><th>Name</th><th>Sessions</th><th>Avg Uplift</th><th>Last Push</th><th></th></tr>
              </thead>
              <tbody>
                {hubInfo.members.map((m) => (
                  <tr key={m.member_name}>
                    <td>
                      {m.member_name}
                      {m.role === "admin" && (
                        <span style={{
                          marginLeft: 6,
                          fontSize: 9,
                          padding: "1px 4px",
                          background: "#dbeafe",
                          color: "#1d4ed8",
                          borderRadius: 3,
                        }}>
                          admin
                        </span>
                      )}
                    </td>
                    <td>
                      {!hasFolders && m.role === "admin" ? (
                        <span style={{ color: "var(--text-muted)" }}>{"\u2014"}</span>
                      ) : (m.sessions_pushed ?? 0) > 0 ? (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                          {m.role === "admin" ? (
                            <Link
                              to={`/sessions?org_id=${orgId}&is_local=true`}
                              style={{ color: "var(--link)" }}
                            >
                              {m.sessions_pushed}
                            </Link>
                          ) : m.has_sessions ? (
                            <Link
                              to={`/sessions?org_id=${orgId}&source_member=${encodeURIComponent(m.member_name)}&is_local=false`}
                              style={{ color: "var(--link)" }}
                            >
                              {m.sessions_pushed}
                            </Link>
                          ) : (
                            <span>{m.sessions_pushed}</span>
                          )}
                          {m.aggregate_only && (
                            <span style={{
                              fontSize: 9,
                              padding: "1px 4px",
                              background: "var(--bg-hover)",
                              color: "var(--text-muted)",
                              borderRadius: 3,
                            }}>
                              agg
                            </span>
                          )}
                        </span>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>0</span>
                      )}
                    </td>
                    <td>
                      {m.avg_uplift != null ? (
                        <span style={{ color: "#16a34a", fontWeight: 500 }}>{m.avg_uplift}x</span>
                      ) : (m.sessions_pushed ?? 0) > 0 ? (
                        <span style={{ color: "var(--text-muted)" }}>N/A</span>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>{"\u2014"}</span>
                      )}
                    </td>
                    <td>{m.last_push_at ? m.last_push_at.slice(0, 16).replace("T", " ") : "\u2014"}</td>
                    <td>
                      {m.role !== "admin" && (
                        <button
                          className="btn btn-secondary"
                          style={{ padding: "2px 6px", fontSize: 10, color: "#dc2626" }}
                          disabled={removingMember === m.member_name}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteMember(m.member_name);
                          }}
                        >
                          {removingMember === m.member_name ? "..." : "Remove"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {mergedUpliftByMember.length > 0 && (
            <div className="chart-card" style={{ marginTop: 16, marginBottom: 16 }}>
              <h3>Uplift by Member</h3>
              <ResponsiveContainer width="100%" height={Math.max(200, mergedUpliftByMember.length * 30)}>
                <BarChart data={mergedUpliftByMember} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis type="number" tick={{ fill: "#666", fontSize: 11 }} tickFormatter={(v) => `${v}x`} />
                  <YAxis dataKey="member_name" type="category" tick={{ fill: "#666", fontSize: 11 }} width={120} />
                  <Tooltip contentStyle={{ background: "#fff", border: "1px solid #e0e0e0" }} formatter={(v: number) => [`${v}x`, "Avg Uplift"]} />
                  <Bar dataKey="avg_uplift" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

      {/* ===== MEMBER VIEW ===== */}

      {/* Member view: Push and Pull sections */}
      {isMember && membership && (
        <>
          {/* Hub info bar */}
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 16, marginBottom: 8 }}>
            {membership.hub_url && <>Hub: <strong>{membership.hub_url}</strong></>}
            {" "}&middot; Role: {membership.role}
          </div>

          {/* PUSH section */}
          <div className="chart-card" style={{ marginBottom: 16 }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>Push</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Last push: {membership.last_push_at
                  ? membership.last_push_at.slice(0, 16).replace("T", " ")
                  : "Never"}
              </div>
            </div>

            {pushResult && (
              <div style={{ fontSize: 12, color: pushResult.startsWith("Error") ? "#dc2626" : "#16a34a", marginTop: 8 }}>
                {pushResult}
              </div>
            )}

            {/* Data being shared (locked from admin) */}
            {sharingConfig && (
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 12 }}>
                <span style={{ fontWeight: 500, color: "var(--text-muted)", whiteSpace: "nowrap" }}>Data Shared Per Push:</span>
                {Object.entries(sharingConfig.stats).filter(([, v]) => v).map(([key]) => (
                  <span key={key} style={{
                    padding: "2px 8px",
                    background: "var(--bg-hover)",
                    borderRadius: 4,
                    color: "var(--text-muted)",
                  }}>
                    {key.replace(/_/g, " ")}
                  </span>
                ))}
                <span style={{
                  padding: "2px 8px",
                  background: "var(--bg-hover)",
                  borderRadius: 4,
                  color: "var(--text-muted)",
                }}>
                  {sharingConfig.level >= 2 ? "per-session" : "aggregates only"}
                </span>
                <span style={{ flex: 1 }} />
                <span style={{
                  fontSize: 10,
                  padding: "1px 5px",
                  background: "var(--bg-hover)",
                  borderRadius: 3,
                  color: "var(--text-muted)",
                  whiteSpace: "nowrap",
                }}>
                  Set by Admin
                </span>
              </div>
            )}

            {/* Sessions ready to push — with Push button inline */}
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <div>
                  <span style={{ fontSize: 13, fontWeight: 500 }}>
                    {org.judged_unpushed_count ?? 0} session{(org.judged_unpushed_count ?? 0) !== 1 ? "s" : ""} ready to push
                  </span>
                  {unpushedLastPush && (
                    <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 8 }}>
                      since {unpushedLastPush.slice(0, 16).replace("T", " ")}
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {unpushedTotal > 0 && (
                    <Link
                      to={`/sessions?org_id=${orgId}&is_local=true`}
                      style={{ fontSize: 12, color: "var(--text-muted)" }}
                    >
                      View all &rarr;
                    </Link>
                  )}
                  <button
                    className="btn"
                    style={{ fontSize: 12 }}
                    disabled={pushing || (org.judged_unpushed_count ?? 0) === 0 || !!batchJobId}
                    onClick={async () => {
                      setPushing(true);
                      setPushResult(null);
                      try {
                        const res = await api.pushOrg(orgId!);
                        setPushResult(`Pushed ${res.received_sessions ?? 0} sessions`);
                        load();
                      } catch (e) {
                        setPushResult(`Error: ${(e as Error).message}`);
                      } finally {
                        setPushing(false);
                      }
                    }}
                  >
                    {pushing ? "Pushing..." : "Push"}
                  </button>
                </div>
              </div>

              {/* Needs judging indicator */}
              {(org.needs_judging_count ?? 0) > 0 && (
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
                    <span style={{
                      display: "inline-block",
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      border: "1.5px solid var(--border)",
                      background: "transparent",
                    }} />
                    <span style={{ color: "var(--text-muted)" }}>{org.needs_judging_count} need{org.needs_judging_count === 1 ? "s" : ""} judging</span>
                  </div>
                  {unpushedTotal > 0 && (
                    <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {unpushedTotal} total unpushed
                    </span>
                  )}
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: 11, padding: "3px 10px" }}
                    disabled={judgingBeforePush || !!batchJobId}
                    onClick={async () => {
                      const needJudging = unpushedSessions.filter(s => !s.judge_current);
                      if (needJudging.length === 0) return;
                      setJudgingBeforePush(true);
                      try {
                        const res = await api.runBatchAsync(
                          ["transcript-compact", "llm-time-estimate"],
                          needJudging.map(s => s.session_id),
                        );
                        if (res.job_id) {
                          setBatchJobId(res.job_id);
                          window.dispatchEvent(new Event("job-created"));
                        }
                      } catch { /* ignore */ }
                      finally {
                        setJudgingBeforePush(false);
                      }
                    }}
                  >
                    {judgingBeforePush ? "Starting..." : "Judge before push"}
                  </button>
                </div>
              )}

              {batchJobId && (
                <JobProgress
                  jobId={batchJobId}
                  onProgress={load}
                  onComplete={() => {
                    setBatchJobId(null);
                    load();
                  }}
                />
              )}

              {unpushedTotal === 0 && (
                <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
                  All sessions synced. Nothing new to push.
                </div>
              )}
            </div>
          </div>

          {/* PULL section */}
          <div className="chart-card" style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>Pull</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  Last pull: {membership.last_pull_at
                    ? new Date(membership.last_pull_at).toLocaleString()
                    : "Never"}
                </div>
              </div>
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12 }}
                disabled={pulling}
                onClick={async () => {
                  setPulling(true);
                  setPullResult(null);
                  try {
                    const res = await api.pullOrg(orgId!);
                    const stored = (res.stored_sessions as number) ?? 0;
                    const now = new Date().toLocaleString();
                    setPullResult(stored > 0 ? `Pulled ${stored} sessions at ${now}` : `Aggregates updated at ${now}`);
                    load();
                  } catch (e) {
                    setPullResult(`Error: ${(e as Error).message}`);
                  } finally {
                    setPulling(false);
                  }
                }}
              >
                {pulling ? "Pulling..." : "Pull"}
              </button>
            </div>

            {pullResult && (
              <div style={{ fontSize: 12, color: pullResult.startsWith("Error") ? "#dc2626" : "#16a34a", marginTop: 8 }}>
                {pullResult}
              </div>
            )}

            {/* What you pull */}
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 12 }}>
                <span style={{ fontWeight: 500, color: "var(--text-muted)", whiteSpace: "nowrap" }}>Pulling:</span>
                {(() => {
                  const effective = pullConfig || sharingConfig;
                  if (!effective) return null;
                  return (
                    <>
                      {Object.entries(effective.stats).filter(([, v]) => v).map(([key]) => (
                        <span key={key} style={{
                          padding: "2px 8px",
                          background: "var(--bg-hover)",
                          borderRadius: 4,
                          color: "var(--text-muted)",
                        }}>
                          {key.replace(/_/g, " ")}
                        </span>
                      ))}
                      <span style={{
                        padding: "2px 8px",
                        background: "var(--bg-hover)",
                        borderRadius: 4,
                        color: "var(--text-muted)",
                      }}>
                        {effective.level >= 2 ? "per-session" : "aggregates only"}
                      </span>
                    </>
                  );
                })()}
                <span style={{ flex: 1 }} />
                <Link
                  to={`/organizations/${orgId}/settings`}
                  style={{ fontSize: 12, color: "var(--text-muted)", whiteSpace: "nowrap" }}
                >
                  Settings &rarr;
                </Link>
              </div>
              {(org.pulled_session_count ?? 0) > 0 && (
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>
                  {org.pulled_session_count} session{org.pulled_session_count !== 1 ? "s" : ""} pulled so far
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* ===== CHARTS (both modes) ===== */}

      {/* Member: Uplift by Project chart */}
      {isMember && byProject.length > 0 && (
        <div className="chart-card" style={{ marginTop: 24, marginBottom: 16 }}>
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

      {/* Distribution chart */}
      {distribution && distribution.values && distribution.values.length > 0 && (
        <div style={{ marginTop: 16, marginBottom: 16 }}>
          <UpliftDistributionChart
            values={distribution.values}
            failCount={0}
            stats={distribution.stats}
          />
        </div>
      )}

      {/* Scaffold + Model charts */}
      <div className="chart-grid" style={{ marginBottom: 24 }}>
        {byScaffold.length > 0 && (
          <div className="chart-card">
            <h3>Uplift by Scaffold</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={byScaffold}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis dataKey="scaffold" tick={{ fill: "#666", fontSize: 11 }} />
                <YAxis tick={{ fill: "#666", fontSize: 11 }} tickFormatter={(v) => `${v}x`} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #e0e0e0" }}
                  formatter={(v: number) => [`${v}x`, "Avg Uplift"]}
                />
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
                <XAxis
                  dataKey="model"
                  tick={{ fill: "#666", fontSize: 11 }}
                  tickFormatter={(v) => v?.replace("claude-", "") || "unknown"}
                />
                <YAxis tick={{ fill: "#666", fontSize: 11 }} tickFormatter={(v) => `${v}x`} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #e0e0e0" }}
                  formatter={(v: number) => [`${v}x`, "Avg Uplift"]}
                />
                <Bar dataKey="avg_uplift" fill="#ec4899" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Folders Table — at the bottom */}
      <h3 style={{ margin: "8px 0 12px", color: "var(--text-muted)" }}>Folders</h3>
      <div className="chart-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {org.folders.length} folder{org.folders.length !== 1 ? "s" : ""} assigned
          </span>
          <button className="btn" style={{ fontSize: 12, padding: "4px 12px" }} onClick={openAddFolder}>
            Add Folder
          </button>
        </div>
        {org.folders.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Path</th>
                <th>Added</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {org.folders.map((f) => (
                <tr key={f.folder_path}>
                  <td style={{ fontFamily: "monospace", fontSize: 12 }}>{f.folder_path}</td>
                  <td>{new Date(f.added_at).toLocaleDateString()}</td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: "2px 8px", fontSize: 11 }}
                      onClick={() => handleRemoveFolder(f.folder_path)}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            No folders assigned yet. Add folders to start tracking org-level analytics.
          </div>
        )}
      </div>

      {/* Add Folder Modal */}
      {showAddFolder && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.4)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
          }}
          onMouseDown={() => setShowAddFolder(false)}
        >
          <div
            className="chart-card"
            style={{ width: 480, maxHeight: "80vh", overflow: "auto" }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>Add Folders</h3>
            <div
              style={{
                maxHeight: 300,
                overflow: "auto",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: 8,
                marginBottom: 12,
              }}
            >
              {projects
                .filter((p) => p.project_path && !existingPaths.has(p.project_path))
                .map((p) => (
                  <label
                    key={p.project_path}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "4px 0",
                      cursor: "pointer",
                      fontSize: 13,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedFolders.includes(p.project_path!)}
                      onChange={() =>
                        setSelectedFolders((prev) =>
                          prev.includes(p.project_path!)
                            ? prev.filter((x) => x !== p.project_path)
                            : [...prev, p.project_path!]
                        )
                      }
                    />
                    <span>{p.project_name}</span>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {p.project_path}
                    </span>
                  </label>
                ))}
            </div>
            {addError && (
              <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 8 }}>{addError}</div>
            )}
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={() => setShowAddFolder(false)}>
                Cancel
              </button>
              <button
                className="btn"
                onClick={handleAddFolders}
                disabled={addingFolders || selectedFolders.length === 0}
              >
                {addingFolders ? "Adding..." : `Add ${selectedFolders.length} Folder${selectedFolders.length !== 1 ? "s" : ""}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
