import { useEffect, useState, useRef } from "react";
import { api, Job } from "../api.ts";

interface Props {
  jobId: string;
  onComplete?: () => void;
  onProgress?: () => void;
}

export default function JobProgress({ jobId, onComplete, onProgress }: Props) {
  const [job, setJob] = useState<Job | null>(null);
  const prevCompleted = useRef(0);
  const onCompleteRef = useRef(onComplete);
  const onProgressRef = useRef(onProgress);
  onCompleteRef.current = onComplete;
  onProgressRef.current = onProgress;

  useEffect(() => {
    if (!jobId) return;
    prevCompleted.current = 0;
    let active = true;
    const poll = () => {
      api.job(jobId).then((j) => {
        if (!active) return;
        setJob(j);
        if (j.progress.completed > prevCompleted.current) {
          prevCompleted.current = j.progress.completed;
          onProgressRef.current?.();
        }
        if (j.status === "pending" || j.status === "running") {
          setTimeout(poll, 2000);
        } else {
          onCompleteRef.current?.();
        }
      }).catch(() => {
        if (active) setTimeout(poll, 2000);
      });
    };
    poll();
    return () => { active = false; };
  }, [jobId]);

  if (!job) return null;

  const { progress, status } = job;
  const pct = progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0;
  const done = status === "completed" || status === "failed" || status === "cancelled";

  const handleCancel = () => {
    api.cancelJob(jobId);
  };

  return (
    <div style={{
      padding: "8px 12px",
      background: "var(--bg-hover)",
      borderRadius: 6,
      marginBottom: 16,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 500 }}>
          {status === "pending" && "Waiting to start..."}
          {status === "running" && `Processing ${progress.completed}/${progress.total}`}
          {status === "completed" && `Completed ${progress.completed} sessions`}
          {status === "failed" && "Job failed"}
          {status === "cancelled" && `Cancelled (${progress.completed}/${progress.total} done)`}
          {progress.failed > 0 && ` (${progress.failed} failed)`}
        </span>
        {!done && (
          <button
            className="btn btn-secondary"
            style={{ padding: "2px 8px", fontSize: 11 }}
            onClick={handleCancel}
          >
            Cancel
          </button>
        )}
      </div>
      <div style={{
        height: 6,
        background: "var(--border)",
        borderRadius: 3,
        overflow: "hidden",
      }}>
        <div style={{
          height: "100%",
          width: `${pct}%`,
          background: status === "failed" ? "#dc2626" : status === "cancelled" ? "#f59e0b" : "#3b82f6",
          borderRadius: 3,
          transition: "width 0.3s ease",
        }} />
      </div>
      {progress.current_session_id && status === "running" && (
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
          Current: {progress.current_session_id.slice(0, 12)}...
        </div>
      )}
      {progress.last_error && progress.failed > 0 && (
        <div style={{ fontSize: 12, color: "#dc2626", marginTop: 6 }}>
          Error: {progress.last_error.length > 150 ? progress.last_error.slice(0, 150) + "..." : progress.last_error}
        </div>
      )}
    </div>
  );
}
