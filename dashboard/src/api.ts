const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: `API error: ${res.status}` }));
    throw new Error(err.error || `API error: ${res.status}`);
  }
  return res.json();
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: `API error: ${res.status}` }));
    throw new Error(err.error || `API error: ${res.status}`);
  }
  return res.json();
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: `API error: ${res.status}` }));
    throw new Error(err.error || `API error: ${res.status}`);
  }
  return res.json();
}

export function fmt(n: number): string {
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + "B";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toLocaleString();
}

// --- Existing interfaces ---

export interface OverviewData {
  totals: {
    total_sessions: number;
    total_tokens: number;
    total_messages: number;
    total_tool_calls: number;
  };
  daily: { day: string; sessions: number; tokens: number }[];
  self_reports: {
    avg_speedup_factor: number;
    total_reports: number;
  };
}

export interface Session {
  session_id: string;
  tool_source: string;
  project_path: string | null;
  project_name: string | null;
  git_branch: string | null;
  started_at: string;
  ended_at: string | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_read_tokens: number;
  total_cache_create_tokens: number;
  message_count: number;
  tool_call_count: number;
  model_primary: string | null;
  has_report: number;
  compaction_current: number;
  judge_current: number;
  judge_success: string | null;
  org_name: string | null;
  is_local: number;
  continued_from: string | null;
  continuation_type: string | null;
  source_member: string | null;
}

export interface Project {
  project_name: string;
  project_path: string | null;
  session_count: number;
  total_tokens: number;
  total_messages: number;
  total_tool_calls: number;
  last_active: string;
  org_id: string | null;
  org_name: string | null;
  org_is_verified: number | null;
  org_mode: string | null;
}

export interface TokensByModel {
  model: string;
  tokens: number;
}

export interface TokensBySource {
  tool_source: string;
  tokens: number;
}

export interface TokensTimeseries {
  day: string;
  input_tokens: number;
  output_tokens: number;
  cache_read: number;
  cache_create: number;
}

export interface ToolUsage {
  tool: string;
  count: number;
}

export interface SelfReport {
  id: number;
  session_id: string | null;
  tool_source: string;
  timestamp: string;
  speedup_factor: number | null;
  notes: string;
  project_name: string | null;
}

export interface SelfReportSummary {
  summary: {
    total: number;
    avg_speedup_factor: number;
  };
}

export interface SyncStats {
  sessions_new: number;
  sessions_updated: number;
  messages_added: number;
}

// --- Survey system interfaces ---

export interface QuestionOption {
  label: string;
  value: number;
}

export interface QuestionDefinition {
  id: string;
  label: string;
  description: string;
  type: "select" | "text" | "number";
  options?: QuestionOption[];
  allow_custom?: boolean;
  custom_validation?: { min: number; max: number; type: string; max_decimals?: number };
  validation?: { min: number; max: number; type: string; max_decimals?: number };
  suffix?: string;
  placeholder?: string;
  required: boolean;
}

export interface OutputDefinition {
  id: string;
  name: string;
  description: string;
}

export interface RawSurveyDefinition {
  id: string;
  name: string;
  description: string;
  questions: string[];
  scripts: unknown[];
  outputs: OutputDefinition[];
}

export interface SurveyDefinition {
  id: string;
  name: string;
  description: string;
  questions: QuestionDefinition[];
  scripts: unknown[];
  outputs: OutputDefinition[];
}

export interface UpliftOutput {
  output_id: string;
  uplift_factor: number;
  metadata: Record<string, unknown>;
}

export interface SessionUpliftOutput {
  output_id: string;
  uplift_factor: number;
  metadata: Record<string, unknown>;
  timestamp: string;
}

export interface SurveyResponse {
  id: number;
  session_id: string | null;
  survey_id: string;
  tool_source: string;
  timestamp: string;
  answers: Record<string, number>;
  notes: string;
  project_name?: string | null;
  outputs: UpliftOutput[];
}

export interface UpliftSummary {
  total_responses: number;
  total_measured_sessions: number;
  outputs: {
    output_id: string;
    count: number;
    avg_uplift: number;
  }[];
}

// --- Transcript interfaces ---

