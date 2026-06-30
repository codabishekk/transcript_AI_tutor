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
        message: err.response?.data?.error || "Failed to process video. Please check the URL.",
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
