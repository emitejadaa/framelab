export function Loader({ label }: { label: string }) {
  return (
    <div
      className="fl:flex fl:h-full fl:items-center fl:justify-center fl:gap-2"
      style={{ color: "var(--fl-muted)" }}
    >
      <span
        aria-hidden
        style={{
          width: 14,
          height: 14,
          borderRadius: "50%",
          border: "2px solid var(--fl-border)",
          borderTopColor: "var(--fl-accent)",
          animation: "fl-spin .8s linear infinite",
        }}
      />
      <span role="status">{label}</span>
    </div>
  );
}
