interface SyncStatusProps {
  lastPushAt: string | null;
  lastPullAt: string | null;
}

export default function SyncStatus({ lastPushAt, lastPullAt }: SyncStatusProps) {
  const lastSync = lastPushAt || lastPullAt;
  if (!lastSync) {
    return <span className="sync-status sync-status-never">Never synced</span>;
  }

  const elapsed = Date.now() - new Date(lastSync).getTime();
  const hours = elapsed / (1000 * 60 * 60);

  let colorClass: string;
  if (hours < 1) {
    colorClass = "sync-status-recent";
  } else if (hours < 24) {
    colorClass = "sync-status-ok";
  } else {
    colorClass = "sync-status-stale";
  }

  const timeAgo = hours < 1
    ? `${Math.round(hours * 60)}m ago`
    : hours < 24
      ? `${Math.round(hours)}h ago`
      : `${Math.round(hours / 24)}d ago`;

  return <span className={`sync-status ${colorClass}`}>{timeAgo}</span>;
}
