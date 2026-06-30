function ResultPanel({ answer }) {
  if (!answer) return null;

  return (
    <div className="result-panel">
      <div className="result-panel__header">
        <div className="result-panel__accent" />
        <span className="result-panel__title">Tutor's Response</span>
      </div>
      <div className="result-panel__content">
        {answer}
      </div>
    </div>
  );
}

export default ResultPanel;
