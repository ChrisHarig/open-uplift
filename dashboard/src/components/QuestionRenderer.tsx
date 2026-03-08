import { useState } from "react";
import type { QuestionDefinition } from "../api.ts";

interface Props {
  question: QuestionDefinition;
  value: number | null;
  onChange: (val: number) => void;
}

function validateDecimals(val: string, maxDecimals: number): boolean {
  if (!val.includes(".")) return true;
  const decimalPart = val.split(".")[1];
  return decimalPart.length <= maxDecimals;
}

export default function QuestionRenderer({ question, value, onChange }: Props) {
  const [showCustom, setShowCustom] = useState(false);
  const [custom, setCustom] = useState("");
  const [inputVal, setInputVal] = useState("");
  const [error, setError] = useState("");

  if (question.type === "number") {
    const validation = question.validation ?? question.custom_validation;
    const maxDecimals = validation?.max_decimals ?? 1;
    const min = validation?.min ?? 0;
    const max = validation?.max ?? 10000;
    const suffix = question.suffix ?? "";
    const placeholder = question.placeholder ?? "";

    const handleChange = (raw: string) => {
      // Strip suffix characters (x, min, etc.)
      const cleaned = raw.replace(/[xXa-zA-Z]/g, "").trim();
      setInputVal(raw);

      if (cleaned === "" || cleaned === ".") {
        setError("");
        return;
      }

      const num = parseFloat(cleaned);
      if (isNaN(num)) {
        setError("Must be a number");
        return;
      }

      if (!validateDecimals(cleaned, maxDecimals)) {
        setError(`At most ${maxDecimals} decimal place(s)`);
        return;
      }

      if (num < min || num > max) {
        setError(`Must be between ${min} and ${max}`);
        return;
      }

      setError("");
      onChange(num);
    };

    return (
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 6 }}>
          {question.label}
        </div>
        {question.description && (
          <p className="report-explanation">{question.description}</p>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input
            type="text"
            inputMode="decimal"
            className="search-input"
            placeholder={placeholder}
            value={inputVal}
            onChange={(e) => handleChange(e.target.value)}
            autoFocus
            style={{ maxWidth: 200 }}
          />
          {suffix && (
            <span style={{ fontSize: 14, color: "#666" }}>{suffix}</span>
          )}
        </div>
        {error && (
          <p style={{ color: "#e74c3c", fontSize: 12, marginTop: 4 }}>{error}</p>
        )}
      </div>
    );
  }

  // Fallback: select type (buttons) for backward compatibility
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 6 }}>
        {question.label}
      </div>
      {question.description && (
        <p className="report-explanation">{question.description}</p>
      )}

      {question.type === "select" && question.options && (
        <>
          <div className="speedup-grid">
            {question.options.map((opt) => (
              <button
                key={opt.value}
                className={`speedup-btn ${!showCustom && value === opt.value ? "speedup-btn-active" : ""}`}
                onClick={() => {
                  setShowCustom(false);
                  onChange(opt.value);
                }}
              >
                {opt.label}
              </button>
            ))}
            {question.allow_custom && (
              <button
                className={`speedup-btn ${showCustom ? "speedup-btn-active" : ""}`}
                onClick={() => setShowCustom(true)}
              >
                Other
              </button>
            )}
          </div>
          {showCustom && question.custom_validation && (
            <input
              type="number"
              className="search-input"
              placeholder=""
              min={question.custom_validation.min}
              max={question.custom_validation.max}
              step="0.1"
              value={custom}
              onChange={(e) => {
                setCustom(e.target.value);
                const v = parseFloat(e.target.value);
                if (!isNaN(v)) onChange(v);
              }}
              autoFocus
              style={{ marginTop: 8, maxWidth: 160 }}
            />
          )}
        </>
      )}
    </div>
  );
}
