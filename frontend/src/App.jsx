import { useState } from "react";
import axios from "axios";

import Header from "./components/Header";
import InputSection from "./components/InputSection";
import StatusToast from "./components/StatusToast";
import ResultPanel from "./components/ResultPanel";

function App() {
  const [url, setUrl] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [status, setStatus] = useState({ type: "", message: "" });

  const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || "http://localhost:5000",
  });

  const friendlyErrors = {
    no_transcript: "There is no transcript available for this video.",
    auth_required: "This video requires signing in to YouTube to view its transcript.",
    ip_blocked: "YouTube is blocking requests from the server. Try again later.",
    video_unavailable: "This video is unavailable (private, removed, or deleted).",
    timed_out: "Transcript fetch timed out. Please try again in a moment.",
  };

  const getProcessError = (err) =>
    friendlyErrors[err.response?.data?.error_code] ||
    err.response?.data?.error ||
    (err.response ? `Server error (${err.response.status}). Please try again.` : err.message) ||
    "Failed to process video. Please check the URL.";

  // The Render backend sits behind Cloudflare and can cold-start (~30s) after
  // inactivity, during which the browser sees a CORS/network error (no error
  // body). Retry those transient failures a few times before surfacing.
  const postWithRetry = async (path, payload, { retries = 3, delay = 1500 } = {}) => {
    let lastErr;
    for (let attempt = 1; attempt <= retries; attempt++) {
      try {
        return await api.post(path, payload);
      } catch (err) {
        lastErr = err;
        const isServer5xx = err.response && err.response.status >= 500;
        const isNetworkError = !err.response && (err.message === "Network Error" || err.code === "ERR_NETWORK");
        if ((!isServer5xx && !isNetworkError) || attempt === retries) throw err;
        await new Promise((r) => setTimeout(r, delay * attempt));
      }
    }
    throw lastErr;
  };

  const processVideo = async () => {
    if (!url) {
      setStatus({ type: "error", message: "Please provide a YouTube URL!" });
      return;
    }

    setIsProcessing(true);
    setStatus({ type: "loading", message: "Extracting transcript and indexing..." });
    setAnswer("");

    try {
      const res = await postWithRetry("/process", { url });
      setStatus({ type: "success", message: res.data.message || "Video processed successfully!" });
    } catch (err) {
      console.error(err);
      setStatus({
        type: "error",
        message: getProcessError(err),
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
      const res = await postWithRetry("/ask", { question });
      setAnswer(res.data.answer);
      setStatus({ type: "success", message: "Answer generated!" });
    } catch (err) {
      console.error(err);
      setStatus({
        type: "error",
        message: err.response?.data?.error || "Failed to get an answer. Is the video processed?",
      });
    } finally {
      setIsAsking(false);
    }
  };

  return (
    <>
      <div className="orb orb--1" aria-hidden="true" />
      <div className="orb orb--2" aria-hidden="true" />
      <div className="orb orb--3" aria-hidden="true" />
      <div className="app-container">
        <Header />
        <InputSection
          url={url}
          setUrl={setUrl}
          question={question}
          setQuestion={setQuestion}
          processVideo={processVideo}
          askQuestion={askQuestion}
          isProcessing={isProcessing}
          isAsking={isAsking}
        />
        <StatusToast type={status.type} message={status.message} />
        <ResultPanel answer={answer} />
      </div>
    </>
  );
}

export default App;
