import { useEffect, useState } from "react";
import {
  api,
  QuestionDefinition,
  RawSurveyDefinition,
} from "../api.ts";

export default function StudyConfig() {
  const [surveys, setSurveys] = useState<Record<string, RawSurveyDefinition>>({});
  const [activeSurveyId, setActiveSurveyId] = useState("");
  const [questions, setQuestions] = useState<Record<string, QuestionDefinition>>({});
  const [expandedSurvey, setExpandedSurvey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Inline add-question form state (shown inside a survey)
  const [addingToSurvey, setAddingToSurvey] = useState<string | null>(null);
  const [qLabel, setQLabel] = useState("");
  const [qDescription, setQDescription] = useState("");
  const [qType, setQType] = useState<"number" | "text">("number");
  const [qSuffix, setQSuffix] = useState("");
  const [qMin, setQMin] = useState("");
  const [qMax, setQMax] = useState("");
  const [qRequired, setQRequired] = useState(true);
  const [qError, setQError] = useState("");
  const [qSubmitting, setQSubmitting] = useState(false);

  // Add Survey modal state
  const [showAddSurvey, setShowAddSurvey] = useState(false);
  const [sName, setSName] = useState("");
  const [sDescription, setSDescription] = useState("");
  const [sQuestions, setSQuestions] = useState<string[]>([]);
  const [sError, setSError] = useState("");
  const [sSubmitting, setSSubmitting] = useState(false);

  useEffect(() => {
    Promise.all([
      api.questions().then(setQuestions),
      api.surveys().then((d) => {
        setSurveys(d.surveys);
        setActiveSurveyId(d.active);
      }),
    ]).finally(() => setLoading(false));
  }, []);

  const handleSetActive = async (surveyId: string) => {
    try {
      const result = await api.setActiveSurvey(surveyId);
      setActiveSurveyId(result.active);
    } catch (e) {
      console.error("Failed to set active survey:", e);
    }
  };

  const handleDeleteSurvey = async (surveyId: string) => {
    if (!confirm("Delete this survey?")) return;
    try {
      const result = await api.deleteSurvey(surveyId);
      setSurveys(result.surveys);
      setActiveSurveyId(result.active);
      if (expandedSurvey === surveyId) setExpandedSurvey(null);
    } catch (e) {
      alert((e as Error).message);
    }
  };

  // --- Question CRUD ---
  const resetQuestionForm = () => {
    setQLabel("");
    setQDescription("");
    setQType("number");
    setQSuffix("");
    setQMin("");
    setQMax("");
    setQRequired(true);
    setQError("");
  };

  const handleAddQuestion = async (surveyId: string) => {
    if (!qLabel || !qType) {
      setQError("Label and Type are required");
      return;
    }
    setQSubmitting(true);
    setQError("");
    try {
      const payload: Parameters<typeof api.createQuestion>[0] = {
        label: qLabel,
        type: qType,
        description: qDescription,
        suffix: qSuffix,
        required: qRequired,
      };
      if (qType === "number") {
        if (qMin) payload.min = parseFloat(qMin);
        if (qMax) payload.max = parseFloat(qMax);
      }
      const updatedQuestions = await api.createQuestion(payload);
      setQuestions(updatedQuestions);

      // Find the new question ID and add it to the survey
      const existingIds = new Set(Object.keys(questions));
      const newId = Object.keys(updatedQuestions).find((id) => !existingIds.has(id));
      if (newId) {
        const survey = surveys[surveyId];
        if (survey) {
          const result = await api.updateSurvey(surveyId, {
            questions: [...survey.questions, newId],
          });
          setSurveys(result.surveys);
          setActiveSurveyId(result.active);
        }
      }

      setAddingToSurvey(null);
      resetQuestionForm();
    } catch (e: unknown) {
      setQError(e instanceof Error ? e.message : "Failed to add question");
    } finally {
      setQSubmitting(false);
    }
  };

  // --- Survey CRUD ---
  const resetSurveyForm = () => {
    setSName("");
    setSDescription("");
    setSQuestions([]);
    setSError("");
  };

  const handleAddSurvey = async () => {
    if (!sName || sQuestions.length === 0) {
      setSError("Name and at least one question are required");
      return;
    }
    setSSubmitting(true);
    setSError("");
    try {
      const result = await api.createSurvey({
        name: sName,
        description: sDescription,
        questions: sQuestions,
      });
      setSurveys(result.surveys);
      setActiveSurveyId(result.active);
      setShowAddSurvey(false);
      resetSurveyForm();
    } catch (e: unknown) {
      setSError(e instanceof Error ? e.message : "Failed to add survey");
    } finally {
      setSSubmitting(false);
    }
  };

  const toggleSurveyQuestion = (qid: string) => {
    setSQuestions((prev) =>
      prev.includes(qid) ? prev.filter((id) => id !== qid) : [...prev, qid]
    );
  };

  const removeQuestionFromSurvey = async (surveyId: string, questionId: string) => {
    const survey = surveys[surveyId];
    if (!survey) return;
    const updated = survey.questions.filter((qid) => qid !== questionId);
    if (updated.length === 0) return; // don't allow empty
    try {
      const result = await api.updateSurvey(surveyId, { questions: updated });
      setSurveys(result.surveys);
      setActiveSurveyId(result.active);
    } catch (e) {
      console.error("Failed to remove question from survey:", e);
    }
  };

  const surveysList = Object.values(surveys);
  const questionsList = Object.values(questions);

  return (
    <div>
      <h2 className="page-title">Session Survey</h2>

      {/* ===== Surveys Section ===== */}
      <h3 style={{ margin: "24px 0 12px", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 12 }}>
        Surveys
        <button className="btn" style={{ fontSize: 13, padding: "6px 14px" }} onClick={() => setShowAddSurvey(true)}>
          + Add Survey
        </button>
      </h3>

      {loading ? (
        <div className="empty">Loading...</div>
      ) : surveysList.length === 0 ? (
        <div className="empty">No surveys defined yet.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {surveysList.map((s) => {
            const isActive = s.id === activeSurveyId;
            const isExpanded = expandedSurvey === s.id;
            const surveyQuestions = s.questions
              .map((qid) => questions[qid])
              .filter(Boolean);
            return (
              <div
                key={s.id}
                className="stat-card"
                style={{
                  maxWidth: 800,
                  border: isActive ? "1px solid #22c55e" : undefined,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setExpandedSurvey(isExpanded ? null : s.id);
                  setAddingToSurvey(null);
                  resetQuestionForm();
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontWeight: 600 }}>{s.name}</span>
                      {isActive && (
                        <span style={{ color: "#22c55e", fontSize: 12, fontWeight: 600 }}>Active</span>
                      )}
                    </div>
                    {s.description && (
                      <div style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 2 }}>{s.description}</div>
                    )}
                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                      {s.questions.length} question{s.questions.length !== 1 ? "s" : ""}
                      {" \u2014 "}
                      <span>click to {isExpanded ? "collapse" : "expand"}</span>
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 6, marginLeft: 16 }}>
                    {!isActive && (
                      <button
                        className="btn"
                        style={{ fontSize: 12, padding: "4px 10px" }}
                        onClick={(e) => { e.stopPropagation(); handleSetActive(s.id); }}
                      >
                        Set Active
                      </button>
                    )}
                    {!isActive && (
                      <button
                        className="btn btn-secondary"
                        style={{ fontSize: 12, padding: "4px 10px", color: "#dc2626" }}
                        onClick={(e) => { e.stopPropagation(); handleDeleteSurvey(s.id); }}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </div>

                {isExpanded && (
                  <div
                    style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {surveyQuestions.length > 0 && (
                      <table style={{ margin: 0, tableLayout: "auto" }}>
                        <thead>
                          <tr>
                            <th style={{ whiteSpace: "normal" }}>Question</th>
                            <th style={{ width: 70 }}>Type</th>
                            <th style={{ width: 80 }}></th>
                          </tr>
                        </thead>
                        <tbody>
                          {surveyQuestions.map((q) => (
                            <tr key={q.id}>
                              <td style={{ whiteSpace: "normal", wordBreak: "break-word" }}>{q.label}</td>
                              <td>{q.type}</td>
                              <td>
                                {s.questions.length > 1 && (
                                  <button
                                    className="btn btn-secondary"
                                    style={{ fontSize: 11, padding: "2px 8px" }}
                                    onClick={() => removeQuestionFromSurvey(s.id, q.id)}
                                  >
                                    Remove
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}

                    {/* Add question inline */}
                    {addingToSurvey === s.id ? (
                      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                        <input
                          className="search-input"
                          type="text"
                          value={qLabel}
                          onChange={(e) => setQLabel(e.target.value)}
                          placeholder="Question text"
                          autoFocus
                          style={{ width: "100%", maxWidth: "none" }}
                        />
                        <div style={{ display: "flex", gap: 8 }}>
                          <select
                            value={qType}
                            onChange={(e) => setQType(e.target.value as "number" | "text")}
                            style={{ fontSize: 12, padding: "4px 6px" }}
                          >
                            <option value="number">number</option>
                            <option value="text">text</option>
                          </select>
                          <input
                            className="search-input"
                            type="text"
                            value={qSuffix}
                            onChange={(e) => setQSuffix(e.target.value)}
                            placeholder="Suffix (e.g. x, min)"
                            style={{ flex: 1, fontSize: 12, maxWidth: "none" }}
                          />
                          {qType === "number" && (
                            <>
                              <input
                                className="search-input"
                                type="number"
                                value={qMin}
                                onChange={(e) => setQMin(e.target.value)}
                                placeholder="Min"
                                style={{ width: 60, fontSize: 12, maxWidth: "none" }}
                              />
                              <input
                                className="search-input"
                                type="number"
                                value={qMax}
                                onChange={(e) => setQMax(e.target.value)}
                                placeholder="Max"
                                style={{ width: 60, fontSize: 12, maxWidth: "none" }}
                              />
                            </>
                          )}
                        </div>
                        {qError && <p style={{ color: "#dc2626", fontSize: 12, margin: 0 }}>{qError}</p>}
                        <div style={{ display: "flex", gap: 8 }}>
                          <button
                            className="btn"
                            style={{ fontSize: 12, padding: "4px 10px" }}
                            disabled={qSubmitting}
                            onClick={() => handleAddQuestion(s.id)}
                          >
                            {qSubmitting ? "Adding..." : "Add"}
                          </button>
                          <button
                            className="btn btn-secondary"
                            style={{ fontSize: 12, padding: "4px 10px" }}
                            onClick={() => { setAddingToSurvey(null); resetQuestionForm(); }}
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <button
                        className="btn"
                        style={{ fontSize: 12, padding: "4px 10px", marginTop: 12 }}
                        onClick={() => setAddingToSurvey(s.id)}
                      >
                        + Add Question
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ===== Add Survey modal ===== */}
      {showAddSurvey && (
        <div className="modal-overlay" onClick={() => { setShowAddSurvey(false); resetSurveyForm(); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modal-header">
              <h3>Add Survey</h3>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <label>
                <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Name</span>
                <input className="search-input" type="text" value={sName} onChange={(e) => setSName(e.target.value)} placeholder="Survey name" style={{ width: "100%", maxWidth: "none" }} />
              </label>
              <label>
                <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>Description</span>
                <input className="search-input" type="text" value={sDescription} onChange={(e) => setSDescription(e.target.value)} placeholder="Optional description" style={{ width: "100%", maxWidth: "none" }} />
              </label>
              <div>
                <span style={{ fontSize: 13, color: "var(--text-muted)", display: "block", marginBottom: 8 }}>Questions</span>
                {questionsList.length === 0 ? (
                  <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No questions available. Add questions first.</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {questionsList.map((q) => (
                      <label key={q.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                        <input
                          type="checkbox"
                          checked={sQuestions.includes(q.id)}
                          onChange={() => toggleSurveyQuestion(q.id)}
                        />
                        {q.label}
                      </label>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {sError && <p style={{ color: "#dc2626", fontSize: 12, marginTop: 8 }}>{sError}</p>}

            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => { setShowAddSurvey(false); resetSurveyForm(); }}>
                Cancel
              </button>
              <button className="btn" disabled={sSubmitting} onClick={handleAddSurvey}>
                {sSubmitting ? "Adding..." : "Add Survey"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
