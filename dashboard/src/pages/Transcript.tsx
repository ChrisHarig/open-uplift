import { useEffect, useState } from "react";
import { useParams, useLocation, Link } from "react-router-dom";
import {
  api,
  TranscriptData,
  TranscriptEntry,
  TranscriptContentBlock,
  ScriptResult,
  Prompt,
  Session,
  JudgeOutput,
  SessionUpliftOutput,
  SurveyResponse,
  SurveyDefinition,
  QuestionDefinition,
  fmt,
} from "../api.ts";
import ReportForm from "../components/ReportForm.tsx";

type ViewMode = "raw" | "compacted";

export default function Transcript() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const location = useLocation();
  const backTo = `/sessions${(location.state as { sessionsSearch?: string })?.sessionsSearch || ""}`;
  const [data, setData] = useState<TranscriptData | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");
  const [transcriptError, setTranscriptError] = useState("");
  const [showThinking, setShowThinking] = useState(false);
  const [showToolDetails, setShowToolDetails] = useState(false);
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());

  // Compaction state
  const [viewMode, setViewMode] = useState<ViewMode>("raw");
  const [compactedText, setCompactedText] = useState<string | null>(null);
  const [compacting, setCompacting] = useState(false);
  const [compactionPrompt, setCompactionPrompt] = useState<Prompt | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  const [compactionCurrent, setCompactionCurrent] = useState(false);

  // Judge outputs
  const [judgeOutputs, setJudgeOutputs] = useState<Record<string, JudgeOutput> | null>(null);
  const [upliftOutputs, setUpliftOutputs] = useState<SessionUpliftOutput[]>([]);
  const [judgeExpanded, setJudgeExpanded] = useState(window.location.hash === "#judge");
  const [judgePrompt, setJudgePrompt] = useState<Prompt | null>(null);

  // Survey state
  const [surveyExpanded, setSurveyExpanded] = useState(false);
  const [surveyResponses, setSurveyResponses] = useState<SurveyResponse[]>([]);
  const [showReportForm, setShowReportForm] = useState(false);
  const [activeSurvey, setActiveSurvey] = useState<SurveyDefinition | null>(null);
  const [allQuestions, setAllQuestions] = useState<Record<string, QuestionDefinition>>({});

  // Deterministic elements
  const [usedCompaction, setUsedCompaction] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    api.transcript(sessionId).then(setData).catch((e) => setTranscriptError(e.message));
    // Fetch active survey, all questions, and survey responses for this session
    api.activeSurvey().then((d) => setActiveSurvey(d.survey)).catch(() => {});
    api.questions().then(setAllQuestions).catch(() => {});
    api.surveyResponses().then((responses) => {
      setSurveyResponses(responses.filter((r: SurveyResponse) => r.session_id === sessionId));
    }).catch(() => {});
    // Fetch judge outputs
    api.sessionJudgeOutputs(sessionId).then(setJudgeOutputs).catch(() => {});
    // Fetch uplift outputs for metadata
    api.sessionUpliftOutputs(sessionId).then(setUpliftOutputs).catch(() => {});
    // (deterministic context fetched via session/script results below)
    // Check for existing compaction, staleness, and fetch its prompt
    Promise.all([
      api.scriptResults(sessionId),
      api.sessionDetail(sessionId),
    ]).then(([results, detail]) => {
      setSession(detail.session);
      const compaction = results.find(
        (r: ScriptResult) => r.script_id === "transcript-compact" && r.status === "completed"
      );
      if (compaction?.result) {
        const res = compaction.result as Record<string, unknown>;
        setCompactedText(res.compacted_transcript as string);
        setUsedCompaction(true);
      }
      // Check if compaction is current (not stale)
      if (compaction && compaction.session_message_count != null) {
        setCompactionCurrent(compaction.session_message_count >= (detail.session.message_count || 0));
      }
      if (compaction?.prompt_id) {
        api.prompts("compaction", true).then((prompts) => {
          const p = prompts.find((pr: Prompt) => pr.prompt_id === compaction.prompt_id);
          if (p) setCompactionPrompt(p);
        }).catch(() => {});
      }
      // Fetch judge prompt info
      const judge = results.find(
        (r: ScriptResult) => r.script_id === "llm-time-estimate" && r.status === "completed"
      );
      if (judge?.prompt_id) {
        api.prompts("judge", true).then((prompts) => {
          const p = prompts.find((pr: Prompt) => pr.prompt_id === judge.prompt_id);
          if (p) setJudgePrompt(p);
        }).catch(() => {});
      }
    }).catch(() => {});
  }, [sessionId]);

  const handleCompact = async () => {
    if (!sessionId) return;
    setCompacting(true);
    try {
      const result = await api.runScript("transcript-compact", sessionId);
      if (result.compacted_transcript) {
        setCompactedText(result.compacted_transcript as string);
        setCompactionCurrent(true);
        setViewMode("compacted");
        // Refresh prompt info for the new compaction
        api.scriptResults(sessionId).then((results) => {
          const compaction = results.find(
            (r: ScriptResult) => r.script_id === "transcript-compact" && r.status === "completed"
          );
          if (compaction?.prompt_id) {
            api.prompts("compaction").then((prompts) => {
              const p = prompts.find((pr: Prompt) => pr.prompt_id === compaction.prompt_id);
              if (p) setCompactionPrompt(p);
            }).catch(() => {});
          }
        }).catch(() => {});
      } else if (result.error) {
        setError(`Compaction error: ${result.error}`);
      }
    } catch (e) {
      setError(`Compaction error: ${(e as Error).message}`);
    } finally {
      setCompacting(false);
    }
  };

  const toggleTool = (key: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (error) {
    return (
      <div>
        <Link to={backTo} className="transcript-back">
          &larr; Sessions
        </Link>
        <div className="empty">{error}</div>
      </div>
    );
  }

  if (!session && !data && !transcriptError) {
    return (
      <div>
        <Link to={backTo} className="transcript-back">
          &larr; Sessions
        </Link>
        <div className="empty">Loading...</div>
      </div>
    );
  }

  // Compute judge panel values
  const llmUplift = upliftOutputs.find((u) => u.output_id === "llm-judge");
  const minutesWithoutAi = llmUplift?.metadata?.minutes_without_ai as number | undefined;
  const activeMinutes = llmUplift?.metadata?.active_minutes as number | undefined;

  return (
    <div>
      <Link to={backTo} className="transcript-back">
        &larr; Sessions
      </Link>

      <h2 className="page-title">
        Session
        {session && (
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              padding: "2px 6px",
              borderRadius: 4,
              background: (session.is_local ?? 1) ? "#3b82f618" : "#8b5cf618",
              color: (session.is_local ?? 1) ? "#3b82f6" : "#8b5cf6",
              letterSpacing: 0.3,
              textTransform: "uppercase",
              marginLeft: 12,
              verticalAlign: "middle",
            }}
          >
            {(session.is_local ?? 1) ? "Local" : "Remote"}
          </span>
        )}
      </h2>

      {session && (
        <div className="stat-grid" style={{ marginBottom: 20 }}>
          <div className="stat-card">
            <div className="label">Project</div>
            <div className="value" style={{ fontSize: 16 }}>
              {session.project_name || "Unknown"}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">Date</div>
            <div className="value" style={{ fontSize: 16 }}>
              {new Date(session.started_at).toLocaleDateString()}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">Model</div>
            <div className="value" style={{ fontSize: 16 }}>
              {session.model_primary?.replace("claude-", "") || "\u2014"}
            </div>
            {(session as Session & { scaffold?: string }).scaffold && (
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
                {((session as Session & { scaffold?: string }).scaffold || "").replace("claude_code", "Claude Code").replace("custom:", "")}
              </div>
            )}
          </div>
          <div className="stat-card">
            <div className="label">Messages / Tools</div>
            <div className="value" style={{ fontSize: 16 }}>
              {data
                ? `${data.stats.user_messages + data.stats.assistant_messages} / ${data.stats.tool_calls}`
                : `${session.message_count} / ${session.tool_call_count}`}
            </div>
          </div>
          <div className="stat-card">
            <div className="label">Tokens</div>
            <div className="value" style={{ fontSize: 16 }}>
              {fmt(session.total_input_tokens + session.total_output_tokens)}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, lineHeight: 1.5 }}>
              <div>In: {fmt(session.total_input_tokens)} · Out: {fmt(session.total_output_tokens)}</div>
              {session.total_cache_read_tokens > 0 && (
                <div>Cache read: {fmt(session.total_cache_read_tokens)}</div>
              )}
              {session.total_cache_create_tokens > 0 && (
                <div>Cache write: {fmt(session.total_cache_create_tokens)}</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Survey Panel (collapsible) — only show if active survey exists OR responses exist */}
      {session && (activeSurvey || surveyResponses.length > 0) && (
        <div className="stat-card" style={{ marginBottom: 20, padding: 0, overflow: "hidden" }}>
          <div
            onClick={() => {
              if (surveyResponses.length > 0) {
                setSurveyExpanded(!surveyExpanded);
              } else {
                setShowReportForm(true);
              }
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              padding: "12px 16px",
              cursor: "pointer",
              userSelect: "none",
            }}
          >
            <span style={{ fontSize: 11, color: "var(--text-muted)", width: 12 }}>
              {surveyResponses.length > 0 ? (surveyExpanded ? "\u25BC" : "\u25B6") : "+"}
            </span>
            <span style={{ fontSize: 14, fontWeight: 500 }}>Survey</span>
            {surveyResponses.length > 0 && (
              <span style={{
                fontSize: 11,
                fontWeight: 500,
                padding: "2px 8px",
                borderRadius: 4,
                background: "#16a34a22",
                color: "#16a34a",
              }}>
                Reported
              </span>
            )}
            {surveyResponses.length === 0 && (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Click to submit survey
              </span>
            )}
          </div>
          {surveyExpanded && surveyResponses.length > 0 && (
            <div style={{ padding: "0 16px 16px", borderTop: "1px solid var(--border)" }}>
              <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                {surveyResponses.map((r, i) => (
                  <div key={i} style={{ fontSize: 13, lineHeight: 1.6 }}>
                    {Object.entries(r.answers).map(([qId, v]) => {
                      const qDef = allQuestions[qId];
                      const label = qDef?.label || qId;
                      const suffix = qDef?.suffix ? ` ${qDef.suffix}` : "";
                      return (
                        <div key={qId} style={{ marginBottom: 4 }}>
                          <strong>{label}</strong>: {v}{suffix}
                        </div>
                      );
                    })}
                    {r.notes && <div style={{ color: "var(--text-muted)", marginTop: 4 }}>Notes: {r.notes}</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {showReportForm && session && (
        <ReportForm
          sessionId={session.session_id}
          projectName={session.project_name}
          onClose={() => setShowReportForm(false)}
          onSubmitted={() => {
            setShowReportForm(false);
            if (sessionId) {
              api.surveyResponses().then((responses) => {
                setSurveyResponses(responses.filter((r: SurveyResponse) => r.session_id === sessionId));
              }).catch(() => {});
            }
          }}
        />
      )}

      {/* Judge Results Panel (collapsible) */}
      {judgeOutputs && Object.keys(judgeOutputs).length > 0 ? (
        <JudgePanel
          judgeOutputs={judgeOutputs}
          upliftOutputs={upliftOutputs}
          minutesWithoutAi={minutesWithoutAi}
          activeMinutes={activeMinutes}
          expanded={judgeExpanded}
          onToggle={() => setJudgeExpanded(!judgeExpanded)}
          judgePrompt={judgePrompt}
          session={session}
          usedCompaction={usedCompaction}
          compactionPrompt={compactionPrompt}
        />
      ) : session && (
        <div className="stat-card" style={{ marginBottom: 20, padding: "12px 16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <span style={{ fontSize: 14, fontWeight: 500, color: "var(--text-muted)" }}>Judge Results</span>
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Not yet evaluated. Configure an API key in <Link to="/settings" style={{ color: "var(--text-muted)" }}>Settings</Link> and run the judge to generate uplift estimates.
            </span>
          </div>
        </div>
      )}

      <div className="transcript-controls">
        {/* View mode toggle */}
        {(data || compactedText) && (
        <div className="transcript-view-toggle">
          <button
            className={`btn ${viewMode === "raw" ? "" : "btn-secondary"}`}
            style={{ borderRadius: "6px 0 0 6px", padding: "6px 14px", fontSize: 12 }}
            onClick={() => setViewMode("raw")}
            disabled={!data}
          >
            Raw
          </button>
          <button
            className={`btn ${viewMode === "compacted" ? "" : "btn-secondary"}`}
            style={{ borderRadius: "0 6px 6px 0", padding: "6px 14px", fontSize: 12 }}
            onClick={() => setViewMode("compacted")}
          >
            Compacted
          </button>
        </div>
        )}

        {compactionPrompt && (
          <button
            className="btn btn-secondary"
            onClick={() => setShowPrompt(!showPrompt)}
            style={{ padding: "4px 10px", fontSize: 12 }}
          >
            {showPrompt ? "Hide Prompt" : `Prompt: ${compactionPrompt.name}${compactionPrompt.version && compactionPrompt.version > 1 ? ` v${compactionPrompt.version}` : ""}`}
          </button>
        )}

        {viewMode === "raw" && data && (
          <>
            <label className="toggle-row" style={{ display: "inline-flex" }}>
              <span className="toggle-label">Show thinking</span>
              <div
                className={`toggle ${showThinking ? "toggle-on" : ""}`}
                onClick={() => setShowThinking(!showThinking)}
              >
                <div className="toggle-knob" />
              </div>
            </label>
            <label className="toggle-row" style={{ display: "inline-flex" }}>
              <span className="toggle-label">Show tool details</span>
              <div
                className={`toggle ${showToolDetails ? "toggle-on" : ""}`}
                onClick={() => setShowToolDetails(!showToolDetails)}
              >
                <div className="toggle-knob" />
              </div>
            </label>
          </>
        )}
      </div>

      {/* Compaction prompt (shown/hidden via controls bar button) */}
      {showPrompt && compactionPrompt && (
        <div style={{
          background: "var(--bg-hover)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          padding: "12px 16px",
          marginBottom: 16,
          fontSize: 13,
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
        }}>
          {compactionPrompt.system_prompt}
        </div>
      )}

      {viewMode === "compacted" && compactedText ? (
        <div className="transcript-compacted">
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <button
              className="btn"
              onClick={handleCompact}
              disabled={compacting || compactionCurrent}
              style={{ padding: "4px 10px", fontSize: 12 }}
              title={compactionCurrent ? "Compaction is up to date (no new messages)" : undefined}
            >
              {compacting ? "Compacting..." : compactionCurrent ? "Up to date" : "Re-compact"}
            </button>
          </div>
          <div style={{ whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.7 }}>
            {compactedText}
          </div>
        </div>
      ) : viewMode === "compacted" && !compactedText ? (
        <div className="empty">
          <p>No compacted transcript available.</p>
          <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
            Configure an API key in <Link to="/settings">Settings</Link> and run compaction to generate a summary.
          </p>
        </div>
      ) : data ? (
        <div className="transcript-messages">
          {data.transcript.map((entry, i) => (
            <MessageEntry
              key={i}
              entry={entry}
              index={i}
              showThinking={showThinking}
              showToolDetails={showToolDetails}
              expandedTools={expandedTools}
              toggleTool={toggleTool}
            />
          ))}
        </div>
      ) : transcriptError ? (
        <div className="empty">
          <p>Transcript file not available.</p>
          <p style={{ fontSize: 13, color: "var(--text-muted)" }}>
            The raw transcript for this session could not be loaded. Session metadata and judge results (if available) are shown above.
          </p>
        </div>
      ) : (
        <div className="empty">Loading transcript...</div>
      )}
    </div>
  );
}

function JudgePanel({
  judgeOutputs,
  upliftOutputs,
  minutesWithoutAi,
  activeMinutes,
  expanded,
  onToggle,
  judgePrompt,
  session,
  usedCompaction,
  compactionPrompt,
}: {
  judgeOutputs: Record<string, JudgeOutput>;
  upliftOutputs: SessionUpliftOutput[];
  minutesWithoutAi: number | undefined;
  activeMinutes: number | undefined;
  expanded: boolean;
  onToggle: () => void;
  judgePrompt: Prompt | null;
  session: Session | null;
  usedCompaction: boolean;
  compactionPrompt: Prompt | null;
}) {
  const [showJudgePrompt, setShowJudgePrompt] = useState(false);

  const llmUplift = upliftOutputs.find((u) => u.output_id === "llm-judge");
  const upliftFactor = judgeOutputs.uplift_factor?.value_numeric ?? llmUplift?.uplift_factor ?? null;
  const success = judgeOutputs.success;
  const confidence = judgeOutputs.confidence_level;
  const reasoning = judgeOutputs.reasoning;

  const metricItems = (Object.entries(judgeOutputs) as [string, JudgeOutput][])
    .filter(([key]) => key !== "tasks" && key !== "reasoning")
    .map(([key, output]) => {
      let displayValue: string;
      if (output.value_type === "boolean") {
        displayValue = output.value ? "Yes" : "No";
      } else if (output.value_type === "array") {
        const arr = Array.isArray(output.value) ? output.value : [];
        displayValue = `${arr.length} items`;
      } else {
        displayValue = String(output.value);
      }
      const colorStyle = output.value_type === "boolean"
        ? (output.value ? "#16a34a" : "var(--text)")
        : undefined;
      return (
        <div key={key} style={{ minWidth: 100 }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{key}</div>
          <div style={{ fontWeight: 500, color: colorStyle }}>
            {displayValue}
          </div>
        </div>
      );
    });

  return (
    <div id="judge" className="stat-card" style={{ marginBottom: 20, padding: 0, overflow: "hidden" }}>
      {/* Header row — always visible */}
      <div
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "12px 16px",
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        <span style={{ fontSize: 11, color: "var(--text-muted)", width: 12 }}>
          {expanded ? "\u25BC" : "\u25B6"}
        </span>
        {upliftFactor != null && (
          <span style={{ fontSize: 18, fontWeight: 600, color: "#16a34a" }}>
            {upliftFactor}x uplift
          </span>
        )}
        {success && (
          <span style={{
            fontSize: 12,
            fontWeight: 500,
            padding: "2px 8px",
            borderRadius: 4,
            background: success.value ? "#16a34a22" : "var(--bg-hover)",
            color: success.value ? "#16a34a" : "var(--text)",
          }}>
            {success.value ? "Success" : "Failed"}
          </span>
        )}
        {confidence && (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            Confidence: {String(confidence.value)}
          </span>
        )}
        <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-muted)" }}>
          Judge Results
          {judgePrompt && (
            <span style={{ marginLeft: 8, fontSize: 11 }}>
              ({judgePrompt.name}{judgePrompt.version && judgePrompt.version > 1 ? ` v${judgePrompt.version}` : ""})
            </span>
          )}
        </span>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div style={{ padding: "0 16px 16px", borderTop: "1px solid var(--border)" }}>
          {/* Judge prompt button */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 12 }}>
            {judgePrompt && (
              <button
                className="btn"
                onClick={() => setShowJudgePrompt(!showJudgePrompt)}
                style={{ padding: "6px 14px", fontSize: 13 }}
              >
                {showJudgePrompt ? "Hide Prompt" : `Prompt: ${judgePrompt.name}${judgePrompt.version && judgePrompt.version > 1 ? ` v${judgePrompt.version}` : ""}`}
              </button>
            )}
          </div>
          {showJudgePrompt && judgePrompt && (
            <>
              <div style={{
                background: "var(--bg-hover)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "12px 16px",
                marginTop: 8,
                fontSize: 13,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                maxHeight: 300,
                overflow: "auto",
              }}>
                {judgePrompt.system_prompt}
              </div>
              {/* Judge inputs — shown alongside prompt */}
              {session?.continuation_type && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                    <span style={{ padding: "1px 6px", borderRadius: 3, background: "#fef3c7", color: "#92400e", fontSize: 11, fontWeight: 500 }}>
                      Continuation
                    </span>
                    <span style={{ color: "var(--text-muted)" }}>
                      {session.continuation_type} (from {session.continued_from?.slice(0, 8)}...)
                    </span>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Uplift calculation */}
          {minutesWithoutAi != null && activeMinutes != null && (
            <div style={{ marginTop: 12, fontSize: 13, padding: "8px 12px", background: "var(--bg-hover)", borderRadius: 6 }}>
              <span style={{ fontWeight: 500 }}>Uplift calculation: </span>
              {minutesWithoutAi} min (no AI) / {activeMinutes} min (with AI) = {upliftFactor}x
            </div>
          )}

          {/* Key metrics */}
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap", fontSize: 13, marginTop: 12 }}>
            {metricItems}
          </div>

          {/* Tasks detail */}
          {judgeOutputs.tasks && Array.isArray(judgeOutputs.tasks.value) && (
            <div style={{ marginTop: 12, fontSize: 13 }}>
              <div style={{ fontWeight: 500, marginBottom: 6 }}>Tasks</div>
              {(judgeOutputs.tasks.value as Array<Record<string, unknown>>).map((task, i) => (
                <div key={i} style={{ paddingLeft: 12, marginBottom: 3, lineHeight: 1.5 }}>
                  <span style={{ color: task.succeeded === true ? "#16a34a" : task.succeeded === false ? "var(--text)" : "var(--text-muted)" }}>
                    {task.succeeded === true ? "+" : task.succeeded === false ? "\u2013" : "\u2022"}
                  </span>{" "}
                  {String(task.description || "")}
                  {task.estimated_minutes_without_ai != null && (
                    <span style={{ color: "var(--text-muted)" }}> ({String(task.estimated_minutes_without_ai)} min)</span>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Reasoning */}
          {reasoning != null && reasoning.value != null && (
            <div style={{ marginTop: 12, fontSize: 13 }}>
              <div style={{ fontWeight: 500, marginBottom: 6 }}>Reasoning</div>
              <div style={{
                padding: "10px 14px",
                background: "var(--bg-hover)",
                borderRadius: 6,
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
                color: "var(--text-muted)",
              }}>
                {String(reasoning.value)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MessageEntry({
  entry,
  index,
  showThinking,
  showToolDetails,
  expandedTools,
  toggleTool,
}: {
  entry: TranscriptEntry;
  index: number;
  showThinking: boolean;
  showToolDetails: boolean;
  expandedTools: Set<string>;
  toggleTool: (key: string) => void;
}) {
  const isUser = entry.role === "user";

  // Tool-only assistant messages render as compact inline rows
  const isToolOnly =
    !isUser &&
    entry.blocks.length > 0 &&
    entry.blocks.every((b) => b.type === "tool_use" || b.type === "thinking");

  if (isToolOnly) {
    const toolBlocks = entry.blocks.filter((b) => b.type === "tool_use");
    const thinkingBlocks = entry.blocks.filter((b) => b.type === "thinking");
    if (toolBlocks.length === 0 && (!showThinking || thinkingBlocks.length === 0))
      return null;
    return (
      <>
        {showThinking &&
          thinkingBlocks.map((b, j) => (
            <div key={`t-${index}-${j}`} className="transcript-msg transcript-msg-assistant">
              <div className="transcript-msg-role">Assistant</div>
              <div className="transcript-msg-content">
                <div className="transcript-thinking">{b.text}</div>
              </div>
            </div>
          ))}
        {toolBlocks.map((block, j) => {
          const blockKey = `${index}-${entry.blocks.indexOf(block)}`;
          const isExpanded = showToolDetails || expandedTools.has(blockKey);
          return (
            <ToolCallRow
              key={blockKey}
              block={block}
              blockKey={blockKey}
              isExpanded={isExpanded}
              toggleTool={toggleTool}
            />
          );
        })}
      </>
    );
  }

  const hasContent = entry.blocks.some((b) => {
    if (b.type === "thinking" && !showThinking) return false;
    return true;
  });

  if (!hasContent) return null;

  return (
    <div className={`transcript-msg ${isUser ? "transcript-msg-user" : "transcript-msg-assistant"}`}>
      <div className="transcript-msg-role">
        {isUser ? "User" : "Assistant"}
      </div>
      <div className="transcript-msg-content">
        {entry.blocks.map((block, j) => (
          <BlockContent
            key={j}
            block={block}
            blockKey={`${index}-${j}`}
            showThinking={showThinking}
            showToolDetails={showToolDetails}
            expanded={expandedTools.has(`${index}-${j}`)}
            toggleTool={toggleTool}
          />
        ))}
      </div>
    </div>
  );
}

function ToolCallRow({
  block,
  blockKey,
  isExpanded,
  toggleTool,
}: {
  block: TranscriptContentBlock;
  blockKey: string;
  isExpanded: boolean;
  toggleTool: (key: string) => void;
}) {
  return (
    <div className={`transcript-toolrow ${block.is_error ? "transcript-toolrow-error" : ""}`}>
      <div className="transcript-toolrow-header" onClick={() => toggleTool(blockKey)}>
        <span className="transcript-toolrow-toggle">
          {isExpanded ? "\u25BC" : "\u25B6"}
        </span>
        <span className="transcript-toolrow-role">Assistant</span>
        <span className="transcript-toolrow-sep">&mdash;</span>
        <span className="transcript-toolrow-name">{block.tool_name}</span>
      </div>
      {isExpanded && (
        <div className="transcript-tool-body">
          <div className="transcript-tool-section">
            <div className="transcript-tool-label">Input</div>
            <pre className="transcript-tool-pre">
              {formatToolInput(block.input)}
            </pre>
          </div>
          {block.result != null && (
            <div className="transcript-tool-section">
              <div className="transcript-tool-label">
                Result{block.is_error ? " (error)" : ""}
              </div>
              <pre className="transcript-tool-pre">{truncate(block.result, 2000)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function BlockContent({
  block,
  blockKey,
  showThinking,
  showToolDetails,
  expanded,
  toggleTool,
}: {
  block: TranscriptContentBlock;
  blockKey: string;
  showThinking: boolean;
  showToolDetails: boolean;
  expanded: boolean;
  toggleTool: (key: string) => void;
}) {
  if (block.type === "text") {
    return <div className="transcript-text">{block.text}</div>;
  }

  if (block.type === "thinking") {
    if (!showThinking) return null;
    return <div className="transcript-thinking">{block.text}</div>;
  }

  if (block.type === "tool_use") {
    const isExpanded = showToolDetails || expanded;
    return (
      <div className={`transcript-tool ${block.is_error ? "transcript-tool-error" : ""}`}>
        <div
          className="transcript-tool-header"
          onClick={() => toggleTool(blockKey)}
        >
          <span className="transcript-tool-badge">{block.tool_name}</span>
          <span className="transcript-tool-toggle">
            {isExpanded ? "\u25BC" : "\u25B6"}
          </span>
        </div>
        {isExpanded && (
          <div className="transcript-tool-body">
            <div className="transcript-tool-section">
              <div className="transcript-tool-label">Input</div>
              <pre className="transcript-tool-pre">
                {formatToolInput(block.input)}
              </pre>
            </div>
            {block.result != null && (
              <div className="transcript-tool-section">
                <div className="transcript-tool-label">
                  Result{block.is_error ? " (error)" : ""}
                </div>
                <pre className="transcript-tool-pre">{truncate(block.result, 2000)}</pre>
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  return null;
}

function formatToolInput(input?: Record<string, unknown>): string {
  if (!input) return "";
  try {
    return JSON.stringify(input, null, 2);
  } catch {
    return String(input);
  }
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "\n... (truncated)";
}
