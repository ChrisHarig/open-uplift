import { useEffect, useState, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api, OrgDetail, OrgMembership, OrgHubInfo, SharingConfig, RunModeConfig } from "../api.ts";
import SharingConfigDisplay from "../components/SharingConfigDisplay.tsx";
import InfoTip from "../components/InfoTip.tsx";

const STAT_LABELS: Record<string, string> = {
  tokens: "Tokens",
  cost: "Cost",
  messages: "Messages",
  tool_calls: "Tool calls",
  uplift: "Uplift",
  compacted_transcripts: "Compacted transcripts",
  full_transcripts: "Full transcripts",
};

const DEFAULT_SHARING: SharingConfig = {
  level: 1,
  stats: { tokens: true, cost: true, messages: true, tool_calls: true, uplift: true, compacted_transcripts: false, full_transcripts: false },
};

export default function OrganizationSettings() {
  const { orgId } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const [org, setOrg] = useState<OrgDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);

  // Org membership / hub data
  const [membership, setMembership] = useState<OrgMembership | null>(null);
  const [sharingConfig, setSharingConfig] = useState<SharingConfig | null>(null);
  const [hubInfo, setHubInfo] = useState<OrgHubInfo | null>(null);

  // Sharing config editing
  const [editingConfig, setEditingConfig] = useState<SharingConfig | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);

  // Pull config (member)
  const [pullConfig, setPullConfig] = useState<SharingConfig | null>(null);
  const [savingPullConfig, setSavingPullConfig] = useState(false);

  // Run mode config (sync schedule)
  const [runConfig, setRunConfig] = useState<RunModeConfig | null>(null);
  const [savingRunConfig, setSavingRunConfig] = useState(false);

  // Name/description editing
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [savingOrg, setSavingOrg] = useState(false);
  const [orgDirty, setOrgDirty] = useState(false);

  // Invite management
  const [generatingInvite, setGeneratingInvite] = useState(false);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!orgId) return;
    api.organizationDetail(orgId).then((o) => {
      setOrg(o);
      setEditName(o.name);
      setEditDesc(o.description);
    }).catch((e) => setError(e.message));
    api.organizationHubInfo(orgId).then(setHubInfo).catch(() => {});
    api.getRunModeConfig().then(setRunConfig).catch(() => {});
    api.orgMemberships().then((memberships) => {
      const m = memberships.find((ms) => ms.org_id === orgId);
      setMembership(m || null);
      if (m?.sharing_config) {
        try {
          setSharingConfig(JSON.parse(m.sharing_config));
        } catch { /* ignore */ }
      }
    }).catch(() => {});
    api.pullConfig(orgId).then((data) => {
      if (data.pull_config) setPullConfig(data.pull_config);
    }).catch(() => {});
  }, [orgId]);

  useEffect(load, [load]);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedCode(text);
      setTimeout(() => setCopiedCode(null), 2000);
    });
  };

  const handleSaveSharingConfig = async () => {
    if (!orgId || !editingConfig) return;
    setSavingConfig(true);
    try {
      await api.updateSharingConfig(orgId, editingConfig);
      setSharingConfig(editingConfig);
      setEditingConfig(null);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setSavingConfig(false);
    }
  };

  const saveRunConfig = async (newConfig: RunModeConfig) => {
    setSavingRunConfig(true);
    try {
      const saved = await api.setRunModeConfig(newConfig);
      setRunConfig(saved);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setSavingRunConfig(false);
    }
  };

  const handleSavePullConfig = async (config: SharingConfig) => {
    if (!orgId) return;
    setSavingPullConfig(true);
    try {
      const res = await api.updatePullConfig(orgId, config);
      setPullConfig(res.pull_config);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setSavingPullConfig(false);
    }
  };

  const handleSaveOrg = async () => {
    if (!orgId) return;
    setSavingOrg(true);
    try {
      await api.updateOrganization(orgId, { name: editName, description: editDesc });
      setOrgDirty(false);
      load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setSavingOrg(false);
    }
  };

  if (error) return <div className="empty">{error}</div>;
  if (!org) return <div className="empty">Loading...</div>;

  const mode = org.org_mode || "hub";
  const isHub = mode === "hub";
  const isMember = mode === "member";
  const isAdmin = isHub && hubInfo && hubInfo.members.length > 0;
  const currentSharing = sharingConfig || hubInfo?.sharing_config || DEFAULT_SHARING;

  return (
    <div>
      {/* Back link */}
      <Link to={`/organizations/${orgId}`} className="transcript-back" style={{ marginBottom: 16, display: "inline-block" }}>
        &larr; {org.name}
      </Link>

      <h2 className="page-title" style={{ marginBottom: 24 }}>Organization Settings</h2>

      {/* General section */}
      <div className="chart-card" style={{ marginBottom: 24 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>General</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Name</label>
            <input
              className="search-input"
              style={{ fontSize: 13, maxWidth: 400 }}
              value={editName}
              onChange={(e) => { setEditName(e.target.value); setOrgDirty(true); }}
            />
          </div>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Description</label>
            <input
              className="search-input"
              style={{ fontSize: 13, maxWidth: 400 }}
              value={editDesc}
              onChange={(e) => { setEditDesc(e.target.value); setOrgDirty(true); }}
              placeholder="Optional description"
            />
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Mode: <strong>{mode}</strong> &middot; Created: {new Date(org.created_at).toLocaleDateString()}
          </div>
          {orgDirty && (
            <div>
              <button className="btn" style={{ fontSize: 12 }} onClick={handleSaveOrg} disabled={savingOrg}>
                {savingOrg ? "Saving..." : "Save Changes"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Sharing Configuration — hub admin: full editor */}
      {isHub && (
        <div className="chart-card" style={{ marginBottom: 24 }}>
          <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
            Sharing Configuration
            <InfoTip text="Controls what data members share when pushing to the hub." />
          </h3>
          {editingConfig ? (
            <div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={editingConfig.stats.tokens}
                    onChange={(e) => setEditingConfig({ ...editingConfig, stats: { ...editingConfig.stats, tokens: e.target.checked } })}
                  />
                  Tokens
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={editingConfig.stats.cost}
                    onChange={(e) => setEditingConfig({ ...editingConfig, stats: { ...editingConfig.stats, cost: e.target.checked } })}
                  />
                  Cost
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={editingConfig.stats.messages}
                    onChange={(e) => setEditingConfig({ ...editingConfig, stats: { ...editingConfig.stats, messages: e.target.checked } })}
                  />
                  Messages
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={editingConfig.stats.tool_calls}
                    onChange={(e) => setEditingConfig({ ...editingConfig, stats: { ...editingConfig.stats, tool_calls: e.target.checked } })}
                  />
                  Tool Calls
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={editingConfig.stats.uplift}
                    onChange={(e) => setEditingConfig({ ...editingConfig, stats: { ...editingConfig.stats, uplift: e.target.checked } })}
                  />
                  Uplift
                </label>
                <div style={{ marginTop: 8 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                    <input
                      type="checkbox"
                      checked={editingConfig.level >= 2}
                      onChange={(e) => setEditingConfig({ ...editingConfig, level: e.target.checked ? 2 : 1 })}
                    />
                    Session-level sharing (share individual sessions, not just aggregates)
                  </label>
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn" onClick={handleSaveSharingConfig} disabled={savingConfig}>
                  {savingConfig ? "Saving..." : "Save"}
                </button>
                <button className="btn btn-secondary" onClick={() => setEditingConfig(null)}>Cancel</button>
              </div>
            </div>
          ) : (
            <div>
              <SharingConfigDisplay config={currentSharing} />
              <button
                className="btn btn-secondary"
                style={{ marginTop: 8, fontSize: 12 }}
                onClick={() => setEditingConfig({ ...currentSharing })}
              >
                Edit
              </button>
            </div>
          )}
        </div>
      )}

      {/* Member: Push config (read-only pills) + Pull config (editable toggles) */}
      {isMember && (
        <>
          {/* Push: read-only summary of what admin requires */}
          <div className="chart-card" style={{ marginBottom: 24 }}>
            <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
              Data Shared Per Push
              <span style={{
                marginLeft: 8,
                fontSize: 10,
                fontWeight: 500,
                padding: "2px 6px",
                background: "var(--bg-hover)",
                color: "var(--text-muted)",
                borderRadius: 3,
                verticalAlign: "middle",
              }}>
                Set by Admin
              </span>
            </h3>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              {Object.entries(currentSharing.stats).filter(([, v]) => v).map(([key]) => (
                <span key={key} style={{
                  fontSize: 12,
                  padding: "3px 10px",
                  background: "var(--bg-hover)",
                  borderRadius: 4,
                  color: "var(--text-muted)",
                }}>
                  {STAT_LABELS[key] || key.replace(/_/g, " ")}
                </span>
              ))}
              <span style={{
                fontSize: 12,
                padding: "3px 10px",
                background: currentSharing.level >= 2 ? "#ede9fe" : "var(--bg-hover)",
                color: currentSharing.level >= 2 ? "#6d28d9" : "var(--text-muted)",
                borderRadius: 4,
              }}>
                {currentSharing.level >= 2 ? "Per-session" : "Aggregates only"}
              </span>
            </div>
          </div>

          {/* Pull: editable toggles for what member wants to receive */}
          <div className="chart-card" style={{ marginBottom: 24 }}>
            <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
              Pull Configuration
              <InfoTip text="Choose what data to pull from the hub. You can receive up to what the admin shares." />
            </h3>
            {(() => {
              const effective = pullConfig || currentSharing;
              return (
                <div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 12 }}>
                    {Object.entries(STAT_LABELS).map(([key, label]) => {
                      const offered = currentSharing.stats[key as keyof typeof currentSharing.stats];
                      if (!offered) return null;
                      const enabled = effective.stats[key as keyof typeof effective.stats] ?? true;
                      return (
                        <label key={key} className="toggle-row" style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                          <div
                            className={`toggle ${enabled ? "toggle-on" : ""}`}
                            onClick={() => {
                              const updated = {
                                ...effective,
                                stats: { ...effective.stats, [key]: !enabled },
                              };
                              setPullConfig(updated);
                              handleSavePullConfig(updated);
                            }}
                            style={{ opacity: savingPullConfig ? 0.5 : 1 }}
                          >
                            <div className="toggle-knob" />
                          </div>
                          <span style={{ fontSize: 13 }}>{label}</span>
                        </label>
                      );
                    })}
                    {currentSharing.level >= 2 && (
                      <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--border)" }}>
                        <label className="toggle-row" style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                          <div
                            className={`toggle ${(effective.level >= 2) ? "toggle-on" : ""}`}
                            onClick={() => {
                              const updated = {
                                ...effective,
                                level: effective.level >= 2 ? 1 : 2,
                              };
                              setPullConfig(updated);
                              handleSavePullConfig(updated);
                            }}
                            style={{ opacity: savingPullConfig ? 0.5 : 1 }}
                          >
                            <div className="toggle-knob" />
                          </div>
                          <span style={{ fontSize: 13 }}>Pull per-session summaries</span>
                        </label>
                      </div>
                    )}
                  </div>
                </div>
              );
            })()}
          </div>
        </>
      )}

      {/* Sync Settings — member mode */}
      {isMember && membership && (
        <div className="chart-card" style={{ marginBottom: 24 }}>
          <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>Sync Settings</h3>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 12 }}>
            {membership.hub_url && <>Hub: <strong>{membership.hub_url}</strong></>}
          </div>
          <div style={{ display: "flex", gap: 24, marginBottom: 12, flexWrap: "wrap" }}>
            <div style={{ fontSize: 12 }}>
              <span style={{ color: "var(--text-muted)" }}>Last push: </span>
              {membership.last_push_at
                ? membership.last_push_at.slice(0, 16).replace("T", " ")
                : <span style={{ color: "var(--text-muted)" }}>Never</span>}
            </div>
            <div style={{ fontSize: 12 }}>
              <span style={{ color: "var(--text-muted)" }}>Last pull: </span>
              {membership.last_pull_at
                ? membership.last_pull_at.slice(0, 16).replace("T", " ")
                : <span style={{ color: "var(--text-muted)" }}>Never</span>}
            </div>
          </div>

          {/* Auto-sync schedule */}
          {runConfig && (
            <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 12 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                <div
                  className={`toggle ${runConfig.enabled ? "toggle-on" : ""}`}
                  onClick={() => saveRunConfig({ ...runConfig, enabled: !runConfig.enabled })}
                >
                  <div className="toggle-knob" />
                </div>
                <div>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>
                    Auto-sync schedule
                    <InfoTip text="Automatically push and pull on a schedule. Also triggers batch compaction + judge." />
                  </div>
                </div>
              </label>
              {runConfig.enabled && (
                <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 8, fontSize: 12 }}>
                  <span>At</span>
                  <select
                    value={runConfig.start_hour}
                    onChange={(e) => saveRunConfig({ ...runConfig, start_hour: parseInt(e.target.value) })}
                    style={{ width: 96 }}
                    disabled={savingRunConfig}
                  >
                    {Array.from({ length: 24 }, (_, i) => (
                      <option key={i} value={i}>{i.toString().padStart(2, "0")}:00</option>
                    ))}
                  </select>
                  <span>every</span>
                  <input
                    type="number"
                    className="search-input"
                    style={{ width: 80 }}
                    min={0.1}
                    step={0.5}
                    value={runConfig.frequency_hours}
                    onChange={(e) => saveRunConfig({ ...runConfig, frequency_hours: Math.max(0.1, parseFloat(e.target.value) || 0.1) })}
                    disabled={savingRunConfig}
                  />
                  <span>hrs</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Invite Code section — hub admin only */}
      {isAdmin && (() => {
        const activeInvites = hubInfo!.invites.filter((i) => !i.revoked_at);
        const activeInvite = activeInvites[0] || null;
        return (
          <div className="chart-card" style={{ marginBottom: 24 }}>
            <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
              Invite Code
              <InfoTip text="Only one invite code is active at a time. Creating a new code automatically revokes the previous one." />
            </h3>

            {activeInvite && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <code style={{ fontSize: 13, padding: "4px 8px", background: "var(--bg-hover)", borderRadius: 4 }}>
                  {activeInvite.invite_code}
                </code>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 11, padding: "2px 8px" }}
                  onClick={() => copyToClipboard(activeInvite.invite_code)}
                >
                  {copiedCode === activeInvite.invite_code ? "Copied!" : "Copy"}
                </button>
              </div>
            )}

            <button
              className="btn btn-secondary"
              style={{ fontSize: 12 }}
              disabled={generatingInvite}
              onClick={async () => {
                if (!orgId) return;
                setGeneratingInvite(true);
                try {
                  // Revoke all active invites first
                  for (const inv of activeInvites) {
                    await api.revokeHubInvite(orgId, inv.invite_code);
                  }
                  await api.createHubInvite(orgId);
                  load();
                } catch (e) {
                  alert((e as Error).message);
                } finally {
                  setGeneratingInvite(false);
                }
              }}
            >
              {generatingInvite ? "Generating..." : "New Invite Code"}
            </button>
          </div>
        );
      })()}

      {/* Danger zone */}
      <div className="chart-card" style={{ borderColor: "#fecaca" }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "#dc2626" }}>Danger Zone</h3>
        <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "0 0 12px" }}>
          {isMember
            ? "Deleting this organization will disconnect from the hub and remove all folder associations. You will stop syncing with this organization."
            : "Deleting this organization will remove all folder associations, hub members, invite codes, and all synced session data. Members will no longer be able to sync."}
          {" "}This cannot be undone.
        </p>
        <button
          className="btn btn-secondary"
          style={{ color: "#dc2626" }}
          onClick={() => { setDeleteConfirmOpen(true); setDeleteConfirmText(""); }}
        >
          Delete Organization
        </button>
      </div>

      {/* Delete confirmation modal */}
      {deleteConfirmOpen && (
        <>
          <div
            onMouseDown={() => setDeleteConfirmOpen(false)}
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 100 }}
          />
          <div style={{
            position: "fixed",
            top: "30%",
            left: "50%",
            transform: "translate(-50%, -30%)",
            width: "min(440px, 90vw)",
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: 12,
            padding: "24px 28px",
            zIndex: 101,
            boxShadow: "0 16px 48px rgba(0,0,0,0.2)",
          }}>
            <h3 style={{ margin: "0 0 12px", color: "#dc2626" }}>Delete {org.name}?</h3>
            <p style={{ fontSize: 13, color: "var(--text-muted)", margin: "0 0 16px", lineHeight: 1.5 }}>
              {isMember
                ? "This will disconnect from the hub and stop all syncing. Your local sessions will be preserved."
                : "This will permanently delete the organization, all member connections, and all synced data."}
            </p>
            <label style={{ fontSize: 13, display: "block", marginBottom: 8 }}>
              Type <strong>{org.name}</strong> to confirm:
            </label>
            <input
              className="search-input"
              style={{ width: "100%", fontSize: 13, marginBottom: 16 }}
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              placeholder={org.name}
              autoFocus
            />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn btn-secondary" onClick={() => setDeleteConfirmOpen(false)}>
                Cancel
              </button>
              <button
                className="btn"
                style={{ background: "#dc2626", color: "#fff", opacity: deleteConfirmText === org.name ? 1 : 0.4 }}
                disabled={deleteConfirmText !== org.name || deleting}
                onClick={async () => {
                  if (!orgId || deleteConfirmText !== org.name) return;
                  setDeleting(true);
                  try {
                    await api.deleteOrganization(orgId);
                    navigate("/organizations");
                  } catch (e) {
                    alert((e as Error).message);
                    setDeleting(false);
                  }
                }}
              >
                {deleting ? "Deleting..." : "Delete Organization"}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
