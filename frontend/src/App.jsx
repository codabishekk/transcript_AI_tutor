import { useState } from "react";
import axios from "axios";

/**
 * AI YouTube Tutor - A modern interface for interacting with YouTube transcripts.
 */
function App() {
  const [url, setUrl] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  
  // UI States
  const [isProcessing, setIsProcessing] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [status, setStatus] = useState({ type: "", message: "" });

  const api = axios.create({
    baseURL: "http://localhost:5000",
  });

  const processVideo = async () => {
    if (!url) {
      setStatus({ type: "error", message: "Please paste a YouTube URL first!" });
      return;
    }

    setIsProcessing(true);
    setStatus({ type: "loading", message: "Extracting transcript and indexing..." });
    setAnswer("");
    
    try {
      const res = await api.post("/process", { url });
      setStatus({ type: "success", message: res.data.message || "Video processed successfully!" });
    } catch (err) {
      console.error(err);
      setStatus({ 
        type: "error", 
        message: err.response?.data?.error || "Failed to process video. Please check the URL." 
      });
    } finally {
      setIsProcessing(false);
    }
  };

  const askQuestion = async () => {
    if (!question) {
      setStatus({ type: "error", message: "What would you like to know?" });
      return;
    }

    setIsAsking(true);
    setStatus({ type: "loading", message: "Consulting the AI tutor..." });
    
    try {
      const res = await api.post("/ask", { question });
      setAnswer(res.data.answer);
      setStatus({ type: "success", message: "Answer generated!" });
    } catch (err) {
      console.error(err);
      setStatus({ 
        type: "error", 
        message: err.response?.data?.error || "Failed to get an answer. Is the video processed?" 
      });
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <div className="app-container">
      <header>
        <h1>AI YouTube Tutor</h1>
        <p className="subtitle">Learn anything from any video, instantly.</p>
      </header>

      <main className="input-section">
        {/* URL Input Area */}
        <div className="input-wrapper">
          <div className="input-group">
            <input
              type="text"
              placeholder="Paste YouTube Video URL (e.g., https://youtube.com/watch?v=...)"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={isProcessing}
            />
            <button onClick={processVideo} disabled={isProcessing}>
              {isProcessing ? (
                <span className="loading-dots">Processing</span>
              ) : (
                <>🚀 Process</>
              )}
            </button>
          </div>
        </div>

        {/* Question Input Area */}
        <div className="input-wrapper">
          <div className="input-group">
            <input
              type="text"
              placeholder="Ask a question about the video..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && askQuestion()}
              disabled={isAsking || isProcessing}
            />
            <button onClick={askQuestion} disabled={isAsking || isProcessing}>
              {isAsking ? (
                <span className="loading-dots">Thinking</span>
              ) : (
                <>💡 Ask AI</>
              )}
            </button>
          </div>
        </div>

        {/* Status Messaging */}
        {status.message && (
          <div className={`status-message status-${status.type}`}>
            {status.type === "loading" && "⏳"}
            {status.type === "success" && "✅"}
            {status.type === "error" && "❌"}
            {status.message}
          </div>
        )}

        {/* Results Area */}
        {answer && (
          <div className="result-container">
            <div className="result-header">Tutor's Response</div>
            <div className="answer-box">
              {answer}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;