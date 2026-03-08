import { SharingConfig } from "../api.ts";

interface SharingConfigDisplayProps {
  config: SharingConfig;
  editable?: boolean;
  onChange?: (config: SharingConfig) => void;
}

const STAT_LABELS: Record<string, string> = {
  tokens: "Token usage",
  cost: "Cost data",
  messages: "Message counts",
  tool_calls: "Tool call counts",
  uplift: "Uplift factors",
  compacted_transcripts: "Compacted transcripts",
  full_transcripts: "Full transcripts",
};

const LEVEL_LABELS: Record<number, string> = {
  1: "Aggregates only",
  2: "Aggregates + per-session summaries",
};

export default function SharingConfigDisplay({ config, editable, onChange }: SharingConfigDisplayProps) {
  const handleStatToggle = (stat: string) => {
    if (!editable || !onChange) return;
    onChange({
      ...config,
      stats: {
        ...config.stats,
        [stat]: !config.stats[stat as keyof typeof config.stats],
      },
    });
  };

  const handleLevelChange = (level: number) => {
    if (!editable || !onChange) return;
    onChange({ ...config, level });
  };

  return (
    <div className="sharing-config-display">
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 6 }}>Sharing Level</div>
        {editable ? (
          <select
            value={config.level}
            onChange={(e) => handleLevelChange(parseInt(e.target.value))}
            style={{ fontSize: 13 }}
          >
            <option value={1}>{LEVEL_LABELS[1]}</option>
            <option value={2}>{LEVEL_LABELS[2]}</option>
          </select>
        ) : (
          <div style={{ fontSize: 13, color: "var(--text-muted)" }}>
            {LEVEL_LABELS[config.level] || `Level ${config.level}`}
          </div>
        )}
      </div>

      <div style={{ fontWeight: 500, fontSize: 13, marginBottom: 8 }}>Shared Data</div>
      <div className="sharing-config-grid">
        {Object.entries(STAT_LABELS).map(([key, label]) => (
          <label
            key={key}
            className="toggle-row"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              cursor: editable ? "pointer" : "default",
              fontSize: 13,
            }}
          >
            <div
              className={`toggle ${config.stats[key as keyof typeof config.stats] ? "toggle-on" : ""}`}
              onClick={() => handleStatToggle(key)}
              style={{
                pointerEvents: editable ? "auto" : "none",
                opacity: editable ? 1 : 0.7,
              }}
            >
              <div className="toggle-knob" />
            </div>
            <span>{label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
