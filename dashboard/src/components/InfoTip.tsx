import { useState, useRef, useEffect } from "react";

interface InfoTipProps {
  text: string;
}

export default function InfoTip({ text }: InfoTipProps) {
  const [visible, setVisible] = useState(false);
  const [flipBelow, setFlipBelow] = useState(false);
  const iconRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (visible && iconRef.current) {
      const rect = iconRef.current.getBoundingClientRect();
      setFlipBelow(rect.top < 80);
    }
  }, [visible]);

  return (
    <span
      ref={iconRef}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      style={{ position: "relative", display: "inline-flex", alignItems: "center", marginLeft: 6, cursor: "help" }}
    >
      <span
        aria-label="info"
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 16,
          height: 16,
          borderRadius: "50%",
          border: "1.5px solid var(--text-muted)",
          fontSize: 10,
          fontWeight: 700,
          color: "var(--text-muted)",
          lineHeight: 1,
          userSelect: "none",
        }}
      >
        i
      </span>
      {visible && (
        <span
          role="tooltip"
          style={{
            position: "absolute",
            left: "50%",
            transform: "translateX(-50%)",
            ...(flipBelow
              ? { top: "calc(100% + 8px)" }
              : { bottom: "calc(100% + 8px)" }),
            background: "var(--bg)",
            color: "var(--text)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "8px 12px",
            fontSize: 12,
            fontWeight: 400,
            lineHeight: 1.4,
            whiteSpace: "normal",
            width: 220,
            boxShadow: "0 4px 12px rgba(0,0,0,0.12)",
            zIndex: 100,
            textTransform: "none",
            letterSpacing: "normal",
            pointerEvents: "none",
          }}
        >
          {text}
        </span>
      )}
    </span>
  );
}