export interface TranscriptContentBlock {
  type: "text" | "thinking" | "tool_use";
  text?: string;
  tool_name?: string;
  input?: Record<string, unknown>;
  result?: string | null;
  is_error?: boolean;
}

export interface TranscriptEntry {
  role: "user" | "assistant";
  timestamp: string;
  blocks: TranscriptContentBlock[];
}

export interface TranscriptData {
  transcript: TranscriptEntry[];
  stats: {
    user_messages: number;
    assistant_messages: number;
    tool_calls: number;
  };
}

// --- API Key interfaces ---

export interface ApiKeyInfo {
  provider: string;
  key_name: string;
  created_at: string;
  last_used_at: string | null;
}

// --- Scaffold interfaces ---

export interface Scaffold {
  scaffold_id: string;
  display_name: string;
  description: string;
  created_at: string;
}

// --- Script Config ---

export interface ScriptSettings {
  provider: string;
  model: string;
  prompt_id: string;
}

export interface JudgeSettings extends ScriptSettings {
  include_profile?: boolean;
}

export interface ScriptConfig {
  compaction: ScriptSettings;
  judge: JudgeSettings;
}

// Backward-compat interface for /api/llm-config endpoint
export interface LLMConfig {
  judge_provider: string;
  judge_model: string;
  judge_prompt_id: string;
  judge_include_profile: boolean;
  compaction_provider: string;
  compaction_model: string;
  compaction_prompt_id: string;
}

// --- Prompt interfaces ---

export interface SchemaField {
  name: string;
  type: "boolean" | "numeric" | "string" | "array";
  required?: boolean;
  description?: string;
}

export interface JudgeOutput {
  field_name: string;
  value: unknown;
  value_text: string;
  value_numeric: number | null;
  value_type: string;
  prompt_id: string | null;
  created_at: string;
}

export interface JudgeOutputSummary {
  field_name: string;
  value_type: string;
  count: number;
  avg_numeric: number | null;
  true_count: number;
  rate?: number;
}

export interface JudgeOutputSummaryResponse {
  fields: JudgeOutputSummary[];
  total_judged_sessions: number;
}

export interface Prompt {
  prompt_id: string;
  category: string;
  name: string;
  description: string;
  system_prompt: string;
  created_at: string;
  is_default: number;
  output_schema?: SchemaField[] | null;
  version?: number;
  parent_prompt_id?: string | null;
  archived_at?: string | null;
}

// --- Script Result interfaces ---

export interface ScriptResult {
  id: number;
  session_id: string;
  script_id: string;
  status: string;
  result: Record<string, unknown> | null;
  error: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  started_at: string | null;
  completed_at: string | null;
  prompt_id: string | null;
  session_message_count: number | null;
}

// --- Time Measurement ---

export interface TimeMeasurement {
  time: {
    active_minutes: number;
    total_windows: number;
    active_windows: number;
    first_message: string | null;
    last_message: string | null;
  };
  concurrency: {
    raw_minutes: number;
    adjusted_minutes: number;
    concurrent_sessions: number;
  };
}

// --- Uplift Analytics ---

export interface UpliftDistribution {
  buckets: { lo: number; hi: number; count: number }[];
  values: number[];
  stats: { count: number; avg: number; median: number; min: number; max: number };
}

export interface UpliftTimeseries {
  day: string;
  avg_uplift: number;
  count: number;
}

export interface UpliftByGroup {
  project_name?: string;
  scaffold?: string;
  model?: string;
  avg_uplift: number;
  count: number;
}

export interface UpliftAgreement {
  session_id: string;
  human: number;
  llm: number;
}

export interface UpliftConcurrency {
  session_id: string;
  uplift_factor: number;
  concurrent_sessions: number;
  adjusted_minutes: number;
}

// --- Job Queue ---

export interface JobProgress {
  total: number;
  completed: number;
  failed: number;
  current_session_id: string | null;
  last_error: string | null;
}

