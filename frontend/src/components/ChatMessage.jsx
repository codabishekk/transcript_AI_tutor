function ChatMessage({ role, content }) {
  return (
    <div className={`message message--${role}`}>
      {role === "assistant" && (
        <div className="message__avatar message__avatar--ai">✦</div>
      )}
      <div className="message__bubble">{content}</div>
    </div>
  );
}

export default ChatMessage;
