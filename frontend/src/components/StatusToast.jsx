const ICONS = {
  success: "check-circle",
  error: "alert-circle",
  loading: "loader",
};

function StatusToast({ type, message }) {
  if (!message) return null;

  return (
    <div className={`status-toast status-toast--${type}`}>
      <span className="status-toast__icon">
        {type === "success" && "✓"}
        {type === "error" && "!"}
        {type === "loading" && "⟳"}
      </span>
      {message}
    </div>
  );
}

export default StatusToast;
