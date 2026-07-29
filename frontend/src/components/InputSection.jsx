function InputSection({ isProcessing, isAsking, ...props }) {
  return (
    <div className="input-section">
      <div className="input-card">
        <span className="input-card__label">YouTube URL</span>
        <div className="input-card__row">
          <input
            type="text"
            placeholder="https://youtube.com/watch?v=..."
            value={props.url}
            onChange={(e) => props.setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && props.processVideo()}
            disabled={isProcessing}
          />
          <button
            className="btn btn--primary"
            onClick={props.processVideo}
            disabled={isProcessing}
          >
            {isProcessing ? (
              <><div className="spinner" /><span className="btn__text">Processing</span></>
            ) : (
              <span className="btn__text">Process</span>
            )}
          </button>
        </div>
      </div>

      <div className="input-card">
        <span className="input-card__label">Ask a Question</span>
        <div className="input-card__row">
          <input
            type="text"
            placeholder="What would you like to know about this video?"
            value={props.question}
            onChange={(e) => props.setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && props.askQuestion()}
            disabled={isAsking || isProcessing}
          />
          <button
            className="btn btn--secondary"
            onClick={props.askQuestion}
            disabled={isAsking || isProcessing}
          >
            {isAsking ? (
              <><div className="spinner spinner--sm" /><span className="btn__text">Thinking</span></>
            ) : (
              <span className="btn__text">Ask AI</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default InputSection;
