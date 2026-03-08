import { useEffect, useState } from "react";
import { api, SurveyDefinition } from "../api.ts";
import QuestionRenderer from "./QuestionRenderer.tsx";

interface Props {
  sessionId: string;
  projectName?: string | null;
  onClose: () => void;
  onSubmitted: () => void;
}

export default function ReportForm({ sessionId, projectName, onClose, onSubmitted }: Props) {
  const [survey, setSurvey] = useState<SurveyDefinition | null>(null);
  const [answers, setAnswers] = useState<Record<string, number | null>>({});
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.activeSurvey().then((d) => setSurvey(d.survey));
  }, []);

  const allAnswered = survey
    ? survey.questions
        .filter((q) => q.required)
        .every((q) => answers[q.id] != null)
    : false;

  const handleSubmit = async () => {
    if (!survey || !allAnswered) return;
    setSubmitting(true);
    setError("");
    const cleanAnswers: Record<string, number> = {};
    for (const [k, v] of Object.entries(answers)) {
      if (v != null) cleanAnswers[k] = v;
    }
    try {
      await api.submitSurveyResponse(sessionId, survey.id, cleanAnswers, notes);
      onSubmitted();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to submit report");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{survey ? survey.name : "Loading..."}</h3>
          {projectName && <span className="modal-subtitle">{projectName}</span>}
        </div>

        {!survey ? (
          <p style={{ color: "#666", padding: "16px 0" }}>Loading survey...</p>
        ) : (
          <>
            {survey.questions.map((q) => (
              <QuestionRenderer
                key={q.id}
                question={q}
                value={answers[q.id] ?? null}
                onChange={(val) =>
                  setAnswers((prev) => ({ ...prev, [q.id]: val }))
                }
              />
            ))}

            <textarea
              className="report-notes"
              placeholder="Notes (optional)"
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />

            {error && <p className="report-error">{error}</p>}

            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={onClose}>
                Cancel
              </button>
              <button
                className="btn"
                disabled={!allAnswered || submitting}
                onClick={handleSubmit}
              >
                {submitting ? "Saving..." : "Submit"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
