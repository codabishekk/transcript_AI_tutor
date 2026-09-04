import { useRef, useEffect, useState } from "react";
import axios from "axios";

import ChatMessage from "./components/ChatMessage";
import Composer from "./components/Composer";
import StatusToast from "./components/StatusToast";

const URL_PATTERN = /^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\//i;

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [videoLoaded, setVideoLoaded] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState({ type: "", message: "" });
  const scrollRef = useRef(null);

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

  const isYouTubeUrl = (text) => URL_PATTERN.test(text.trim());

  const addMessage = (role, content) =>
    setMessages((prev) => [...prev, { role, content }]);

  const processVideo = async (url) => {
    if (!url) return;
    setIsLoading(true);
    setStatus({ type: "loading", message: "Extracting transcript and indexing..." });
    addMessage("user", url);
    try {
      const res = await postWithRetry("/process", { url });
      setVideoUrl(url);
      setVideoLoaded(true);
      addMessage(
        "assistant",
        res.data.message || "Video processed. Ask me anything about it!"
      );
      setStatus({ type: "success", message: res.data.message || "Video processed successfully!" });
    } catch (err) {
      console.error(err);
      addMessage("assistant", "⚠ " + getProcessError(err));
      setStatus({ type: "error", message: getProcessError(err) });
    } finally {
      setIsLoading(false);
    }
  };

  const askQuestion = async (question) => {
    setIsLoading(true);
    setStatus({ type: "loading", message: "Consulting the AI tutor..." });
    addMessage("user", question);
    try {
      const res = await postWithRetry("/ask", { question });
      addMessage("assistant", res.data.answer);
      setStatus({ type: "success", message: "Answer generated!" });
    } catch (err) {
      console.error(err);
      const msg = err.response?.data?.error || "Failed to get an answer. Is the video processed?";
      addMessage("assistant", "⚠ " + msg);
      setStatus({ type: "error", message: msg });
    } finally {
      setIsLoading(false);
    }
  };

  const handleSend = () => {
    const text = input.trim();
    if (!text || isLoading) return;
    setInput("");

    if (!videoLoaded) {
      if (isYouTubeUrl(text)) {
        processVideo(text);
      } else {
        setStatus({
          type: "error",
          message: "Paste a YouTube link first so I can load the video's transcript.",
        });
      }
      return;
    }

    if (isYouTubeUrl(text)) {
      processVideo(text);
    } else {
      askQuestion(text);
    }
  };

  const newChat = () => {
    setMessages([]);
    setInput("");
    setVideoUrl("");
    setVideoLoaded(false);
    setStatus({ type: "", message: "" });
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const hasStarted = messages.length > 0 || isLoading;

  return (
    <div className="chat-app">
      <main className="chat-main">
        <header className="chat-topbar">
          <div className="chat-topbar__brand">
            <span className="chat-topbar__logo">✦</span>
            <span>YouTube Tutor</span>
          </div>
          <button className="chat-topbar__new" onClick={newChat}>
            <span>+</span> New chat
          </button>
        </header>
        {!hasStarted ? (
          <div className="welcome">
            <div className="welcome__brand">
              <div className="welcome__logo">✦</div>
              <h1>YouTube Tutor</h1>
              <p>Paste a YouTube link below, then ask anything about the video.</p>
            </div>
            <div className="welcome__composer">
              <Composer
                value={input}
                onChange={setInput}
                onSend={handleSend}
                disabled={isLoading}
                placeholder="Paste a YouTube link to start…"
              />
            </div>
          </div>
        ) : (
          <div className="chat-scroll" ref={scrollRef}>
            <div className="chat-thread">
              {!videoLoaded && videoUrl && (
                <div className="video-banner">⬆ Currently loading: {videoUrl}</div>
              )}
              {messages.map((m, i) => (
                <ChatMessage key={i} role={m.role} content={m.content} />
              ))}
              {isLoading && (
                <div className="message message--assistant">
                  <div className="dots">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {hasStarted && (
          <div className="chat-composer">
            {status.message && <StatusToast type={status.type} message={status.message} />}
            <Composer
              value={input}
              onChange={setInput}
              onSend={handleSend}
              disabled={isLoading}
              placeholder={videoLoaded ? "Ask about the video…" : "Paste a YouTube link…"}
            />
            {videoLoaded && (
              <div className="chat-composer__foot">Source video is loaded and ready to answer.</div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
