import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmt, Project, Organization, UpliftByGroup } from "../api.ts";

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [search, setSearch] = useState("");
  const [subfolders, setSubfolders] = useState<Record<string, boolean>>({});
  const [overrides, setOverrides] = useState<Record<string, Partial<Project>>>({});
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [orgMenuFor, setOrgMenuFor] = useState<string | null>(null);
  const [upliftByProject, setUpliftByProject] = useState<Record<string, number>>({});
  const navigate = useNavigate();

  useEffect(() => {
    api.projects().then(setProjects);
    api.organizations().then(setOrgs);
    api.upliftByProject("llm-judge").then((data: UpliftByGroup[]) => {
      const map: Record<string, number> = {};
      for (const d of data) {
        if (d.project_name) map[d.project_name] = d.avg_uplift;
      }
      setUpliftByProject(map);
    }).catch(() => {});
  }, []);

  const handleSetOrg = async (project: Project, orgId: string | null) => {
    setOrgMenuFor(null);
    if (!project.project_path) return;
    try {
      // Remove from current org if assigned
      if (project.org_id) {
        await api.removeOrgFolders(project.org_id, [project.project_path]);
      }
      // Add to new org if not "Personal"
      if (orgId) {
        await api.addOrgFolders(orgId, [project.project_path]);
      }
      api.projects().then(setProjects);
    } catch (e) {
      alert((e as Error).message);
    }
  };

  const handleToggle = (p: Project) => {
    const newValue = !subfolders[p.project_name];
    setSubfolders((s) => ({ ...s, [p.project_name]: newValue }));
    if (newValue && p.project_path) {
      api.projectStats(p.project_path).then((stats) => {
        setOverrides((o) => ({ ...o, [p.project_name]: stats }));
      });
    }
  };

  const getStats = (p: Project): Project => {
    if (subfolders[p.project_name] && overrides[p.project_name]) {
      return { ...p, ...overrides[p.project_name] };
    }
    return p;
  };

  const filtered = projects.filter((p) =>
    p.project_name.toLowerCase().includes(search.toLowerCase())
  );

  const handleCardClick = (p: Project) => {
    if (subfolders[p.project_name] && p.project_path) {
      navigate(
        `/sessions?project_path=${encodeURIComponent(p.project_path)}&subfolders=true&project=${encodeURIComponent(p.project_name)}`
      );
    } else {
      navigate(`/sessions?project=${encodeURIComponent(p.project_name)}`);
    }
  };

  return (
    <div>
      <h2 className="page-title">Projects ({projects.length})</h2>
      <div style={{ marginBottom: 20 }}>
        <input
          type="text"
          placeholder="Search projects..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="search-input"
        />
      </div>
      {filtered.length === 0 ? (
        <div className="empty">
          {search ? "No projects match your search." : "No projects yet. Run `open-uplift sync` to ingest data."}
        </div>
      ) : (
        <div className="project-grid">
          {filtered.map((p) => {
            const s = getStats(p);
            return (
            <div
              key={p.project_name}
              className="project-card"
              onClick={() => handleCardClick(p)}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div className="project-name">{p.project_name}</div>
                <div style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
                  <span
                    style={{
                      fontSize: 10,
                      padding: "2px 6px",
                      background: !p.org_id
                        ? "#dbeafe"
                        : p.org_mode === "hub" ? "#ede9fe"
                        : p.org_mode === "member" ? "#fef3c7"
                        : "#f3f4f6",
                      color: !p.org_id
                        ? "#2563eb"
                        : p.org_mode === "hub" ? "#6d28d9"
                        : p.org_mode === "member" ? "#92400e"
                        : "#6b7280",
                      borderRadius: 4,
                      fontWeight: 600,
                      whiteSpace: "nowrap",
                      cursor: "pointer",
                      userSelect: "none",
                    }}
                    onClick={() => setOrgMenuFor(orgMenuFor === p.project_name ? null : p.project_name)}
                  >
                    {p.org_name || "Personal"}
                  </span>
                  {orgMenuFor === p.project_name && (
                    <>
                      <div style={{ position: "fixed", inset: 0, zIndex: 49 }} onClick={() => setOrgMenuFor(null)} />
                      <div style={{
                        position: "absolute",
                        left: 0,
                        top: "100%",
                        marginTop: 4,
                        background: "var(--bg)",
                        border: "1px solid var(--border)",
                        borderRadius: 6,
                        boxShadow: "0 4px 16px rgba(0,0,0,0.12)",
                        minWidth: 140,
                        zIndex: 50,
                        overflow: "hidden",
                      }}>
                        <div
                          onClick={() => handleSetOrg(p, null)}
                          style={{
                            padding: "7px 12px",
                            fontSize: 12,
                            cursor: "pointer",
                            color: "#2563eb",
                            fontWeight: !p.org_id ? 600 : 400,
                            background: !p.org_id ? "var(--bg-hover)" : undefined,
                          }}
                          onMouseEnter={(e) => e.currentTarget.style.background = "var(--bg-hover)"}
                          onMouseLeave={(e) => e.currentTarget.style.background = !p.org_id ? "var(--bg-hover)" : ""}
                        >
                          Personal
                        </div>
                        {orgs.map((o) => (
                          <div
                            key={o.org_id}
                            onClick={() => handleSetOrg(p, o.org_id)}
                            style={{
                              padding: "7px 12px",
                              fontSize: 12,
                              cursor: "pointer",
                              fontWeight: p.org_id === o.org_id ? 600 : 400,
                              background: p.org_id === o.org_id ? "var(--bg-hover)" : undefined,
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.background = "var(--bg-hover)"}
                            onMouseLeave={(e) => e.currentTarget.style.background = p.org_id === o.org_id ? "var(--bg-hover)" : ""}
                          >
                            {o.name}
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>
              <div className="project-path">{p.project_path || ""}</div>
              <label
                className="toggle-row"
                onClick={(e) => e.stopPropagation()}
              >
                <span className="toggle-label">Incl. subfolders</span>
                <div
                  className={`toggle ${subfolders[p.project_name] ? "toggle-on" : ""}`}
                  onClick={() => handleToggle(p)}
                >
                  <div className="toggle-knob" />
                </div>
              </label>
              <div className="project-stats">
                <div className="project-stat">
                  <span className="project-stat-value" style={{ color: upliftByProject[p.project_name] ? "#16a34a" : undefined }}>
                    {upliftByProject[p.project_name] ? `${upliftByProject[p.project_name]}x` : "\u2014"}
                  </span>
                  <span className="project-stat-label">Uplift</span>
                </div>
                <div className="project-stat">
                  <span className="project-stat-value">{s.session_count.toLocaleString()}</span>
                  <span className="project-stat-label">Sessions</span>
                </div>
                <div className="project-stat">
                  <span
                    className="project-stat-value"
                    onClick={(e) => {
                      e.stopPropagation();
                      const params = new URLSearchParams();
                      params.set("project", p.project_name);
                      if (p.project_path) params.set("project_path", p.project_path);
                      if (subfolders[p.project_name]) params.set("subfolders", "true");
                      navigate(`/tokens?${params}`);
                    }}
                    style={{ cursor: "pointer", textDecoration: "underline", textDecorationColor: "#e0e0e0", textUnderlineOffset: 2 }}
                  >
                    {fmt(s.total_tokens)}
                  </span>
                  <span className="project-stat-label">Tokens</span>
                </div>
                <div className="project-stat">
                  <span className="project-stat-value">{s.total_messages.toLocaleString()}</span>
                  <span className="project-stat-label">Messages</span>
                </div>
              </div>
              <div className="project-meta">
                Last active: {new Date(s.last_active).toLocaleDateString()}
              </div>
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
