import React, { useEffect, useState, useCallback } from "react";
import { useSearchParams, useNavigate, useLocation, Link } from "react-router-dom";
import { api, fmt, Session, SurveyResponse, FilterOptions, ScriptConfig, Organization } from "../api.ts";

type UpliftMap = Record<string, Record<string, number>>;
import ReportForm from "../components/ReportForm.tsx";
import JobProgress from "../components/JobProgress.tsx";

type ThreeWay = "" | "true" | "false";

export default function Sessions() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [total, setTotal] = useState(0);
  const [responses, setResponses] = useState<SurveyResponse[]>([]);
  const [upliftMap, setUpliftMap] = useState<UpliftMap>({});
  const [reportSession, setReportSession] = useState<Session | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();

  // Filter state
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [modelFilter, setModelFilter] = useState("");
  const [scaffoldFilter, setScaffoldFilter] = useState("");
  const [hasSurvey, setHasSurvey] = useState<ThreeWay>((searchParams.get("has_survey") as ThreeWay) || "");
  const [hasJudge, setHasJudge] = useState<ThreeWay>((searchParams.get("has_judge") as ThreeWay) || "");
  const [judgeSuccess, setJudgeSuccess] = useState<ThreeWay>((searchParams.get("judge_success") as ThreeWay) || "");
  const [isLocal, setIsLocal] = useState<ThreeWay>((searchParams.get("is_local") as ThreeWay) || "");
  const [sourceMember, setSourceMember] = useState(searchParams.get("source_member") || "");

  // Org filter state
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [orgFilter, setOrgFilter] = useState("");

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchJobId, setBatchJobId] = useState<string | null>(null);
  const [processingIds, setProcessingIds] = useState<Set<string>>(new Set());
  const [scriptConfig, setScriptConfig] = useState<ScriptConfig | null>(null);

  const projectFilter = searchParams.get("project") || "";
  const projectPath = searchParams.get("project_path") || "";
  const subfolders = searchParams.get("subfolders") === "true";

  useEffect(() => {
    api.sessionFilterOptions(orgFilter || undefined).then(setFilterOptions);
    api.getScriptConfig().then(setScriptConfig);
    api.organizations().then(setOrgs);
  }, [orgFilter]);

  const loadSessions = useCallback(() => {
    const opts: Record<string, string | boolean | undefined> = {};
    if (projectPath && subfolders) {
      opts.projectPath = projectPath;
      opts.subfolders = true;
    } else if (projectFilter) {
      opts.project = projectFilter;
    }
    if (dateFrom) opts.date_from = dateFrom;
    if (dateTo) opts.date_to = dateTo;
    if (modelFilter) opts.model = modelFilter;
    if (scaffoldFilter) opts.scaffold = scaffoldFilter;
    if (hasSurvey) opts.has_survey = hasSurvey;
    if (hasJudge) opts.has_judge = hasJudge;
    if (judgeSuccess) opts.judge_success = judgeSuccess;
    if (isLocal) opts.is_local = isLocal;
    if (orgFilter) opts.org_id = orgFilter;
    if (sourceMember) opts.source_member = sourceMember;

    api.sessions(100, 0, Object.keys(opts).length > 0 ? opts as Parameters<typeof api.sessions>[2] : undefined).then((d) => {
      setSessions(d.sessions);
      setTotal(d.total);
      setSelectedIds(new Set());
    });
  }, [projectFilter, projectPath, subfolders, dateFrom, dateTo, modelFilter, scaffoldFilter, hasSurvey, hasJudge, judgeSuccess, isLocal, orgFilter, sourceMember]);

  const loadResponses = useCallback(() => {
    api.surveyResponses().then(setResponses);
  }, []);

  const loadUpliftMap = useCallback(() => {
    api.upliftBySession().then(setUpliftMap);
  }, []);

  useEffect(() => {
    loadSessions();
    loadResponses();
    loadUpliftMap();
  }, [loadSessions, loadResponses, loadUpliftMap]);

  // Detect active jobs (e.g. triggered from org detail) and mark their sessions as processing
  useEffect(() => {
    const checkActiveJobs = () => {
      api.jobs("pending,running").then((jobs) => {
        if (jobs.length > 0 && !batchJobId) {
          const activeJob = jobs[0];
          const ids = activeJob.payload?.session_ids ?? [];
          if (ids.length > 0) {
            setBatchJobId(activeJob.id);
            setProcessingIds(new Set(ids));
          }
        }
      }).catch(() => {});
    };
    checkActiveJobs();
    const handler = () => checkActiveJobs();
    window.addEventListener("job-created", handler);
    return () => window.removeEventListener("job-created", handler);
  }, [batchJobId]);

  // Index responses by session_id
  const responsesBySession = new Map<string, SurveyResponse[]>();
  for (const r of responses) {
    if (!r.session_id) continue;
    const arr = responsesBySession.get(r.session_id) || [];
    arr.push(r);
    responsesBySession.set(r.session_id, arr);
  }

  const toggleSubfolders = () => {
    const params = new URLSearchParams(searchParams);
    if (subfolders) {
      params.delete("subfolders");
      params.delete("project_path");
    } else {
      const path = projectPath || sessions.find((s) => s.project_name === projectFilter)?.project_path;
      if (path) {
        params.set("project_path", path);
        params.set("subfolders", "true");
      }
    }
    setSearchParams(params);
  };

  const hasProjectFilter = projectFilter || projectPath;
  const hasAnyFilter = hasProjectFilter || dateFrom || dateTo || modelFilter || scaffoldFilter || hasSurvey || hasJudge || judgeSuccess || isLocal || orgFilter || sourceMember;

  const clearFilters = () => {
    setDateFrom("");
    setDateTo("");
    setModelFilter("");
    setScaffoldFilter("");
    setHasSurvey("");
    setHasJudge("");
    setJudgeSuccess("");
    setIsLocal("");
    setOrgFilter("");
    setSourceMember("");
    navigate("/sessions");
  };

  // Compute how many selected sessions need judging (compaction + judge as one step)
  const selectedSessions = sessions.filter((s) => selectedIds.has(s.session_id));
  const needsJudge = selectedSessions.filter((s) => !s.judge_current).length;

  // Selection handlers
  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    const selectable = sessions.filter((s) => !processingIds.has(s.session_id));
    if (selectedIds.size === selectable.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(selectable.map((s) => s.session_id)));
    }
  };

  const handleBatchJudge = async () => {
    if (selectedIds.size === 0) return;

    // Check for green (current) sessions that may have been judged with the same prompt
    const greenSessions = selectedSessions.filter((s) => s.judge_current === 1);
    if (greenSessions.length > 0 && scriptConfig) {
      try {
        const outputs = await api.sessionJudgeOutputs(greenSessions[0].session_id);
        const outputValues = Object.values(outputs);
        const lastPromptId = outputValues.length > 0 ? outputValues[0].prompt_id : null;
        if (lastPromptId && lastPromptId === scriptConfig.judge.prompt_id) {
          const proceed = confirm(
            `${greenSessions.length} selected session(s) already judged with the same prompt. Are you sure you want to judge again?`
          );
          if (!proceed) return;
        }
      } catch {
        // If we can't check, proceed without warning
      }
    }

    try {
      const ids = Array.from(selectedIds);
      setProcessingIds(new Set(ids));
      // Always run compaction + judge together as one "Judge" step
      const res = await api.runBatchAsync(["transcript-compact", "llm-time-estimate"], ids);
      setBatchJobId(res.job_id);
      window.dispatchEvent(new Event("job-created"));
    } catch (e) {
      setProcessingIds(new Set());
      alert((e as Error).message);
    }
  };

  const cycleThreeWay = (current: ThreeWay): ThreeWay => {
    if (current === "") return "true";
    if (current === "true") return "false";
    return "";
  };

  const threeWayLabel = (value: ThreeWay, label: string) => {
    if (value === "true") return `${label}: Yes`;
    if (value === "false") return `${label}: No`;
    return label;
  };

  return (
    <div>
      <h2 className="page-title">
        Sessions ({total.toLocaleString()})
        {hasProjectFilter && (
          <span style={{ fontSize: 14, fontWeight: 400, marginLeft: 12 }}>
            filtered by <strong>{projectFilter}</strong>
            {subfolders && " + subfolders"}
          </span>
        )}
      </h2>

      {/* Filter bar */}
      <div style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        alignItems: "center",
        marginBottom: 16,
        padding: "10px 12px",
        background: "var(--bg-hover)",
        borderRadius: 6,
      }}>
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          style={{ fontSize: 12, padding: "4px 6px" }}
          title="From date"
        />
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>to</span>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          style={{ fontSize: 12, padding: "4px 6px" }}
          title="To date"
        />

        {filterOptions && (
          <>
            <select
              value={modelFilter}
              onChange={(e) => setModelFilter(e.target.value)}
              style={{ fontSize: 12, padding: "4px 6px" }}
            >
              <option value="">All models</option>
              {filterOptions.models.map((m) => (
                <option key={m} value={m}>{m.replace("claude-", "")}</option>
              ))}
            </select>

            <select
              value={scaffoldFilter}
              onChange={(e) => setScaffoldFilter(e.target.value)}
              style={{ fontSize: 12, padding: "4px 6px" }}
            >
              <option value="">All scaffolds</option>
              {filterOptions.scaffolds.map((s) => (
                <option key={s} value={s}>{s.replace("claude_code", "Claude Code").replace("custom:", "")}</option>
              ))}
            </select>
          </>
        )}

        <select
          value={orgFilter}
          onChange={(e) => setOrgFilter(e.target.value)}
          style={{ fontSize: 12, padding: "4px 6px" }}
        >
          <option value="">All orgs</option>
          <option value="personal">Unassigned</option>
          {orgs.map((o) => (
            <option key={o.org_id} value={o.org_id}>{o.name}</option>
          ))}
        </select>

        <button
          className={`btn btn-secondary ${hasSurvey ? "btn-active" : ""}`}
          style={{ padding: "3px 8px", fontSize: 11, background: hasSurvey ? (hasSurvey === "true" ? "#16a34a22" : "#dc262622") : undefined }}
          onClick={() => setHasSurvey(cycleThreeWay(hasSurvey))}
          title="Click to cycle: Any / Yes / No"
        >
          {threeWayLabel(hasSurvey, "Survey")}
        </button>

        <button
          className={`btn btn-secondary ${hasJudge ? "btn-active" : ""}`}
          style={{ padding: "3px 8px", fontSize: 11, background: hasJudge ? (hasJudge === "true" ? "#16a34a22" : "#dc262622") : undefined }}
          onClick={() => setHasJudge(cycleThreeWay(hasJudge))}
          title="Click to cycle: Any / Yes / No"
        >
          {threeWayLabel(hasJudge, "Judge")}
        </button>

        <button
          className={`btn btn-secondary ${judgeSuccess ? "btn-active" : ""}`}
          style={{ padding: "3px 8px", fontSize: 11, background: judgeSuccess ? (judgeSuccess === "true" ? "#16a34a22" : "#dc262622") : undefined }}
          onClick={() => setJudgeSuccess(cycleThreeWay(judgeSuccess))}
          title="Click to cycle: Any / Yes / No"
        >
          {threeWayLabel(judgeSuccess, "Success")}
        </button>

        <button
          className={`btn btn-secondary ${isLocal ? "btn-active" : ""}`}
          style={{ padding: "3px 8px", fontSize: 11, background: isLocal ? (isLocal === "true" ? "#3b82f622" : "#8b5cf622") : undefined }}
          onClick={() => setIsLocal(cycleThreeWay(isLocal))}
          title="Click to cycle: Any / Local / Remote"
        >
          {isLocal === "true" ? "Source: Local" : isLocal === "false" ? "Source: Remote" : "Source"}
        </button>

        {sourceMember && (
          <span style={{
            padding: "3px 8px",
            fontSize: 11,
            background: "#ede9fe",
            color: "#6d28d9",
            borderRadius: 4,
            fontWeight: 500,
          }}>
            Member: {sourceMember}
          </span>
        )}

        {hasAnyFilter && (
          <button
            className="btn btn-secondary"
            style={{ padding: "3px 8px", fontSize: 11 }}
            onClick={clearFilters}
          >
            Clear
          </button>
        )}
      </div>

      {hasProjectFilter && (
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

      {/* Action bar / Progress bar — mutually exclusive */}
      {batchJobId ? (
        <JobProgress
          jobId={batchJobId}
          onProgress={() => {
            loadSessions();
            loadUpliftMap();
          }}
          onComplete={() => {
            setBatchJobId(null);
            setProcessingIds(new Set());
            loadSessions();
            loadResponses();
            loadUpliftMap();
          }}
        />
      ) : (
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 16,
          padding: "8px 12px",
          background: selectedIds.size > 0 ? "#3b82f611" : "var(--bg-hover)",
          border: `1px solid ${selectedIds.size > 0 ? "#3b82f633" : "var(--border)"}`,
          borderRadius: 6,
        }}>
          <span style={{ fontSize: 13, fontWeight: 500, color: selectedIds.size > 0 ? undefined : "var(--text-muted)" }}>
            {selectedIds.size} selected
          </span>
          <button
            className="btn"
            style={{ padding: "3px 10px", fontSize: 12 }}
            disabled={needsJudge === 0}
            onClick={handleBatchJudge}
            title={needsJudge === 0 ? "All selected sessions have current judge results" : "Run compaction + judge on selected sessions"}
          >
            Judge{needsJudge > 0 ? ` (${needsJudge})` : ""}
          </button>
          <button
            className="btn btn-secondary"
            style={{ padding: "3px 8px", fontSize: 11, visibility: selectedIds.size > 0 ? "visible" : "hidden" }}
            onClick={() => setSelectedIds(new Set())}
          >
            Deselect
          </button>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <button
              className="btn btn-secondary"
              style={{ padding: "3px 10px", fontSize: 12 }}
              onClick={() => {
                const opts = {
                  ...(selectedIds.size > 0 ? { session_ids: Array.from(selectedIds) } : {
                    ...(projectPath && subfolders ? { projectPath, subfolders: true } : projectFilter ? { project: projectFilter } : {}),
                    ...(dateFrom ? { date_from: dateFrom } : {}),
                    ...(dateTo ? { date_to: dateTo } : {}),
                    ...(modelFilter ? { model: modelFilter } : {}),
                    ...(scaffoldFilter ? { scaffold: scaffoldFilter } : {}),
                    ...(hasSurvey ? { has_survey: hasSurvey } : {}),
                    ...(hasJudge ? { has_judge: hasJudge } : {}),
                    ...(judgeSuccess ? { judge_success: judgeSuccess } : {}),
                    ...(isLocal ? { is_local: isLocal } : {}),
                    ...(orgFilter ? { org_id: orgFilter } : {}),
                  }),
                  include_judge: true,
                  include_survey: true,
                };
                api.exportSessions("csv", opts);
              }}
              title="Export sessions as CSV"
            >
              Export CSV
            </button>
            <button
              className="btn btn-secondary"
              style={{ padding: "3px 10px", fontSize: 12 }}
              onClick={() => {
                const opts = {
                  ...(selectedIds.size > 0 ? { session_ids: Array.from(selectedIds) } : {
                    ...(projectPath && subfolders ? { projectPath, subfolders: true } : projectFilter ? { project: projectFilter } : {}),
                    ...(dateFrom ? { date_from: dateFrom } : {}),
                    ...(dateTo ? { date_to: dateTo } : {}),
                    ...(modelFilter ? { model: modelFilter } : {}),
                    ...(scaffoldFilter ? { scaffold: scaffoldFilter } : {}),
                    ...(hasSurvey ? { has_survey: hasSurvey } : {}),
                    ...(hasJudge ? { has_judge: hasJudge } : {}),
                    ...(judgeSuccess ? { judge_success: judgeSuccess } : {}),
                    ...(isLocal ? { is_local: isLocal } : {}),
                    ...(orgFilter ? { org_id: orgFilter } : {}),
                  }),
                  include_judge: true,
                  include_survey: true,
                };
                api.exportSessions("json", opts);
              }}
              title="Export sessions as JSON"
            >
              Export JSON
            </button>
          </div>
        </div>
      )}

      {sessions.length === 0 ? (
        <div className="empty">
          No sessions yet. Run `open-uplift sync` to ingest data.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
        <table style={{ minWidth: 1260 }}>
          <thead>
            <tr>
              <th style={{ width: 40, overflow: "visible" }}>
                <input
                  type="checkbox"
                  checked={selectedIds.size === sessions.length && sessions.length > 0}
                  onChange={toggleSelectAll}
                  title="Select all on page"
                />
              </th>
              <th style={{ width: 28 }} title="Judge status"></th>
              <th>Date</th>
              <th>Project</th>
              <th>Scaffold</th>
              <th>Model</th>
              <th style={{ width: 100 }}>Source</th>
              <th>Uplift</th>
              <th>Messages</th>
              <th>Tools</th>
              <th>Tokens</th>
              <th>Survey</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => {
              const llmJudgeUplift = upliftMap[s.session_id]?.["llm-judge"] ?? null;
              const hasReport = responsesBySession.has(s.session_id);
              const scaffold = (s as Session & { scaffold?: string }).scaffold || s.tool_source;

              // Judge status: current (green), stale (yellow warning), or not judged (empty)
              const isJudged = s.judge_current || llmJudgeUplift != null;
              const isCurrent = s.judge_current === 1;
              const isStale = isJudged && !isCurrent;

              return (
                <React.Fragment key={s.session_id}>
                <tr
                  style={{ cursor: "pointer" }}
                  onClick={() => navigate(`/sessions/${s.session_id}/transcript`, { state: { sessionsSearch: location.search } })}
                >
                  <td style={{ overflow: "visible" }} onClick={(e) => e.stopPropagation()}>
                    {processingIds.has(s.session_id) ? (
                      <span
                        title="Processing..."
                        style={{
                          display: "inline-block",
                          width: 14,
                          height: 14,
                          borderRadius: "50%",
                          background: "#000",
                          opacity: 0.4,
                        }}
                      />
                    ) : (
                      <input
                        type="checkbox"
                        checked={selectedIds.has(s.session_id)}
                        onChange={() => toggleSelect(s.session_id)}
                      />
                    )}
                  </td>
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
                  <td>{s.project_name || "\u2014"}</td>
                  <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                    {scaffold?.replace("claude_code", "Claude Code").replace("custom:", "") || "\u2014"}
                  </td>
                  <td>{s.model_primary?.replace("claude-", "") || "\u2014"}</td>
                  <td>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 600,
                        padding: "2px 6px",
                        borderRadius: 4,
                        background: (s.is_local ?? 1) ? "#3b82f618" : "#8b5cf618",
                        color: (s.is_local ?? 1) ? "#3b82f6" : "#8b5cf6",
                        letterSpacing: 0.3,
                        textTransform: "uppercase",
                      }}
                    >
                      {(s.is_local ?? 1) ? "Local" : s.source_member || "Remote"}
                    </span>
                  </td>
                  <td>
                    {llmJudgeUplift != null ? (
                      <Link
                        to={`/sessions/${s.session_id}/transcript#judge`}
                        state={{ sessionsSearch: location.search }}
                        style={{ color: "#16a34a", fontWeight: 500, textDecoration: "underline", textDecorationColor: "var(--border)", textUnderlineOffset: 2 }}
                      >
                        {llmJudgeUplift}x
                      </Link>
                    ) : isJudged && s.judge_success === "false" ? (
                      <Link
                        to={`/sessions/${s.session_id}/transcript#judge`}
                        state={{ sessionsSearch: location.search }}
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
                  <td onClick={(e) => e.stopPropagation()}>
                    <button
                      className={hasReport ? "btn-report-done" : "btn btn-report"}
                      onClick={() => setReportSession(s)}
                      title={hasReport ? "Survey submitted — click to update" : "Submit survey for this session"}
                    >
                      {hasReport ? "Reported" : "Report"}
                    </button>
                  </td>
                </tr>
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
        </div>
      )}

      {reportSession && (
        <ReportForm
          sessionId={reportSession.session_id}
          projectName={reportSession.project_name}
          onClose={() => setReportSession(null)}
          onSubmitted={() => {
            setReportSession(null);
            loadSessions();
            loadResponses();
            loadUpliftMap();
          }}
        />
      )}
    </div>
  );
}
