import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, Organization, Project, OrgMembership, OrgHubInfo } from "../api.ts";

const MODE_LABELS: Record<string, string> = {
  hub: "Hub",
  member: "Member",
};

const MODE_COLORS: Record<string, { bg: string; color: string }> = {
  hub: { bg: "#ede9fe", color: "#6d28d9" },
  member: { bg: "#fef3c7", color: "#92400e" },
};

export default function Organizations() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const navigate = useNavigate();

  // Hub info per org
  const [memberships, setMemberships] = useState<Record<string, OrgMembership>>({});
  const [hubInfos, setHubInfos] = useState<Record<string, OrgHubInfo>>({});

  // Create modal state
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedFolders, setSelectedFolders] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Join modal state
  const [showJoin, setShowJoin] = useState(false);
  const [joinHubUrl, setJoinHubUrl] = useState("");
  const [joinInviteCode, setJoinInviteCode] = useState("");
  const [joinName, setJoinName] = useState("");
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);

  useEffect(() => {
    api.organizations().then((orgs) => {
      setOrgs(orgs);
      for (const org of orgs) {
        api.organizationHubInfo(org.org_id).then((info) => {
          if (info.members.length > 0) {
            setHubInfos((prev) => ({ ...prev, [org.org_id]: info }));
          }
        }).catch(() => {});
      }
    });
    api.orgMemberships().then((ms) => {
      const byId: Record<string, OrgMembership> = {};
      for (const m of ms) byId[m.org_id] = m;
      setMemberships(byId);
    }).catch(() => {});
  }, []);

  const openCreate = () => {
    setShowCreate(true);
    setNewName("");
    setNewDesc("");
    setSelectedFolders([]);
    setError(null);
    api.projects().then(setProjects);
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const result = await api.createOrganization(
        newName.trim(),
        newDesc.trim() || undefined,
        selectedFolders.length > 0 ? selectedFolders : undefined,
      );
      setShowCreate(false);
      navigate(`/organizations/${result.org_id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const toggleFolder = (path: string) => {
    setSelectedFolders((prev) =>
      prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path]
    );
  };

  const openJoin = () => {
    setShowJoin(true);
    setJoinHubUrl("");
    setJoinInviteCode("");
    setJoinName("");
    setJoinError(null);
  };

  const handleJoin = async () => {
    if (!joinHubUrl.trim() || !joinInviteCode.trim() || !joinName.trim()) return;
    setJoining(true);
    setJoinError(null);
    try {
      const result = await api.joinOrg(joinHubUrl.trim(), joinInviteCode.trim(), joinName.trim());
      setShowJoin(false);
      navigate(`/organizations/${result.org_id}`);
    } catch (e) {
      setJoinError((e as Error).message);
    } finally {
      setJoining(false);
    }
  };

  const filtered = orgs.filter(
    (o) =>
      o.name.toLowerCase().includes(search.toLowerCase()) ||
      o.description.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <h2 className="page-title" style={{ margin: 0 }}>Organizations ({orgs.length})</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-secondary" onClick={openJoin}>
            Join Hub
          </button>
          <button className="btn" onClick={openCreate}>
            New Organization
          </button>
        </div>
      </div>

      <div style={{ marginBottom: 20 }}>
        <input
          type="text"
          placeholder="Search organizations..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="search-input"
        />
      </div>

      {filtered.length === 0 ? (
        <div className="empty">
          {search ? "No organizations match your search." : "No organizations yet."}
        </div>
      ) : (
        <div className="project-grid">
          {filtered.map((org) => {
            const hub = hubInfos[org.org_id];
            const mem = memberships[org.org_id];
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
                  <span
                    style={{
                      fontSize: 10,
                      padding: "2px 6px",
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
                        fontSize: 10,
                        padding: "2px 6px",
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
                  <div className="project-path">{org.description}</div>
                )}
                <div className="project-stats" style={{ marginTop: 12 }}>
                  {mode === "hub" ? (
                    <div className="project-stat">
                      <span className="project-stat-value">{hub?.members.length ?? 0}</span>
                      <span className="project-stat-label">Members</span>
                    </div>
                  ) : (
                    <div className="project-stat">
                      <span className="project-stat-value" style={{ fontSize: 14 }}>Hub</span>
                      <span className="project-stat-label">Connected</span>
                    </div>
                  )}
                </div>
                <div className="project-meta">
                  Created: {new Date(org.created_at).toLocaleDateString()}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Modal */}
      {showCreate && (
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
          onMouseDown={() => setShowCreate(false)}
        >
          <div
            className="chart-card"
            style={{ width: 480, maxHeight: "80vh", overflow: "auto" }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>New Organization</h3>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Name</label>
                <input
                  className="search-input"
                  placeholder="Organization name"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  style={{ marginTop: 4 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Description</label>
                <input
                  className="search-input"
                  placeholder="Optional description"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  style={{ marginTop: 4 }}
                />
              </div>

              {/* Folder picker — always shown when projects exist */}
              {projects.length > 0 && (
                <div>
                  <label style={{ fontSize: 13, fontWeight: 500 }}>
                    Assign Folders ({selectedFolders.length} selected)
                    <span style={{ fontWeight: 400, color: "var(--text-muted)" }}> — optional</span>
                  </label>
                  <div
                    style={{
                      marginTop: 4,
                      maxHeight: 200,
                      overflow: "auto",
                      border: "1px solid var(--border)",
                      borderRadius: 6,
                      padding: 8,
                    }}
                  >
                    {projects
                      .filter((p) => p.project_path)
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
                            onChange={() => toggleFolder(p.project_path!)}
                          />
                          <span>{p.project_name}</span>
                          <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                            {p.project_path}
                          </span>
                        </label>
                      ))}
                  </div>
                </div>
              )}

              {error && (
                <div style={{ color: "#dc2626", fontSize: 13 }}>{error}</div>
              )}

              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => setShowCreate(false)}
                >
                  Cancel
                </button>
                <button
                  className="btn"
                  onClick={handleCreate}
                  disabled={creating || !newName.trim()}
                >
                  {creating ? "Creating..." : "Create"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Join Hub Modal */}
      {showJoin && (
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
          onMouseDown={() => setShowJoin(false)}
        >
          <div
            className="chart-card"
            style={{ width: 420, maxHeight: "80vh", overflow: "auto" }}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h3 style={{ marginTop: 0 }}>Join Hub</h3>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Hub URL</label>
                <input
                  className="search-input"
                  placeholder="e.g. https://hub.example.com"
                  value={joinHubUrl}
                  onChange={(e) => { setJoinHubUrl(e.target.value); setJoinError(null); }}
                  style={{ marginTop: 4 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Invite Code</label>
                <input
                  className="search-input"
                  placeholder="Paste invite code"
                  value={joinInviteCode}
                  onChange={(e) => { setJoinInviteCode(e.target.value); setJoinError(null); }}
                  style={{ marginTop: 4 }}
                />
              </div>
              <div>
                <label style={{ fontSize: 13, fontWeight: 500 }}>Your Name</label>
                <input
                  className="search-input"
                  placeholder="Display name"
                  value={joinName}
                  onChange={(e) => setJoinName(e.target.value)}
                  style={{ marginTop: 4 }}
                />
              </div>

              {joinError && (
                <div style={{ color: "#dc2626", fontSize: 13 }}>{joinError}</div>
              )}

              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => setShowJoin(false)}
                >
                  Cancel
                </button>
                <button
                  className="btn"
                  onClick={handleJoin}
                  disabled={joining || !joinHubUrl.trim() || !joinInviteCode.trim() || !joinName.trim()}
                >
                  {joining ? "Joining..." : "Join"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
