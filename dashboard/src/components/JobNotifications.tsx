import { useEffect, useState } from "react";
import { api, Job } from "../api.ts";

export default function JobNotifications() {
  const [activeJobs, setActiveJobs] = useState<Job[]>([]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = () => {
      api.jobs("pending,running").then((jobs) => {
        if (!active) return;
        setActiveJobs(jobs);
        timer = setTimeout(poll, jobs.length > 0 ? 2000 : 15000);
      }).catch(() => {
        if (active) timer = setTimeout(poll, 15000);
      });
    };
    poll();
    // Immediately re-poll when a job is created elsewhere
    const onJobCreated = () => {
      clearTimeout(timer);
      poll();
    };
    window.addEventListener("job-created", onJobCreated);
    return () => {
      active = false;
      clearTimeout(timer);
      window.removeEventListener("job-created", onJobCreated);
    };
  }, []);

  if (activeJobs.length === 0) return null;

  return (
    <div style={{
      position: "fixed",
      bottom: 16,
      right: 16,
      zIndex: 1000,
      display: "flex",
      flexDirection: "column",
      gap: 8,
      maxWidth: 340,
    }}>
      {activeJobs.map((job) => {
        const { progress } = job;
        const pct = progress.total > 0
          ? Math.round((progress.completed / progress.total) * 100)
          : 0;
        const label = job.job_type === "auto-survey"
          ? "Auto-run"
          : "Processing";

        return (
          <div
            key={job.id}
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "10px 14px",
              boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
              fontSize: 13,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontWeight: 500 }}>
                {label}: {job.status === "pending" ? "queued" : `${progress.completed}/${progress.total}`}
              </span>
              <button
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  fontSize: 11,
                  padding: "0 4px",
                }}
                onClick={() => api.cancelJob(job.id)}
                title="Cancel job"
              >
                Cancel
              </button>
            </div>
            <div style={{
              height: 4,
              background: "var(--border)",
              borderRadius: 2,
              overflow: "hidden",
            }}>
              <div style={{
                height: "100%",
                width: `${pct}%`,
                background: "#3b82f6",
                borderRadius: 2,
                transition: "width 0.3s ease",
              }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
