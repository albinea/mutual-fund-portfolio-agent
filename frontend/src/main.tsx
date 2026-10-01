import { FormEvent, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Message = { role: "user" | "assistant"; content: string };

type ChatResponse = {
  success: boolean;
  answer: string;
  error_code?: string;
};

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

function App() {
  const [userId, setUserId] = useState("USER001");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || !userId.trim() || isSending) return;

    const nextMessages = [...messages, { role: "user" as const, content: message }];
    setMessages(nextMessages);
    setDraft("");
    setError("");
    setIsSending(true);

    try {
      const response = await fetch(`${apiBaseUrl}/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId.trim(),
          message,
          conversation_context: messages.slice(-10),
        }),
      });
      const payload: ChatResponse = await response.json();
      if (!response.ok || !payload.success) {
        throw new Error(payload.answer || payload.error_code || "The agent could not answer right now.");
      }
      setMessages([...nextMessages, { role: "assistant", content: payload.answer }]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to reach the API.");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">FundLens</p>
        <h1>Portfolio assistant</h1>
        <label>
          Portfolio user ID
          <input value={userId} onChange={(event) => setUserId(event.target.value)} />
        </label>
      </header>
      <section className="chat" aria-live="polite">
        {messages.length === 0 && <p className="empty">Ask about overlap, holdings, risk, NAV, or allocation scenarios.</p>}
        {messages.map((item, index) => <article className={item.role} key={`${item.role}-${index}`}>{item.content}</article>)}
        {isSending && <article className="assistant">Checking your portfolio…</article>}
      </section>
      {error && <p className="error" role="alert">{error}</p>}
      <form onSubmit={sendMessage}>
        <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Do my mutual funds overlap?" rows={3} />
        <button disabled={isSending || !draft.trim()}>Send</button>
      </form>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
