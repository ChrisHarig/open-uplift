import React, { useEffect, useState, useCallback } from "react";
import { api, SyncStats, ApiKeyInfoExt, Scaffold, RunModeConfig, UserProfile } from "../api.ts";
import JobProgress from "../components/JobProgress.tsx";
import InfoTip from "../components/InfoTip.tsx";

export default function Settings() {
  const [syncing, setSyncing] = useState(false);
  const [result, setResult] = useState<SyncStats | null>(null);
  const [lastSynced, setLastSynced] = useState<string | null>(null);

  // API Keys
  const [apiKeys, setApiKeys] = useState<ApiKeyInfoExt[]>([]);
  const [newKeyProvider, setNewKeyProvider] = useState("anthropic");
  const [newKeyValue, setNewKeyValue] = useState("");
  const [addingKey, setAddingKey] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  // Scaffolds
  const [scaffolds, setScaffolds] = useState<Scaffold[]>([]);
  const [newScaffoldName, setNewScaffoldName] = useState("");
  const [newScaffoldDesc, setNewScaffoldDesc] = useState("");
  const [newToken, setNewToken] = useState<string | null>(null);

  // Run Modes
  const [runConfig, setRunConfig] = useState<RunModeConfig | null>(null);
  const [savingConfig, setSavingConfig] = useState(false);
  const [unprocessedJobId, setUnprocessedJobId] = useState<string | null>(null);
  const [runningUnprocessed, setRunningUnprocessed] = useState(false);

  // Developer Profile
  const [profile, setProfile] = useState<UserProfile>({ experience_description: "" });
  const [savedProfile, setSavedProfile] = useState<UserProfile>({ experience_description: "" });
  const [savingProfile, setSavingProfile] = useState(false);

  useEffect(() => {
    api.syncStatus().then((d) => setLastSynced(d.last_synced));
    api.apiKeys().then(setApiKeys);
    api.scaffolds().then(setScaffolds);
    api.getRunModeConfig().then(setRunConfig);
    api.getUserProfile().then((p) => {
      const safe = { experience_description: p.experience_description ?? "" };
      setProfile(safe);
      setSavedProfile(safe);
    });
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    setResult(null);
    try {
      const stats = await api.sync();
      setResult(stats);
      api.syncStatus().then((d) => setLastSynced(d.last_synced));
    } finally {
      setSyncing(false);
    }
  };

  const handleAddKey = async () => {
    if (!newKeyValue.trim()) return;
    setAddingKey(true);
    setTestResult(null);
    try {
      await api.addApiKey(newKeyProvider, "default", newKeyValue.trim());
      setNewKeyValue("");
      api.apiKeys().then(setApiKeys);
      setTestResult("Key stored successfully");
    } catch (e) {
      setTestResult(`Error: ${(e as Error).message}`);
    } finally {
      setAddingKey(false);
    }
  };

  const handleTestKey = async () => {
    if (!newKeyValue.trim()) return;
    setTestResult("Testing...");
    try {
      const res = await api.testApiKey(newKeyProvider, newKeyValue.trim());
      setTestResult(res.valid ? "Valid key" : `Invalid: ${res.error || "unknown error"}`);
    } catch (e) {
      setTestResult(`Error: ${(e as Error).message}`);
    }
  };

  const handleDeleteKey = async (provider: string, keyName: string) => {
    await api.deleteApiKey(provider, keyName);
    api.apiKeys().then(setApiKeys);
  };

  const handleAddScaffold = async () => {
    if (!newScaffoldName.trim()) return;
    try {
      const res = await api.createScaffold(newScaffoldName.trim(), newScaffoldDesc.trim());
      setNewToken(res.api_token);
      setNewScaffoldName("");
      setNewScaffoldDesc("");
      api.scaffolds().then(setScaffolds);
    } catch (e) {
      alert((e as Error).message);
    }
  };

  const handleDeleteScaffold = async (scaffoldId: string) => {
    await api.deleteScaffold(scaffoldId);
    api.scaffolds().then(setScaffolds);
  };

  // Run mode handlers
  const saveRunConfig = useCallback(async (newConfig: RunModeConfig) => {
    setSavingConfig(true);
    try {
      const saved = await api.setRunModeConfig(newConfig);
      setRunConfig(saved);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setSavingConfig(false);
    }
  }, []);

  const profileChanged = profile.experience_description !== savedProfile.experience_description;

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

  const handleRunUnprocessed = async () => {
    setRunningUnprocessed(true);
    try {
      const res = await api.runUnprocessed();
      if (res.job_id) {
        setUnprocessedJobId(res.job_id);
        window.dispatchEvent(new Event("job-created"));
      } else {
        alert("No unprocessed sessions found.");
      }
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setRunningUnprocessed(false);
    }
  };

  return (
    <div>
      <h2 className="page-title">Settings</h2>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="label">Data Directory</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>~/.open-uplift/</div>
        </div>
        <div className="stat-card">
          <div className="label">JSONL Sources</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>~/.claude/projects/</div>
        </div>
      </div>

      {/* Row 1: Profile + Sync */}
      <div className="chart-grid">
        <div className="chart-card">
          <h3 style={{ margin: "0 0 8px", fontSize: 14 }}>Developer Profile<InfoTip text="Helps the LLM judge estimate task times more accurately for your skill level." /></h3>
          <textarea
            className="search-input"
            style={{ height: 96, resize: "none", overflow: "auto", fontFamily: "inherit", marginBottom: 8, width: "100%", maxWidth: 480 }}
            placeholder='e.g. "5 years web dev, familiar with React, skill 7/10"'
            value={profile.experience_description}
            onChange={(e) => setProfile((p) => ({ ...p, experience_description: e.target.value }))}
          />
          <div>
            <button className="btn" onClick={handleSaveProfile} disabled={!profileChanged || savingProfile}>
              {savingProfile ? "Saving..." : "Save Profile"}
            </button>
          </div>
        </div>

        <div className="chart-card">
          <h3 style={{ margin: "0 0 8px", fontSize: 14 }}>Sync &amp; Processing</h3>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
            <button className="btn" onClick={handleSync} disabled={syncing}>
              {syncing ? "Syncing..." : "Sync Now"}
            </button>
            {lastSynced && (
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                Last: {new Date(lastSynced).toLocaleString()}
              </span>
            )}
          </div>
          {result && (
            <p style={{ fontSize: 12, margin: "0 0 8px" }}>
              {result.sessions_new} new, {result.sessions_updated} updated, {result.messages_added} messages
            </p>
          )}

          {runConfig && (
            <>
              <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginTop: 4 }}>
                <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
                  <div
                    className={`toggle ${runConfig.enabled ? "toggle-on" : ""}`}
                    onClick={() => saveRunConfig({ ...runConfig, enabled: !runConfig.enabled })}
                  >
                    <div className="toggle-knob" />
                  </div>
                  <div>
                    <div style={{ fontWeight: 500, fontSize: 13 }}>Scheduled batch<InfoTip text="Auto-runs compaction + judge on a schedule. Uses LLM API credits." /></div>
                  </div>
                </label>
              </div>

              {runConfig.enabled && (
                <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 8, fontSize: 12 }}>
                  <span>At</span>
                  <select
                    value={runConfig.start_hour}
                    onChange={(e) => saveRunConfig({ ...runConfig, start_hour: parseInt(e.target.value) })}
                    style={{ width: 96 }}
                    disabled={savingConfig}
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
                    disabled={savingConfig}
                  />
                  <span>hrs</span>
                </div>
              )}

              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
                <button
                  className="btn btn-secondary"
                  style={{ fontSize: 11, padding: "3px 10px" }}
                  onClick={handleRunUnprocessed}
                  disabled={runningUnprocessed || !!unprocessedJobId}
                >
                  {runningUnprocessed ? "Starting..." : "Run All Now"}
                </button>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Process unprocessed sessions</span>
              </div>
              {unprocessedJobId && (
                <JobProgress jobId={unprocessedJobId} onComplete={() => setUnprocessedJobId(null)} />
              )}
            </>
          )}
        </div>
      </div>

      {/* Row 2: API Keys + Scaffolds */}
      <div className="chart-grid">
        <div className="chart-card">
          <h3 style={{ margin: "0 0 8px", fontSize: 14 }}>API Keys</h3>
          {apiKeys.length > 0 && (
            <table style={{ marginBottom: 10 }}>
              <thead>
                <tr><th>Provider</th><th>Last Used</th><th></th></tr>
              </thead>
              <tbody>
                {apiKeys.map((k) => (
                  <tr key={`${k.provider}-${k.key_name}`}>
                    <td>
                      {k.provider}
                      {k.source === "env" && (
                        <span style={{ marginLeft: 6, fontSize: 9, padding: "1px 4px", background: "var(--bg-hover)", color: "var(--text-muted)", borderRadius: 3 }}>env</span>
                      )}
                    </td>
                    <td>{k.source === "env" ? "From environment" : k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : "Never"}</td>
                    <td>
                      {k.source !== "env" && (
                        <button className="btn btn-secondary" style={{ padding: "2px 6px", fontSize: 10 }} onClick={() => handleDeleteKey(k.provider, k.key_name)}>
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
            <select value={newKeyProvider} onChange={(e) => setNewKeyProvider(e.target.value)} style={{ flex: 1, fontSize: 12 }}>
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
              <option value="openrouter">OpenRouter</option>
              <option value="other">Other</option>
            </select>
          </div>
          <input className="search-input" type="password" style={{ fontSize: 12, marginBottom: 6 }} placeholder="API key (e.g. sk-...)" value={newKeyValue} onChange={(e) => setNewKeyValue(e.target.value)} />
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <button className="btn" style={{ fontSize: 12 }} onClick={handleAddKey} disabled={addingKey || !newKeyValue.trim()}>
              {addingKey ? "Storing..." : "Add"}
            </button>
            <button className="btn btn-secondary" style={{ fontSize: 12 }} onClick={handleTestKey} disabled={!newKeyValue.trim()}>Test</button>
            {testResult && (
              <span style={{ fontSize: 11, color: testResult.startsWith("Valid") || testResult.startsWith("Key stored") ? "#22c55e" : "#dc2626" }}>
                {testResult}
              </span>
            )}
          </div>
        </div>

      </div>

    </div>
  );
}
