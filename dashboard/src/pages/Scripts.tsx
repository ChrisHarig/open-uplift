import { useEffect, useState } from "react";
import { api, ScriptConfig, Prompt, ApiKeyInfo, SchemaField, UserProfile } from "../api.ts";

const DEFAULT_SCHEMA_FIELD_NAMES = new Set(["success", "total_minutes_without_ai", "tasks", "confidence", "reasoning"]);
const MAX_SCHEMA_FIELDS = 8;

const DEFAULT_JUDGE_SCHEMA: SchemaField[] = [
  { name: "success", type: "boolean", required: true, description: "Whether the task was completed successfully" },
  { name: "total_minutes_without_ai", type: "numeric", required: true, description: "Estimated minutes without AI" },
  { name: "tasks", type: "array", required: true, description: "Breakdown of individual tasks" },
  { name: "confidence", type: "string", required: true, description: "Confidence level: low, medium, high" },
  { name: "reasoning", type: "string", required: true, description: "Explanation of the estimate" },
];

export default function Scripts() {
  const [config, setConfig] = useState<ScriptConfig | null>(null);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [apiKeys, setApiKeys] = useState<ApiKeyInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  // Test script state
  const [testSessionId, setTestSessionId] = useState("");
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);
  const [testing, setTesting] = useState(false);
  const [testScript, setTestScript] = useState<"transcript-compact" | "llm-time-estimate">("transcript-compact");

  // Prompt editing
  const [editingPrompt, setEditingPrompt] = useState<Prompt | null>(null);
  const [editText, setEditText] = useState("");
  const [editSchema, setEditSchema] = useState<SchemaField[]>([]);

  // Create prompt state
  const [isCreating, setIsCreating] = useState(false);
  const [editName, setEditName] = useState("");

  // Compaction section visibility toggle
  const [showCompaction, setShowCompaction] = useState(true);

  // Developer profile
  const [profile, setProfile] = useState<UserProfile>({ experience_description: "" });
  const [savedProfile, setSavedProfile] = useState<UserProfile>({ experience_description: "" });
  const [savingProfile, setSavingProfile] = useState(false);

  const reloadPrompts = () => api.prompts(undefined, true).then(setPrompts);

  useEffect(() => {
    api.getScriptConfig().then(setConfig);
    reloadPrompts();
    api.apiKeys().then(setApiKeys);
    api.getUserProfile().then((p) => {
      const safe = { experience_description: p.experience_description ?? "" };
      setProfile(safe);
      setSavedProfile(safe);
    });
  }, []);

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    try {
      await api.setScriptConfig(config);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!testSessionId.trim()) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await api.runScript(testScript, testSessionId.trim());
      setTestResult(result);
    } catch (e) {
      setTestResult({ error: (e as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const handleSaveProfile = async () => {
    setSavingProfile(true);
    try {
      await api.setUserProfile(profile);
      setSavedProfile(profile);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setSavingProfile(false);
    }
  };

  const profileChanged = profile.experience_description !== savedProfile.experience_description;

  const handleSavePrompt = async () => {
    if (!editingPrompt) return;
    if (isCreating) {
      const promptId = editName.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || `prompt-${Date.now()}`;
      await api.createPrompt({
        prompt_id: promptId,
        category: editingPrompt.category,
        name: editName.trim(),
        system_prompt: editText,
        output_schema: editSchema.length > 0 ? editSchema : undefined,
      });
      setIsCreating(false);
    } else {
      await api.updatePrompt(editingPrompt.prompt_id, {
        system_prompt: editText,
        output_schema: editSchema.length > 0 ? editSchema : null,
      });
    }
    setEditingPrompt(null);
    reloadPrompts();
    api.getScriptConfig().then(setConfig);
  };

  if (!config) return <div className="empty">Loading...</div>;

  // Show non-archived prompts in selectors, but always include the currently active one
  const judgePromptsAll = prompts.filter((p) => p.category === "judge");
  const judgePrompts = judgePromptsAll.filter((p) => !p.archived_at || p.prompt_id === config.judge.prompt_id);
  const compactionPromptsAll = prompts.filter((p) => p.category === "compaction");
  const compactionPrompts = compactionPromptsAll.filter((p) => !p.archived_at || p.prompt_id === config.compaction.prompt_id);
  const activeJudgePrompt = judgePromptsAll.find((p) => p.prompt_id === config.judge.prompt_id);
  const activeCompactionPrompt = compactionPromptsAll.find((p) => p.prompt_id === config.compaction.prompt_id);
  const providers = [...new Set(apiKeys.map((k) => k.provider))];
  const hasKeys = apiKeys.length > 0;

  return (
    <div>
      <h2 className="page-title">Judge</h2>
      <p style={{ color: "var(--text-muted)", fontSize: 13, marginBottom: 24 }}>
        Configure the LLM judge that estimates time-without-AI for your sessions.
        {!hasKeys && (
          <span style={{ color: "#dc2626" }}> Add API keys in Settings first.</span>
        )}
      </p>

      {/* Judge + Compaction side by side */}
      <div className="chart-grid">
        {/* Judge Model + Prompt */}
        <div className="chart-card">
          <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>Judge</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", gap: 12 }}>
              <label style={{ flex: 1 }}>
                <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Provider</span>
                <select
                  value={config.judge.provider}
                  onChange={(e) => setConfig({ ...config, judge: { ...config.judge, provider: e.target.value } })}
                  style={{ width: "100%" }}
                >
                  {providers.length === 0 && <option value="">No keys configured</option>}
                  {providers.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </label>
              <label style={{ flex: 1 }}>
                <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Model</span>
                <input
                  className="search-input"
                  value={config.judge.model}
                  onChange={(e) => setConfig({ ...config, judge: { ...config.judge, model: e.target.value } })}
                  style={{ maxWidth: "100%" }}
                />
              </label>
            </div>
            <label>
              <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Prompt</span>
              <select
                value={config.judge.prompt_id}
                onChange={(e) => setConfig({ ...config, judge: { ...config.judge, prompt_id: e.target.value } })}
                style={{ width: "100%" }}
              >
                {judgePrompts.map((p) => (
                  <option key={p.prompt_id} value={p.prompt_id}>
                    {p.name}{p.version && p.version > 1 ? ` v${p.version}` : ""}{p.archived_at ? " (archived)" : ""}
                  </option>
                ))}
              </select>
            </label>
            {activeJudgePrompt && (
              <div style={{ fontSize: 12, color: "var(--text-muted)", background: "var(--bg-hover)", padding: 8, borderRadius: 4, maxHeight: 120, overflow: "auto", whiteSpace: "pre-wrap" }}>
                {activeJudgePrompt.system_prompt}
              </div>
            )}
            {(() => {
              const schema = activeJudgePrompt?.output_schema;
              if (!schema || schema.length === 0) return null;
              return (
                <div style={{ fontSize: 12 }}>
                  <div style={{ fontWeight: 500, color: "var(--text-muted)", marginBottom: 4 }}>Output Schema</div>
                  <table style={{ fontSize: 12, width: "100%" }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: "left", padding: "2px 8px" }}>Field</th>
                        <th style={{ textAlign: "left", padding: "2px 8px" }}>Type</th>
                        <th style={{ textAlign: "left", padding: "2px 8px" }}>Req</th>
                      </tr>
                    </thead>
                    <tbody>
                      {schema.map((f) => (
                        <tr key={f.name}>
                          <td style={{ padding: "2px 8px", fontFamily: "monospace" }}>{f.name}</td>
                          <td style={{ padding: "2px 8px" }}>{f.type}</td>
                          <td style={{ padding: "2px 8px" }}>{f.required ? "Yes" : "No"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })()}
            <div style={{ display: "flex", gap: 8, alignSelf: "flex-start" }}>
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12 }}
                disabled={!activeJudgePrompt}
                onClick={() => {
                  if (activeJudgePrompt) { setIsCreating(false); setEditingPrompt(activeJudgePrompt); setEditText(activeJudgePrompt.system_prompt); setEditSchema(activeJudgePrompt.output_schema || []); }
                }}
              >
                Edit Prompt
              </button>
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12 }}
                onClick={() => {
                  setIsCreating(true);
                  setEditName("");
                  setEditText("");
                  setEditSchema([...DEFAULT_JUDGE_SCHEMA]);
                  setEditingPrompt({ prompt_id: "", category: "judge", name: "", description: "", system_prompt: "", created_at: "", is_default: 0 });
                }}
              >
                Add Prompt
              </button>
            </div>
            {!activeJudgePrompt && (
              <div style={{ fontSize: 11, color: "#dc2626" }}>Prompt "{config.judge.prompt_id}" not found</div>
            )}
          </div>
        </div>

        {/* Compaction Settings */}
        <div className="chart-card">
          <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>Transcript Compaction</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", gap: 12 }}>
              <label style={{ flex: 1 }}>
                <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Provider</span>
                <select
                  value={config.compaction.provider}
                  onChange={(e) => setConfig({ ...config, compaction: { ...config.compaction, provider: e.target.value } })}
                  style={{ width: "100%" }}
                >
                  {providers.length === 0 && <option value="">No keys configured</option>}
                  {providers.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </label>
              <label style={{ flex: 1 }}>
                <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Model</span>
                <input
                  className="search-input"
                  value={config.compaction.model}
                  onChange={(e) => setConfig({ ...config, compaction: { ...config.compaction, model: e.target.value } })}
                  style={{ maxWidth: "100%" }}
                />
              </label>
            </div>
            <label>
              <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Prompt</span>
              <select
                value={config.compaction.prompt_id}
                onChange={(e) => setConfig({ ...config, compaction: { ...config.compaction, prompt_id: e.target.value } })}
                style={{ width: "100%" }}
              >
                {compactionPrompts.map((p) => (
                  <option key={p.prompt_id} value={p.prompt_id}>
                    {p.name}{p.version && p.version > 1 ? ` v${p.version}` : ""}{p.archived_at ? " (archived)" : ""}
                  </option>
                ))}
              </select>
            </label>
            {activeCompactionPrompt && (
              <div style={{ fontSize: 12, color: "var(--text-muted)", background: "var(--bg-hover)", padding: 8, borderRadius: 4, maxHeight: 120, overflow: "auto", whiteSpace: "pre-wrap" }}>
                {activeCompactionPrompt.system_prompt}
              </div>
            )}
            <div style={{ display: "flex", gap: 8, alignSelf: "flex-start" }}>
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12 }}
                disabled={!activeCompactionPrompt}
                onClick={() => {
                  if (activeCompactionPrompt) { setIsCreating(false); setEditingPrompt(activeCompactionPrompt); setEditText(activeCompactionPrompt.system_prompt); setEditSchema(activeCompactionPrompt.output_schema || []); }
                }}
              >
                Edit Prompt
              </button>
              <button
                className="btn btn-secondary"
                style={{ fontSize: 12 }}
                onClick={() => {
                  setIsCreating(true);
                  setEditName("");
                  setEditText("");
                  setEditSchema([]);
                  setEditingPrompt({ prompt_id: "", category: "compaction", name: "", description: "", system_prompt: "", created_at: "", is_default: 0 });
                }}
              >
                Add Prompt
              </button>
            </div>
            {!activeCompactionPrompt && (
              <div style={{ fontSize: 11, color: "#dc2626" }}>Prompt "{config.compaction.prompt_id}" not found</div>
            )}
          </div>
        </div>
      </div>

      {/* Developer Profile */}
      <div className="stat-card" style={{ maxWidth: 600, marginTop: 16 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", marginBottom: config.judge.include_profile !== false ? 12 : 0 }}>
          <div
            className={`toggle ${config.judge.include_profile !== false ? "toggle-on" : ""}`}
            onClick={() => setConfig({ ...config, judge: { ...config.judge, include_profile: config.judge.include_profile === false } })}
          >
            <div className="toggle-knob" />
          </div>
          <div>
            <div style={{ fontWeight: 500, fontSize: 14 }}>Include Developer Profile</div>
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              Prepend a description of the developer to the judge prompt for more accurate time estimates
            </div>
          </div>
        </label>
        {config.judge.include_profile !== false && (
          <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
            {profile.experience_description ? (
              <div style={{ fontSize: 12, color: "var(--text-muted)", background: "var(--bg-hover)", padding: 8, borderRadius: 4, marginBottom: 8, whiteSpace: "pre-wrap" }}>
                <span style={{ fontStyle: "italic" }}>Injected into prompt: </span>
                "The developer completing this task describes themselves as: {profile.experience_description}"
              </div>
            ) : (
              <p style={{ fontSize: 12, color: "var(--text-muted)", margin: "0 0 8px" }}>
                No profile set. The judge will default to "a software developer." Add a description for more accurate estimates.
              </p>
            )}
            <textarea
              className="search-input"
              style={{ minHeight: 70, resize: "vertical", fontFamily: "inherit", fontSize: 13 }}
              placeholder='e.g. "5 years of experience in web development, 2 years in data science, skill level 7/10, very familiar with react, pandas and pytorch."'
              value={profile.experience_description}
              onChange={(e) => setProfile((p) => ({ ...p, experience_description: e.target.value }))}
            />
            {profileChanged && (
              <button
                className="btn"
                style={{ marginTop: 8, fontSize: 12 }}
                onClick={handleSaveProfile}
                disabled={savingProfile}
              >
                {savingProfile ? "Saving..." : "Save Profile"}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Save */}
      <div style={{ margin: "24px 0", display: "flex", gap: 12, alignItems: "center" }}>
        <button className="btn" onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save Configuration"}
        </button>
        {saved && <span style={{ fontSize: 13, color: "#16a34a" }}>Saved</span>}
      </div>

      {/* Test Script */}
      <h3 style={{ margin: "32px 0 12px", color: "var(--text-muted)" }}>Test Script</h3>
      <div className="chart-card" style={{ maxWidth: 600 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", gap: 8 }}>
            <select
              value={testScript}
              onChange={(e) => setTestScript(e.target.value as typeof testScript)}
              style={{ width: 200 }}
            >
              <option value="transcript-compact">Transcript Compaction</option>
              <option value="llm-time-estimate">Time Estimate</option>
            </select>
            <input
              className="search-input"
              placeholder="Session ID"
              value={testSessionId}
              onChange={(e) => setTestSessionId(e.target.value)}
              style={{ flex: 1 }}
            />
          </div>
          <button className="btn" onClick={handleTest} disabled={testing || !testSessionId.trim()}>
            {testing ? "Running..." : "Run Test"}
          </button>
        </div>
        {testResult && (
          <pre style={{ marginTop: 12, fontSize: 12, background: "var(--bg-hover)", padding: 12, borderRadius: 6, overflow: "auto", maxHeight: 400, whiteSpace: "pre-wrap" }}>
            {JSON.stringify(testResult, null, 2)}
          </pre>
        )}
      </div>

      {/* Prompt edit modal */}
      {editingPrompt && (
        <div className="modal-overlay" onMouseDown={() => setEditingPrompt(null)}>
          <div className="modal" style={{ maxWidth: 700 }} onMouseDown={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{isCreating ? "New Prompt" : `Edit Prompt: ${editingPrompt.name}`}</h3>
              <div className="modal-subtitle">{editingPrompt.category} prompt</div>
            </div>
            {isCreating && (
              <div style={{ marginBottom: 12 }}>
                <label>
                  <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Name</span>
                  <input
                    className="search-input"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder="Prompt name"
                    style={{ width: "100%", fontSize: 13 }}
                  />
                </label>
              </div>
            )}
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              rows={16}
              style={{ width: "100%", fontFamily: "monospace", fontSize: 12, padding: 10, border: "1px solid var(--border)", borderRadius: 6, resize: "vertical" }}
            />

            {/* Output Schema Editor */}
            {editingPrompt.category === "judge" && (
              <div style={{ marginTop: 16 }}>
                <div style={{ fontWeight: 500, marginBottom: 8 }}>Output Schema</div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
                  Define JSON fields the judge must return. The schema is auto-appended to the prompt.
                </div>
                {editSchema.map((field, i) => {
                  const isDefault = DEFAULT_SCHEMA_FIELD_NAMES.has(field.name);
                  return (
                  <div key={i} style={{ display: "flex", gap: 6, marginBottom: 4, alignItems: "center" }}>
                    <input
                      className="search-input"
                      value={field.name}
                      disabled={isDefault}
                      onChange={(e) => {
                        const next = [...editSchema];
                        next[i] = { ...next[i], name: e.target.value };
                        setEditSchema(next);
                      }}
                      placeholder="field_name"
                      style={{ flex: 2, fontSize: 12, padding: "3px 6px", fontFamily: "monospace", opacity: isDefault ? 0.6 : 1 }}
                    />
                    <select
                      value={field.type}
                      disabled={isDefault}
                      onChange={(e) => {
                        const next = [...editSchema];
                        next[i] = { ...next[i], type: e.target.value as SchemaField["type"] };
                        setEditSchema(next);
                      }}
                      style={{ flex: 1, fontSize: 12, padding: "3px 6px", opacity: isDefault ? 0.6 : 1 }}
                    >
                      <option value="string">string</option>
                      <option value="numeric">numeric</option>
                      <option value="boolean">boolean</option>
                      <option value="array">array</option>
                    </select>
                    <label style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 12, opacity: isDefault ? 0.6 : 1 }}>
                      <input
                        type="checkbox"
                        checked={field.required ?? false}
                        disabled={isDefault}
                        onChange={(e) => {
                          const next = [...editSchema];
                          next[i] = { ...next[i], required: e.target.checked };
                          setEditSchema(next);
                        }}
                      />
                      Req
                    </label>
                    <input
                      className="search-input"
                      value={field.description || ""}
                      onChange={(e) => {
                        const next = [...editSchema];
                        next[i] = { ...next[i], description: e.target.value };
                        setEditSchema(next);
                      }}
                      placeholder="description"
                      style={{ flex: 3, fontSize: 12, padding: "3px 6px" }}
                    />
                    {!isDefault && (
                      <button
                        className="btn btn-secondary"
                        style={{ padding: "2px 6px", fontSize: 11 }}
                        onClick={() => setEditSchema(editSchema.filter((_, j) => j !== i))}
                      >
                        X
                      </button>
                    )}
                  </div>
                  );
                })}
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: 11, padding: "3px 8px" }}
                    disabled={editSchema.length >= MAX_SCHEMA_FIELDS}
                    onClick={() => setEditSchema([...editSchema, { name: "", type: "string", required: false, description: "" }])}
                  >
                    + Add Field
                  </button>
                  <span style={{ fontSize: 11, color: "var(--text-muted)" }}>({editSchema.length}/{MAX_SCHEMA_FIELDS})</span>
                </div>
              </div>
            )}

            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setEditingPrompt(null)}>Cancel</button>
              <button className="btn" onClick={handleSavePrompt} disabled={isCreating && !editName.trim()}>
                {isCreating ? "Create Prompt" : "Save Prompt"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