export interface Job {
  id: string;
  job_type: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  payload: { scripts?: string[]; session_ids?: string[] };
  progress: JobProgress;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// --- User Profile ---

export interface UserProfile {
  experience_description: string;
}

// --- Run Mode Config ---

export interface RunModeConfig {
  enabled: boolean;
  start_hour: number;
  frequency_hours: number;
}

// --- Filter Options ---

export interface FilterOptions {
  models: string[];
  scaffolds: string[];
  projects: string[];
}

// --- Organization interfaces ---

export interface Organization {
  org_id: string;
  name: string;
  description: string;
  is_verified: number;
  created_at: string;
  folder_count: number;
  org_mode?: "hub" | "member";
}

export interface OrgFolder {
  folder_path: string;
  added_at: string;
}

export interface OrgDetail {
  org_id: string;
  name: string;
  description: string;
  is_verified: number;
  created_at: string;
  org_mode?: "hub" | "member";
  pushed_sessions_count?: number;
  folders: OrgFolder[];
  stats: {
    total_sessions: number;
    total_tokens: number;
    total_messages: number;
    total_cost: number;
  };
  unpushed_count?: number;
  judged_unpushed_count?: number;
  needs_judging_count?: number;
  pulled_session_count?: number;
  pushed_aggregate_only?: boolean;
}

export interface ApiKeyInfoExt extends ApiKeyInfo {
  source?: string;
}

export interface OrgAnalytics {
  totals: { total_sessions: number; total_tokens: number; total_messages: number; total_tool_calls: number; total_cost: number };
  uplift: { count: number; avg_uplift: number };
  daily: { day: string; sessions: number; tokens: number; cost: number }[];
  uplift_timeseries: { day: string; avg_uplift: number; count: number }[];
}

export interface OrgRemoteAggregate {
  aggregate: {
    total_sessions: number;
    total_tokens: number;
    total_cost_usd: number;
    total_messages: number;
    avg_uplift_factor: number | null;
    member_count?: number;
  } | null;
  pulled_at: string | null;
}

export interface UnassignedFolder {
  project_path: string;
  project_name: string;
}

// --- Org Hub Info ---

export interface HubMember {
  member_name: string;
  role: string;
  joined_at: string | null;
  last_push_at: string | null;
  sessions_pushed?: number;
  avg_uplift?: number | null;
  has_sessions?: boolean;
  aggregate_only?: boolean;
}

export interface HubInvite {
  invite_code: string;
  created_by: string | null;
  created_at: string;
  revoked_at: string | null;
}

export interface OrgHubInfo {
  org_id: string;
  org_name: string;
  sharing_config: SharingConfig;
  members: HubMember[];
  invites: HubInvite[];
}

// --- Org Membership interfaces (hub sync) ---

export interface OrgMembership {
  org_id: string;
  org_name: string | null;
  member_name: string | null;
  role: string;
  hub_url: string | null;
  api_key: string | null;
  sharing_config: string | null;
  pull_config: string | null;
  last_push_at: string | null;
  last_pull_at: string | null;
  joined_at: string | null;
}

export interface SharingConfig {
  level: number;
  stats: {
    tokens: boolean;
    cost: boolean;
    messages: boolean;
    tool_calls: boolean;
    uplift: boolean;
    compacted_transcripts: boolean;
    full_transcripts: boolean;
  };
}

export interface UnpushedSession {
  session_id: string;
  project_name: string | null;
  model_primary: string | null;
  started_at: string;
  ended_at: string | null;
  message_count: number;
  tool_call_count: number;
  total_tokens: number;
  total_cost_usd: number;
  updated_at: string | null;
  uplift_factor: number | null;
  judge_current: number;
}

export interface UnpushedSessionsResponse {
  sessions: UnpushedSession[];
  total: number;
  last_push_at: string | null;
  unjudged_count: number;
  stale_count: number;
}

export interface UnifiedOrg extends Organization {
  membership: OrgMembership | null;
}

// --- Setup State ---

export interface SetupState {
  has_sessions: boolean;
  has_profile: boolean;
  has_api_keys: boolean;
  has_scaffolds: boolean;
  has_organizations: boolean;
  welcome_dismissed: boolean;
}

// --- API client ---

export const api = {
  // Setup
  getSetupState: () => get<SetupState>("/setup/state"),
  dismissWelcome: () => post<{ status: string }>("/setup/dismiss-welcome"),

  overview: (days = 30) => get<OverviewData>(`/overview?days=${days}`),
  projects: (orgId?: string) =>
    get<Project[]>(orgId ? `/projects?org_id=${encodeURIComponent(orgId)}` : "/projects"),
  projectStats: (projectPath: string) =>
    get<Pick<Project, "session_count" | "total_tokens" | "total_messages" | "total_tool_calls" | "last_active">>(
      `/projects/stats?project_path=${encodeURIComponent(projectPath)}`
    ),
  sessions: (
    limit = 50,
    offset = 0,
    opts?: {
      project?: string;
      projectPath?: string;
      subfolders?: boolean;
      date_from?: string;
      date_to?: string;
      model?: string;
      scaffold?: string;
      has_survey?: string;
      has_judge?: string;
      has_compaction?: string;
      judge_success?: string;
      is_local?: string;
      org_id?: string;
      source_member?: string;
    }
  ) => {
    let url = `/sessions?limit=${limit}&offset=${offset}`;
    if (opts?.projectPath && opts?.subfolders) {
      url += `&project_path=${encodeURIComponent(opts.projectPath)}&subfolders=true`;
    } else if (opts?.project) {
      url += `&project=${encodeURIComponent(opts.project)}`;
    }
    if (opts?.date_from) url += `&date_from=${encodeURIComponent(opts.date_from)}`;
    if (opts?.date_to) url += `&date_to=${encodeURIComponent(opts.date_to)}`;
    if (opts?.model) url += `&model=${encodeURIComponent(opts.model)}`;
    if (opts?.scaffold) url += `&scaffold=${encodeURIComponent(opts.scaffold)}`;
    if (opts?.has_survey) url += `&has_survey=${opts.has_survey}`;
    if (opts?.has_judge) url += `&has_judge=${opts.has_judge}`;
    if (opts?.has_compaction) url += `&has_compaction=${opts.has_compaction}`;
    if (opts?.judge_success) url += `&judge_success=${opts.judge_success}`;
    if (opts?.is_local) url += `&is_local=${opts.is_local}`;
    if (opts?.org_id) url += `&org_id=${encodeURIComponent(opts.org_id)}`;
    if (opts?.source_member) url += `&source_member=${encodeURIComponent(opts.source_member)}`;
    return get<{ sessions: Session[]; total: number }>(url);
  },
  sessionDetail: (id: string) =>
    get<{ session: Session; messages: unknown[] }>(`/sessions/${id}`),
  tokensByModel: (opts?: { projectPath?: string; subfolders?: boolean }) => {
    let url = "/tokens/by-model";
    if (opts?.projectPath) {
      url += `?project_path=${encodeURIComponent(opts.projectPath)}`;
      if (opts.subfolders) url += "&subfolders=true";
    }
    return get<TokensByModel[]>(url);
  },
  tokensBySource: (opts?: { projectPath?: string; subfolders?: boolean }) => {
    let url = "/tokens/by-source";
    if (opts?.projectPath) {
      url += `?project_path=${encodeURIComponent(opts.projectPath)}`;
      if (opts.subfolders) url += "&subfolders=true";
    }
    return get<TokensBySource[]>(url);
  },
  tokensTimeseries: (days = 30, opts?: { projectPath?: string; subfolders?: boolean }) => {
    let url = `/tokens/timeseries?days=${days}`;
    if (opts?.projectPath) {
      url += `&project_path=${encodeURIComponent(opts.projectPath)}`;
      if (opts.subfolders) url += "&subfolders=true";
    }
    return get<TokensTimeseries[]>(url);
  },
  toolsUsage: () => get<ToolUsage[]>("/tools/usage"),

  // Legacy self-reports (backward compat)
  selfReports: () => get<SelfReport[]>("/self-reports"),
  selfReportsSummary: () => get<SelfReportSummary>("/self-reports/summary"),
  createSelfReport: (sessionId: string, speedupFactor: number, notes: string) =>
    post<{ id: number; session_id: string }>("/self-reports", {
      session_id: sessionId,
      speedup_factor: speedupFactor,
      notes,
    }),

  // Surveys
  activeSurvey: () => get<{ survey: SurveyDefinition }>("/surveys/active"),
  surveys: () => get<{ surveys: Record<string, RawSurveyDefinition>; active: string }>("/surveys"),
  setActiveSurvey: (surveyId: string) =>
    put<{ active: string }>("/surveys/active", { survey_id: surveyId }),
  questions: () => get<Record<string, QuestionDefinition>>("/questions"),
  createQuestion: (question: { label: string; type: string; description?: string; suffix?: string; required?: boolean; min?: number; max?: number }) =>
    post<Record<string, QuestionDefinition>>("/questions", question),
  createSurvey: (survey: { name: string; description?: string; questions: string[] }) =>
    post<{ surveys: Record<string, RawSurveyDefinition>; active: string }>("/surveys", survey),
  updateSurvey: (surveyId: string, updates: { questions?: string[]; name?: string; description?: string }) =>
    put<{ surveys: Record<string, RawSurveyDefinition>; active: string }>(`/surveys/${encodeURIComponent(surveyId)}`, updates),
  deleteSurvey: (surveyId: string) =>
    del<{ surveys: Record<string, RawSurveyDefinition>; active: string }>(`/surveys/${encodeURIComponent(surveyId)}`),

  // Survey responses
  surveyResponses: () => get<SurveyResponse[]>("/survey-responses"),
  submitSurveyResponse: (
    sessionId: string,
    surveyId: string,
    answers: Record<string, number>,
    notes: string
  ) =>
    post<{ id: number; session_id: string; outputs: UpliftOutput[] }>("/survey-responses", {
      session_id: sessionId,
      survey_id: surveyId,
      answers,
      notes,
    }),

  // Uplift outputs
  upliftSummary: (orgId?: string) =>
    get<UpliftSummary>(orgId ? `/uplift-outputs/summary?org_id=${encodeURIComponent(orgId)}` : "/uplift-outputs/summary"),
  upliftBySession: () => get<Record<string, Record<string, number>>>("/uplift-outputs/by-session"),
  sessionUpliftOutputs: (sessionId: string) =>
    get<SessionUpliftOutput[]>(`/sessions/${encodeURIComponent(sessionId)}/uplift-outputs`),

  // Transcripts
  transcript: (sessionId: string) => get<TranscriptData>(`/sessions/${sessionId}/transcript`),

  sync: () => post<SyncStats>("/sync"),
  syncStatus: () => get<{ last_synced: string | null }>("/sync/status"),

  // API Keys
  apiKeys: () => get<ApiKeyInfo[]>("/api-keys"),
  addApiKey: (provider: string, keyName: string, apiKey: string) =>
    post<{ status: string }>("/api-keys", { provider, key_name: keyName, api_key: apiKey }),
  deleteApiKey: (provider: string, keyName: string) =>
    del<{ status: string }>(`/api-keys/${encodeURIComponent(provider)}/${encodeURIComponent(keyName)}`),
  testApiKey: (provider: string, apiKey: string) =>
    post<{ valid: boolean; error?: string }>("/api-keys/test", { provider, api_key: apiKey }),
  apiKeyCost: (provider: string, keyName: string) =>
    get<{ balance_usd?: number; spend_usd?: number; window_days?: number; currency?: string; note?: string; error?: string }>(
      `/api-keys/${encodeURIComponent(provider)}/${encodeURIComponent(keyName)}/cost`,
    ),

  // Script Config
  getScriptConfig: () => get<ScriptConfig>("/script-config"),
  setScriptConfig: (config: ScriptConfig) => put<ScriptConfig>("/script-config", config),

  // Legacy LLM Config aliases
  getLLMConfig: () => get<LLMConfig>("/llm-config"),
  setLLMConfig: (config: LLMConfig) => put<LLMConfig>("/llm-config", config),

  // Scaffolds
  scaffolds: () => get<Scaffold[]>("/scaffolds"),
  createScaffold: (displayName: string, description?: string) =>
    post<{ scaffold_id: string; api_token: string }>("/scaffolds", { display_name: displayName, description }),
  deleteScaffold: (scaffoldId: string) =>
    del<{ status: string }>(`/scaffolds/${encodeURIComponent(scaffoldId)}`),

  // Prompts
  prompts: (category?: string, includeArchived?: boolean) => {
    const params: string[] = [];
    if (category) params.push(`category=${encodeURIComponent(category)}`);
    if (includeArchived) params.push("include_archived=true");
    return get<Prompt[]>(params.length ? `/prompts?${params.join("&")}` : "/prompts");
  },
  createPrompt: (prompt: { prompt_id: string; category: string; name: string; system_prompt: string; description?: string; output_schema?: SchemaField[] }) =>
    post<{ status: string }>("/prompts", prompt),
  updatePrompt: (promptId: string, updates: { name?: string; description?: string; system_prompt?: string; output_schema?: SchemaField[] | null }) =>
    put<{ status: string; new_prompt_id?: string; version?: number }>(`/prompts/${encodeURIComponent(promptId)}`, updates),
  deletePrompt: (promptId: string) =>
    del<{ status: string }>(`/prompts/${encodeURIComponent(promptId)}`),

  // Judge Outputs
  sessionJudgeOutputs: (sessionId: string) =>
    get<Record<string, JudgeOutput>>(`/sessions/${encodeURIComponent(sessionId)}/judge-outputs`),
  judgeOutputsSummary: (orgId?: string) =>
    get<JudgeOutputSummaryResponse>(orgId ? `/judge-outputs/summary?org_id=${encodeURIComponent(orgId)}` : "/judge-outputs/summary"),

  // Script Execution
  runScript: (scriptId: string, sessionId: string) =>
    post<Record<string, unknown>>("/scripts/run", { script_id: scriptId, session_id: sessionId }),
  scriptResults: (sessionId: string) =>
    get<ScriptResult[]>(`/scripts/results/${encodeURIComponent(sessionId)}`),
  runScriptBatch: (scriptId: string, sessionIds: string[]) =>
    post<Record<string, unknown>>("/scripts/run-batch", { script_id: scriptId, session_ids: sessionIds }),

  // Time Measurement
  sessionTime: (sessionId: string) =>
    get<TimeMeasurement>(`/sessions/${encodeURIComponent(sessionId)}/time`),

  // Uplift Analytics
  upliftDistribution: (outputId = "llm-judge", orgId?: string) =>
    get<UpliftDistribution>(`/uplift/distribution?output_id=${encodeURIComponent(outputId)}${orgId ? `&org_id=${encodeURIComponent(orgId)}` : ""}`),
  upliftTimeseries: (outputId = "llm-judge", days = 90) =>
    get<UpliftTimeseries[]>(`/uplift/timeseries?output_id=${encodeURIComponent(outputId)}&days=${days}`),
  upliftByProject: (outputId = "llm-judge", orgId?: string) =>
    get<UpliftByGroup[]>(`/uplift/by-project?output_id=${encodeURIComponent(outputId)}${orgId ? `&org_id=${encodeURIComponent(orgId)}` : ""}`),
  upliftByScaffold: (outputId = "llm-judge", orgId?: string) =>
    get<UpliftByGroup[]>(`/uplift/by-scaffold?output_id=${encodeURIComponent(outputId)}${orgId ? `&org_id=${encodeURIComponent(orgId)}` : ""}`),
  upliftByModel: (outputId = "llm-judge", orgId?: string) =>
    get<UpliftByGroup[]>(`/uplift/by-model?output_id=${encodeURIComponent(outputId)}${orgId ? `&org_id=${encodeURIComponent(orgId)}` : ""}`),
  upliftAgreement: () => get<UpliftAgreement[]>("/uplift/agreement"),
  upliftConcurrency: (outputId = "llm-judge") =>
    get<UpliftConcurrency[]>(`/uplift/concurrency?output_id=${encodeURIComponent(outputId)}`),

  // Job Queue
  jobs: (status?: string) =>
    get<Job[]>(status ? `/jobs?status=${encodeURIComponent(status)}` : "/jobs"),
  job: (jobId: string) => get<Job>(`/jobs/${encodeURIComponent(jobId)}`),
  cancelJob: (jobId: string) =>
    post<{ status: string }>(`/jobs/${encodeURIComponent(jobId)}/cancel`),

  // User Profile
  getUserProfile: () => get<UserProfile>("/config/user-profile"),
  setUserProfile: (profile: UserProfile) =>
    put<UserProfile>("/config/user-profile", profile),

  // Run Mode Config
  getRunModeConfig: () => get<RunModeConfig>("/config/run-modes"),
  setRunModeConfig: (config: RunModeConfig) =>
    put<RunModeConfig>("/config/run-modes", config),

  // Batch / unprocessed
  unprocessedCount: () => get<{ count: number }>("/scripts/unprocessed-count"),
  runUnprocessed: () =>
    post<{ job_id: string; session_count: number }>("/scripts/run-unprocessed"),
  runBatchAsync: (scripts: string[], sessionIds: string[]) =>
    post<{ job_id: string }>("/scripts/run-batch", { scripts, session_ids: sessionIds }),

  // Session filter options
  sessionFilterOptions: (orgId?: string) =>
    get<FilterOptions>(orgId ? `/sessions/filter-options?org_id=${encodeURIComponent(orgId)}` : "/sessions/filter-options"),

  // Organizations
  organizations: () => get<Organization[]>("/organizations"),
  createOrganization: (name: string, description?: string, folderPaths?: string[]) =>
    post<{ org_id: string; name: string; invite_code?: string; api_key?: string; org_mode?: string }>("/organizations", {
      name,
      description,
      folder_paths: folderPaths,
    }),
  organizationDetail: (orgId: string) =>
    get<OrgDetail>(`/organizations/${encodeURIComponent(orgId)}`),
  updateOrganization: (orgId: string, updates: { name?: string; description?: string; is_verified?: boolean }) =>
    put<{ status: string }>(`/organizations/${encodeURIComponent(orgId)}`, updates),
  deleteOrganization: (orgId: string) =>
    del<{ status: string }>(`/organizations/${encodeURIComponent(orgId)}`),
  addOrgFolders: (orgId: string, folderPaths: string[]) =>
    post<{ status: string }>(`/organizations/${encodeURIComponent(orgId)}/folders`, {
      folder_paths: folderPaths,
    }),
  removeOrgFolders: (orgId: string, folderPaths: string[]) =>
    post<{ status: string }>(`/organizations/${encodeURIComponent(orgId)}/remove-folders`, {
      folder_paths: folderPaths,
    }),
  unassignedFolders: () => get<UnassignedFolder[]>("/organizations/unassigned-folders"),
  dismissFolder: (folderPath: string) =>
    post<{ status: string }>("/organizations/dismiss-folder", { folder_path: folderPath }),
  organizationAnalytics: (orgId: string, outputId = "llm-judge", days = 90) =>
    get<OrgAnalytics>(
      `/organizations/${encodeURIComponent(orgId)}/analytics?output_id=${encodeURIComponent(outputId)}&days=${days}`
    ),
  organizationRemoteAggregate: (orgId: string) =>
    get<OrgRemoteAggregate>(`/organizations/${encodeURIComponent(orgId)}/remote-aggregate`),
  organizationHubInfo: (orgId: string) =>
    get<OrgHubInfo>(`/organizations/${encodeURIComponent(orgId)}/hub-info`),
  createHubInvite: (orgId: string) =>
    post<{ invite_code: string }>(`/organizations/${encodeURIComponent(orgId)}/hub-invites`),
  revokeHubInvite: (orgId: string, inviteCode: string) =>
    post<{ status: string }>(`/organizations/${encodeURIComponent(orgId)}/hub-invites/${encodeURIComponent(inviteCode)}/revoke`),
  unpushedSessions: (orgId: string) =>
    get<UnpushedSessionsResponse>(`/organizations/${encodeURIComponent(orgId)}/unpushed-sessions`),
  hubSessions: (orgId: string, member?: string) => {
    let url = `/organizations/${encodeURIComponent(orgId)}/hub-sessions`;
    if (member) url += `?member=${encodeURIComponent(member)}`;
    return get<Array<Record<string, unknown>>>(url);
  },
  deleteHubMember: (orgId: string, memberName: string) =>
    del<{ status: string }>(`/organizations/${encodeURIComponent(orgId)}/hub-members/${encodeURIComponent(memberName)}`),
  organizationUpliftByMember: (orgId: string) =>
    get<{member_name: string; avg_uplift: number; sessions: number}[]>(`/organizations/${encodeURIComponent(orgId)}/uplift-by-member`),
  updateSharingConfig: (orgId: string, sharingConfig: SharingConfig) =>
    put<{ status: string }>(`/organizations/${encodeURIComponent(orgId)}/sharing-config`, { sharing_config: sharingConfig }),

  // Org Memberships (hub sync)
  orgMemberships: () => get<OrgMembership[]>("/org-memberships"),
  joinOrg: (hubUrl: string, inviteCode: string, name: string) =>
    post<{ org_id: string; org_name: string; sharing_config: SharingConfig }>("/org-memberships/join", {
      hub_url: hubUrl,
      invite_code: inviteCode,
      name,
    }),
  syncOrg: (orgId: string) =>
    post<{ push: Record<string, unknown>; pull: Record<string, unknown> }>(`/org-memberships/${encodeURIComponent(orgId)}/sync`),
  pushOrg: (orgId: string) =>
    post<Record<string, unknown>>(`/org-memberships/${encodeURIComponent(orgId)}/push`),
  pullOrg: (orgId: string) =>
    post<Record<string, unknown>>(`/org-memberships/${encodeURIComponent(orgId)}/pull`),
  syncAllOrgs: () =>
    post<{ results: Record<string, unknown>[] }>("/org-memberships/sync-all"),
  pullConfig: (orgId: string) =>
    get<{ pull_config: SharingConfig | null; sharing_config: SharingConfig }>(`/org-memberships/${encodeURIComponent(orgId)}/pull-config`),
  updatePullConfig: (orgId: string, pullConfig: SharingConfig) =>
    put<{ status: string; pull_config: SharingConfig }>(`/org-memberships/${encodeURIComponent(orgId)}/pull-config`, { pull_config: pullConfig }),

  // Session Export
  exportSessions: (
    fmt: "csv" | "json",
    opts?: {
      session_ids?: string[];
      project?: string;
      projectPath?: string;
      subfolders?: boolean;
      date_from?: string;
      date_to?: string;
      model?: string;
      scaffold?: string;
      has_survey?: string;
      has_judge?: string;
      has_compaction?: string;
      judge_success?: string;
      is_local?: string;
      org_id?: string;
      include_judge?: boolean;
      include_survey?: boolean;
      include_transcript?: boolean;
      include_telemetry?: boolean;
    }
  ) => {
    let url = `${BASE}/sessions/export?format=${fmt}`;
    if (opts?.session_ids?.length) url += `&session_ids=${opts.session_ids.join(",")}`;
    if (opts?.projectPath && opts?.subfolders) {
      url += `&project_path=${encodeURIComponent(opts.projectPath)}&subfolders=true`;
    } else if (opts?.project) {
      url += `&project=${encodeURIComponent(opts.project)}`;
    }
    if (opts?.date_from) url += `&date_from=${encodeURIComponent(opts.date_from)}`;
    if (opts?.date_to) url += `&date_to=${encodeURIComponent(opts.date_to)}`;
    if (opts?.model) url += `&model=${encodeURIComponent(opts.model)}`;
    if (opts?.scaffold) url += `&scaffold=${encodeURIComponent(opts.scaffold)}`;
    if (opts?.has_survey) url += `&has_survey=${opts.has_survey}`;
    if (opts?.has_judge) url += `&has_judge=${opts.has_judge}`;
    if (opts?.has_compaction) url += `&has_compaction=${opts.has_compaction}`;
    if (opts?.judge_success) url += `&judge_success=${opts.judge_success}`;
    if (opts?.is_local) url += `&is_local=${opts.is_local}`;
    if (opts?.org_id) url += `&org_id=${encodeURIComponent(opts.org_id)}`;
    if (opts?.include_judge) url += "&include_judge=true";
    if (opts?.include_survey) url += "&include_survey=true";
    if (opts?.include_transcript) url += "&include_transcript=true";
    if (opts?.include_telemetry) url += "&include_telemetry=true";
    window.open(url);
  },
};
