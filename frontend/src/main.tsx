import { useMemo, useState } from "react";
import type { ChangeEvent, FormEvent, ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Page = "assistant" | "portfolio" | "explorer" | "overlap" | "calculators" | "market";
type AssistantMode = "chat" | "documents";
type ExplorerTab = "scanner" | "discovery" | "compare" | "commentary";
type CalculatorTab = "sip" | "wealth" | "rolling";
type PortfolioTab = "overview" | "holdings" | "allocation" | "changes";
type MarketTab = "india" | "us" | "europe" | "currencies" | "crypto" | "futures";
type Message = { role: "user" | "assistant"; content: string; sources?: Source[]; trace?: ToolTrace[]; evidence?: RagEvidenceChunk[]; answerMethod?: string; confidence?: number; usage?: RagUsage[] };
type Source = { name?: string; document?: string; page?: number; labels?: string[]; url?: string | null; data_as_of?: string | null };
type ToolTrace = { activity: string; success: boolean };
type ChatResponse = { success: boolean; answer: string; error_code?: string; sources?: Source[]; tool_trace?: ToolTrace[] };
type RagEvidenceChunk = { text: string; document?: string | null; page?: number | null; score?: number | null; fund_name?: string | null; document_type?: string | null; published_date?: string | null; visual_fallback?: boolean };
type RagUsage = { role: "answer" | "vision"; model: string; requests: number; input_tokens: number; output_tokens: number; input_reports: number; output_reports: number; estimated_cost: string };
type RagResponse = { success: boolean; answer: string; error_code?: string; confidence: number; fund_name?: string | null; answer_method: string; sources: Source[]; retrieved_chunks: RagEvidenceChunk[]; usage: RagUsage[] };
type RagJobAccepted = { job_id: string; status: "queued"; poll_url: string };
type RagJobStatus = { job_id: string; status: "queued" | "running" | "completed" | "failed"; poll_url: string; result?: RagResponse | null };
type DemoFund = { id: string; name: string; category: string; risk: string; return1y: number; rolling3y: number; sharpe: number; expense: number; aum: string; aumCr: number; ageYears: number; manager: string; tenure: string };
type IconName = "assistant" | "portfolio" | "explorer" | "overlap" | "calculator" | "market" | "compare" | "search" | "settings" | "bell" | "send" | "attach" | "arrow" | "menu";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const ragPollTimeoutMs = 10 * 60 * 1000;

async function askFundLens(question: string, fundScope: string): Promise<RagResponse> {
  const apiRoot = apiBaseUrl.replace(/\/+$/, "");
  const createResponse = await fetch(`${apiRoot}/rag/jobs/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, fund_scope: fundScope.trim(), top_k: 5 }),
  });
  const created = await createResponse.json() as RagJobAccepted | { detail?: string; error_code?: string };
  if (!createResponse.ok) {
    const message = "detail" in created ? created.detail : undefined;
    throw new Error(message || ("error_code" in created ? created.error_code : undefined) || "Could not queue the document question.");
  }

  const job = created as RagJobAccepted;
  const deadline = Date.now() + ragPollTimeoutMs;
  while (Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    const statusResponse = await fetch(job.poll_url);
    const statusPayload = await statusResponse.json() as RagJobStatus | { detail?: string };
    if (!statusResponse.ok) {
      throw new Error("detail" in statusPayload ? statusPayload.detail || "Could not check document research status." : "Could not check document research status.");
    }
    const current = statusPayload as RagJobStatus;
    if (current.status === "completed" || current.status === "failed") {
      if (current.result) return current.result;
      throw new Error("Document research finished without a result. Please try again.");
    }
  }
  throw new Error("Document research is still running in the background. Please retry shortly; the job may finish after this page stops checking.");
}

const navigation: { id: Page; label: string; icon: IconName }[] = [
  { id: "assistant", label: "AI Assistant", icon: "assistant" },
  { id: "portfolio", label: "Portfolio", icon: "portfolio" },
  { id: "explorer", label: "Fund explorer", icon: "explorer" },
  { id: "overlap", label: "Overlap", icon: "overlap" },
  { id: "calculators", label: "Calculators", icon: "calculator" },
  { id: "market", label: "Market", icon: "market" },
];

// Isolated demo records for developing the scanner UI. They are never presented as live data.
const demoFunds: DemoFund[] = [
  { id: "f1", name: "Axis Bluechip Fund", category: "Large cap", risk: "Moderate", return1y: 14.8, rolling3y: 13.1, sharpe: 0.82, expense: 1.64, aum: "₹35,240 Cr", aumCr: 35240, ageYears: 15, manager: "Equity team", tenure: "—" },
  { id: "f2", name: "Parag Parikh Flexi Cap", category: "Flexi cap", risk: "Moderate", return1y: 16.2, rolling3y: 15.4, sharpe: 0.95, expense: 1.33, aum: "₹86,190 Cr", aumCr: 86190, ageYears: 12, manager: "Rajeev Thakkar", tenure: "—" },
  { id: "f3", name: "HDFC Mid-Cap Opportunities", category: "Mid cap", risk: "High", return1y: 20.7, rolling3y: 18.2, sharpe: 0.78, expense: 1.51, aum: "₹81,400 Cr", aumCr: 81400, ageYears: 18, manager: "Chirag Setalvad", tenure: "—" },
  { id: "f4", name: "UTI Nifty 50 Index", category: "Index", risk: "Moderate", return1y: 13.9, rolling3y: 12.8, sharpe: 0.88, expense: 0.2, aum: "₹20,870 Cr", aumCr: 20870, ageYears: 7, manager: "Index team", tenure: "—" },
  { id: "f5", name: "ICICI Prudential Corporate Bond", category: "Debt", risk: "Low", return1y: 8.3, rolling3y: 7.2, sharpe: 0.64, expense: 0.42, aum: "₹28,090 Cr", aumCr: 28090, ageYears: 9, manager: "Debt team", tenure: "—" },
];

function StarRating({ score }: { score: number }) {
  const stars = Math.max(1, Math.min(5, Math.round(score * 4)));
  return <span className="stars" aria-label={`${stars} out of 5 risk-adjusted-return stars`}>{"★".repeat(stars)}<i>{"★".repeat(5 - stars)}</i></span>;
}

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  let path: ReactNode;
  switch (name) {
    case "assistant": path = <><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><path d="m7.5 7.5 1.8 1.8M14.7 14.7l1.8 1.8M16.5 7.5l-1.8 1.8M9.3 14.7l-1.8 1.8" /><circle cx="12" cy="12" r="2.5" /></>; break;
    case "portfolio": path = <><rect x="3" y="5" width="18" height="15" rx="2" /><path d="M8 5V3h8v2M3 10h18M9 14h6" /></>; break;
    case "explorer": path = <><circle cx="11" cy="11" r="6" /><path d="m16 16 4 4M8.5 11h5M11 8.5v5" /></>; break;
    case "overlap": path = <><rect x="4" y="4" width="11" height="11" rx="1" /><rect x="9" y="9" width="11" height="11" rx="1" /></>; break;
    case "calculator": path = <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M8 7h8M8 11h.01M12 11h.01M16 11h.01M8 15h.01M12 15h.01M16 15h.01" /></>; break;
    case "market": path = <><path d="M4 18 9 12l4 3 7-8" /><path d="M15 7h5v5" /></>; break;
    case "compare": path = <><path d="M7 7h13M16 3l4 4-4 4M17 17H4M8 13l-4 4 4 4" /></>; break;
    case "search": path = <><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 5 5" /></>; break;
    case "settings": path = <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.6 2.6-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.04 1.56V21h-3.68v-.09a1.7 1.7 0 0 0-1.04-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06L5 17.15l.06-.06A1.7 1.7 0 0 0 5.4 15a1.7 1.7 0 0 0-1.56-1.04h-.09v-3.68h.09A1.7 1.7 0 0 0 5.4 9.24a1.7 1.7 0 0 0-.34-1.88L5 7.3l2.6-2.6.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.04-1.56V3.45h3.68v.09a1.7 1.7 0 0 0 1.04 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.6 2.6-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.04h.09v3.68h-.09A1.7 1.7 0 0 0 19.4 15Z" /></>; break;
    case "bell": path = <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>; break;
    case "send": path = <><path d="m21 3-8.5 18-3.2-7.3L2 10.5 21 3Z" /><path d="m9.3 13.7 4.8-4.8" /></>; break;
    case "attach": path = <path d="m19 11-7.7 7.7a5 5 0 0 1-7.1-7.1l8.1-8.1a3.5 3.5 0 0 1 5 5l-8.1 8.1a2 2 0 0 1-2.8-2.8l7.7-7.7" />; break;
    case "menu": path = <><path d="M4 7h16M4 12h16M4 17h16" /></>; break;
    default: path = <path d="M5 12h14m-5-5 5 5-5 5" />;
  }
  return <svg className="ui-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{path}</svg>;
}

function App() {
  const [page, setPage] = useState<Page>("assistant");
  const [explorerTab, setExplorerTab] = useState<ExplorerTab>("scanner");
  const [calculatorTab, setCalculatorTab] = useState<CalculatorTab>("sip");
  const [portfolioTab, setPortfolioTab] = useState<PortfolioTab>("overview");
  const [quickSearch, setQuickSearch] = useState("");
  const [userId, setUserId] = useState("USER001");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [assistantMode, setAssistantMode] = useState<AssistantMode>("chat");
  const [fundScope, setFundScope] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [chatFiles, setChatFiles] = useState<File[]>([]);
  const [holdingFile, setHoldingFile] = useState<File | null>(null);
  const [selectedFundIds, setSelectedFundIds] = useState<string[]>(["f1", "f2"]);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  function openAssistant(prompt = "") {
    setPage("assistant");
    setDraft(prompt);
  }

  function submitQuickSearch(event: FormEvent) {
    event.preventDefault();
    const prompt = quickSearch.trim();
    if (!prompt) return;
    openAssistant(prompt);
    setQuickSearch("");
  }

  function openExplorer(tab: ExplorerTab = "scanner") {
    setPage("explorer");
    setExplorerTab(tab);
  }

  function openPortfolio(tab: PortfolioTab = "overview") {
    setPage("portfolio");
    setPortfolioTab(tab);
  }

  function toggleFund(id: string) {
    setSelectedFundIds((current) => current.includes(id)
      ? current.filter((fundId) => fundId !== id)
      : current.length === 5 ? current : [...current, id]);
  }

  function selectChatFiles(event: ChangeEvent<HTMLInputElement>) {
    setChatFiles(Array.from(event.target.files ?? []).slice(0, 3));
  }

  function selectHoldingFile(event: ChangeEvent<HTMLInputElement>) {
    setHoldingFile(event.target.files?.[0] ?? null);
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || (assistantMode === "chat" && !userId.trim()) || isSending) return;
    const nextMessages = [...messages, { role: "user" as const, content: message }];
    setMessages(nextMessages);
    setDraft("");
    setError("");
    setIsSending(true);
    try {
      // Keep the existing portfolio-chat contract; document questions use the dedicated RAG API.
      const isDocumentQuestion = assistantMode === "documents";
      if (isDocumentQuestion) {
        const ragPayload = await askFundLens(message, fundScope);
        setMessages([...nextMessages, {
          role: "assistant",
          content: ragPayload.answer,
          sources: ragPayload.sources,
          evidence: ragPayload.retrieved_chunks,
          answerMethod: ragPayload.answer_method,
          confidence: ragPayload.confidence,
          usage: ragPayload.usage,
        }]);
      } else {
        const response = await fetch(`${apiBaseUrl}/chat/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: userId.trim(),
            message,
            conversation_context: messages.slice(-10),
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          const errorMessage = payload.answer || payload.detail || payload.error_code || "The assistant could not answer right now.";
          throw new Error(typeof errorMessage === "string" ? errorMessage : JSON.stringify(errorMessage));
        }
        const chatPayload = payload as ChatResponse;
        if (!chatPayload.success) {
          throw new Error(chatPayload.answer || chatPayload.error_code || "The assistant could not answer right now.");
        }
        setMessages([...nextMessages, { role: "assistant", content: chatPayload.answer, sources: chatPayload.sources, trace: chatPayload.tool_trace }]);
        setChatFiles([]);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to reach the API.");
    } finally {
      setIsSending(false);
    }
  }

  function exportAnswer(message: Message) {
    const csv = markdownTableToCsv(message.content);
    if (!csv) return;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "fundlens-analysis.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to main content</a>
    {mobileMenuOpen && <button className="mobile-nav-backdrop" aria-label="Close navigation" onClick={() => setMobileMenuOpen(false)} />}
    <aside className={mobileMenuOpen ? "sidebar mobile-open" : "sidebar"}>
      <div className="brand"><span>F</span><div><strong>FundLens</strong><small>Mutual Fund Intelligence</small></div></div>
      <p className="workspace-label">WORKSPACE</p>
      <nav aria-label="Main navigation">
        {navigation.map((item) => <button key={item.id} className={page === item.id ? "nav-item active" : "nav-item"} onClick={() => setPage(item.id)}><b><Icon name={item.icon} /></b>{item.label}</button>)}
        <button className={page === "explorer" && explorerTab === "compare" ? "nav-item active" : "nav-item"} onClick={() => openExplorer("compare")}><b><Icon name="compare" /></b>Compare funds</button>
      </nav>
      <div className="sidebar-section"><div className="sidebar-section-heading"><span>PORTFOLIO</span><button aria-label="Add portfolio">+</button></div><button className="sidebar-link" onClick={() => openPortfolio("holdings")}>Holdings</button><button className="sidebar-link" onClick={() => openPortfolio("allocation")}>Allocation & exposure</button><button className="sidebar-link" onClick={() => openPortfolio("changes")}>Changes</button><button className="sidebar-link" onClick={() => openPortfolio("overview")}>Import holdings <span>→</span></button></div>
      <div className="sidebar-section"><div className="sidebar-section-heading"><span>RESEARCH</span></div><button className="sidebar-link" onClick={() => openExplorer("scanner")}>Fund explorer</button><button className="sidebar-link" onClick={() => openExplorer("discovery")}>Fund list</button><button className="sidebar-link" onClick={() => openExplorer("compare")}>Fund compare</button><button className="sidebar-link" onClick={() => openExplorer("commentary")}>Manager commentary</button></div>
      <div className="sidebar-section"><div className="sidebar-section-heading"><span>MARKET</span></div><button className="sidebar-link" onClick={() => setPage("market")}>Market overview</button><button className="sidebar-link" onClick={() => setPage("market")}>Watchlist</button></div>
      <div className="sidebar-footer"><span className="status-dot" /> Research workspace <small>Evidence-led analysis</small></div>
    </aside>

    <section className="workspace">
      <header className="topbar">
        <div className="topbar-brand"><strong>FundLens</strong><small>Mutual Fund Intelligence</small></div>
        <form className="universal-search" onSubmit={submitQuickSearch}><Icon name="search" size={17} /><input value={quickSearch} onChange={(event) => setQuickSearch(event.target.value)} placeholder="Search funds, companies, or ask a question" aria-label="Ask anything or search" /><button type="submit">Search</button></form>
        <button className="mobile-menu-toggle" aria-label="Open navigation" onClick={() => setMobileMenuOpen(true)}><Icon name="menu" /></button>
        <div className="topbar-actions"><label className="user-select">Portfolio <input value={userId} onChange={(event) => setUserId(event.target.value)} aria-label="Portfolio user ID" /></label><button className="icon-button" aria-label="Settings"><Icon name="settings" /></button><button className="icon-button" aria-label="Notifications"><Icon name="bell" /></button><button className="avatar" aria-label="Account">LC</button></div>
      </header>
      <main id="main-content" className={page === "assistant" ? "content" : "content app-content"} tabIndex={-1}>
        <div className="page-main">
          {page === "assistant" && <AssistantView messages={messages} draft={draft} setDraft={setDraft} files={chatFiles} error={error} isSending={isSending} assistantMode={assistantMode} setAssistantMode={setAssistantMode} fundScope={fundScope} setFundScope={setFundScope} onFiles={selectChatFiles} onSend={sendMessage} onExport={exportAnswer} onShortcut={openAssistant} onImport={() => openPortfolio("overview")} />}
          {page === "portfolio" && <PortfolioView tab={portfolioTab} onTab={setPortfolioTab} holdingFile={holdingFile} onFile={selectHoldingFile} onAsk={openAssistant} />}
          {page === "explorer" && <ExplorerView tab={explorerTab} onTab={setExplorerTab} selectedIds={selectedFundIds} onToggle={toggleFund} onCompare={() => setExplorerTab("compare")} />}
          {page === "overlap" && <OverlapView hasHoldingFile={Boolean(holdingFile)} onImport={() => setPage("portfolio")} onAsk={openAssistant} />}
          {page === "calculators" && <CalculatorsView tab={calculatorTab} onTab={setCalculatorTab} onExplore={() => openExplorer("scanner")} />}
          {page === "market" && <MarketView />}
        </div>
      </main>
    </section>
  </div>;
}

function markdownTableToCsv(content: string) {
  const rows = content.split("\n").map((line) => line.trim()).filter((line) => /^\|?.+\|.+\|?$/.test(line) && !/^\|?\s*:?-{3,}/.test(line));
  if (rows.length < 2) return null;
  return rows.map((row) => row.replace(/^\||\|$/g, "").split("|").map((cell) => `"${cell.trim().replaceAll('"', '""')}"`).join(",")).join("\n");
}

function hasStructuredTable(content: string) {
  return Boolean(markdownTableToCsv(content));
}

function AssistantView({ messages, draft, setDraft, files, error, isSending, assistantMode, setAssistantMode, fundScope, setFundScope, onFiles, onSend, onExport, onShortcut, onImport }: { messages: Message[]; draft: string; setDraft: (value: string) => void; files: File[]; error: string; isSending: boolean; assistantMode: AssistantMode; setAssistantMode: (mode: AssistantMode) => void; fundScope: string; setFundScope: (value: string) => void; onFiles: (event: ChangeEvent<HTMLInputElement>) => void; onSend: (event: FormEvent) => void; onExport: (message: Message) => void; onShortcut: (prompt: string) => void; onImport: () => void }) {
  const prompts = [
    { label: "Analyze", prompt: "Analyze my portfolio" },
    { label: "Compare", prompt: "Compare my funds" },
    { label: "Explore", prompt: "Explain this fund" },
    { label: "Exposure", prompt: "What sectors am I exposed to?" },
    { label: "Risk", prompt: "Explain the risk of my portfolio" },
    { label: "Changes", prompt: "What changed in my portfolio?" },
  ];
  return <div className="assistant-page">
    <section className="chat-stage" aria-live="polite">
      {messages.length === 0 ? <div className="assistant-welcome">
        <h2>Search and understand your portfolio</h2>
        <p>Ask a question, compare funds, or explore the data behind your investments.</p>
        <ChatComposer draft={draft} setDraft={setDraft} files={files} isSending={isSending} assistantMode={assistantMode} setAssistantMode={setAssistantMode} fundScope={fundScope} setFundScope={setFundScope} onFiles={onFiles} onSend={onSend} home />
        <div className="prompt-grid" aria-label="Suggested research prompts">{prompts.map((item) => <button key={item.label} onClick={() => onShortcut(item.prompt)}><Icon name="arrow" size={15} />{item.label}</button>)}</div>
        <HomeSnapshots onImport={onImport} />
      </div> : <div className="conversation">{messages.map((item, index) => <ChatMessage key={`${item.role}-${index}`} message={item} onExport={onExport} />)}</div>}
      {isSending && <div className="message assistant loading"><div className="message-label">FundLens</div><p><span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" /> {assistantMode === "documents" ? "Searching indexed fund documents and preparing evidence" : "Reviewing your request"}</p></div>}
    </section>
    {messages.length > 0 && <ChatComposer draft={draft} setDraft={setDraft} files={files} isSending={isSending} assistantMode={assistantMode} setAssistantMode={setAssistantMode} fundScope={fundScope} setFundScope={setFundScope} onFiles={onFiles} onSend={onSend} />}
    {error && <p className="error" role="alert" aria-live="assertive">{error}</p>}
  </div>;
}

function ChatComposer({ draft, setDraft, files, isSending, assistantMode, setAssistantMode, fundScope, setFundScope, onFiles, onSend, home = false }: { draft: string; setDraft: (value: string) => void; files: File[]; isSending: boolean; assistantMode: AssistantMode; setAssistantMode: (mode: AssistantMode) => void; fundScope: string; setFundScope: (value: string) => void; onFiles: (event: ChangeEvent<HTMLInputElement>) => void; onSend: (event: FormEvent) => void; home?: boolean }) {
  return <form className={home ? "composer home-composer" : "composer"} onSubmit={onSend}>
    <div className="composer-mode-row" role="group" aria-label="Assistant mode">
      <button type="button" className={assistantMode === "chat" ? "mode-button active" : "mode-button"} aria-pressed={assistantMode === "chat"} onClick={() => setAssistantMode("chat")}>Portfolio chat</button>
      <button type="button" className={assistantMode === "documents" ? "mode-button active" : "mode-button"} aria-pressed={assistantMode === "documents"} onClick={() => setAssistantMode("documents")}>Fund document research</button>
    </div>
    {assistantMode === "documents" && <label className="fund-scope-field">Fund name <input value={fundScope} onChange={(event) => setFundScope(event.target.value)} placeholder="Optional, e.g. HDFC Medium to Long Term Fund" /></label>}
    {assistantMode === "chat" && files.length > 0 && <div className="attachment-list">{files.map((file) => <span key={`${file.name}-${file.size}`}>{file.name}</span>)}<small>Selected files will be supported when the document-ingestion endpoint is connected.</small></div>}
    <textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={assistantMode === "documents" ? "Ask a question about an indexed fund document" : "Ask anything about your mutual funds"} rows={home ? 2 : 3} />
    <div className="composer-footer">{assistantMode === "chat" ? <label className="attach-control"><input type="file" accept=".pdf,.xlsx,.xls,.csv" multiple onChange={onFiles} /><Icon name="attach" size={16} />Attach</label> : <span className="indexed-docs-note">Searches indexed fund documents</span>}<span>Evidence-led research, not investment advice.</span><button className="send-button" disabled={isSending || !draft.trim()} aria-label="Send message"><Icon name="send" size={16} /></button></div>
  </form>;
}

function ChatMessage({ message, onExport }: { message: Message; onExport: (message: Message) => void }) {
  const exportable = message.role === "assistant" && hasStructuredTable(message.content);
  return <article className={`message ${message.role}`}><div className="message-label">{message.role === "user" ? "You" : "FundLens"}</div><p>{message.content}</p>
    {message.role === "assistant" && <><div className="message-meta">{message.trace?.filter((step) => step.success).map((step) => <span key={step.activity}>✓ {step.activity}</span>)}</div>
      {message.answerMethod && <div className="message-meta"><span>Answer method: {message.answerMethod.replaceAll("_", " ")}</span>{typeof message.confidence === "number" && <span>Confidence: {Math.round(message.confidence * 100)}%</span>}</div>}
      {message.sources?.length ? <div className="sources">{message.sources.map((source, index) => <span key={`${source.document ?? source.name}-${source.page ?? index}`}>Source: {source.document ?? source.name ?? "Source"}{source.page ? ` · page ${source.page}` : ""}{source.labels?.length ? ` · ${source.labels.join(", ")}` : ""}{source.data_as_of ? ` · As of ${source.data_as_of}` : ""}</span>)}</div> : null}
      {message.evidence && <section className="rag-evidence" aria-label="Retrieved evidence"><h4>Retrieved chunks ({message.evidence.length})</h4>{message.evidence.length ? message.evidence.map((chunk, index) => <article className="evidence-chunk" key={`${chunk.document ?? "doc"}-${chunk.page ?? "page"}-${index}`}><div className="evidence-chunk-meta">Chunk {index + 1}{chunk.fund_name ? ` · ${chunk.fund_name}` : ""}{chunk.document ? ` · ${chunk.document}` : ""}{chunk.page ? ` · page ${chunk.page}` : ""}{typeof chunk.score === "number" ? ` · score ${chunk.score.toFixed(3)}` : ""}{chunk.visual_fallback ? " · visual fallback" : ""}</div><p>{chunk.text || "(No text in this retrieved chunk)"}</p></article>) : <p className="no-evidence">No chunks were retrieved for this answer.</p>}</section>}
      {message.usage && <section className="rag-usage" aria-label="Model usage"><h4>Model usage and estimated cost</h4>{message.usage.length ? <div className="rag-usage-list">{message.usage.map((item, index) => <div className="rag-usage-row" key={`${item.role}-${item.model}-${index}`}><strong>{item.role === "vision" ? "Vision fallback" : "Answer model"}: {item.model}</strong><span>{item.requests} API request{item.requests === 1 ? "" : "s"}</span><span>{item.input_tokens} input · {item.output_tokens} output tokens</span><span>Estimated cost: {item.estimated_cost}</span></div>)}</div> : <p className="no-evidence">No model usage was reported for this answer.</p>}</section>}
      {exportable && <button className="text-action" onClick={() => onExport(message)}>Export to Excel</button>}
    </>}
  </article>;
}

function HomeSnapshots({ onImport }: { onImport: () => void }) {
  return <section className="home-snapshots" aria-label="Portfolio and market snapshots"><article><p className="eyebrow">YOUR PORTFOLIO</p><h3>No portfolio imported yet</h3><p>Import holdings to view value, fund count, company exposure, and sector exposure.</p><button className="text-action" type="button" onClick={onImport}>Import holdings</button></article><article><p className="eyebrow">MARKET</p><h3>Market data is currently unavailable</h3><p>India indices and a concise market summary will appear when a supported provider is connected.</p><div className="source-meta"><span>Source: —</span><span>As of: —</span></div></article></section>;
}

function PortfolioView({ tab, onTab, holdingFile, onFile, onAsk }: { tab: PortfolioTab; onTab: (tab: PortfolioTab) => void; holdingFile: File | null; onFile: (event: ChangeEvent<HTMLInputElement>) => void; onAsk: (prompt: string) => void }) {
  return <div className="view-stack">
    <ViewHeading eyebrow="YOUR ACTUAL HOLDINGS" title="Understand the portfolio you already own" description="Import a statement to prepare your real holdings for analysis." />
    <div className="segmented" role="tablist" aria-label="Portfolio sections"><TabButton active={tab === "overview"} onClick={() => onTab("overview")}>Overview</TabButton><TabButton active={tab === "holdings"} onClick={() => onTab("holdings")}>Holdings</TabButton><TabButton active={tab === "allocation"} onClick={() => onTab("allocation")}>Allocation & exposure</TabButton><TabButton active={tab === "changes"} onClick={() => onTab("changes")}>What changed?</TabButton></div>
    {tab === "overview" && <><PortfolioSummary /><section className="import-state">
      <div><span className="import-symbol">↓</span><h3>Import holdings</h3><p>Upload an Excel, CSV, or PDF statement to analyze your real portfolio—not manually entered example values.</p><small>Supported formats: .xlsx, .xls, .csv, .pdf</small></div>
      <label className="primary-button import-button"><input type="file" accept=".pdf,.xlsx,.xls,.csv" onChange={onFile} />Choose a statement</label>
    </section>{holdingFile ? <UploadSelectedState file={holdingFile} onAsk={onAsk} /> : <section className="empty-state compact"><p className="eyebrow">NO PORTFOLIO IMPORTED</p><h2>Your analysis will appear here</h2><p>After an import is processed, this view will organize allocation, sector and company exposure, concentration, risk metrics, and fund overlap in one place.</p></section>}</>}
    {tab === "holdings" && <PortfolioTableEmpty onImport={() => onTab("overview")} />}
    {tab === "allocation" && <PortfolioAllocationEmpty onImport={() => onTab("overview")} />}
    {tab === "changes" && <PortfolioChanges onAsk={onAsk} />}
  </div>;
}

function PortfolioSummary() {
  return <section className="portfolio-summary" aria-label="Portfolio summary awaiting data"><div><p className="eyebrow">MY PORTFOLIO</p><h3>Portfolio summary</h3><small>Values will appear after a portfolio is available.</small></div><div className="summary-metric"><span>Total invested</span><strong>—</strong></div><div className="summary-metric"><span>Current value</span><strong>—</strong></div><div className="summary-metric"><span>Change</span><strong>—</strong></div></section>;
}

function UploadSelectedState({ file, onAsk }: { file: File; onAsk: (prompt: string) => void }) {
  return <section className="upload-ready"><div className="upload-status"><span>✓</span><div><strong>{file.name}</strong><p>File selected. It has not been uploaded or analysed yet.</p></div></div><div className="upload-detection"><span>Funds detected <b>Awaiting import</b></span><span>Holdings detected <b>Awaiting import</b></span></div><div className="button-row left"><button className="primary-button" disabled>Analyze portfolio</button><button className="outline-button" onClick={() => onAsk("How can I analyse my imported mutual-fund holdings?")}>Ask the assistant</button></div><small className="integration-note">A document-upload endpoint is needed before this selected file can be sent and analysed.</small></section>;
}

function PortfolioTableEmpty({ onImport }: { onImport: () => void }) {
  const [query, setQuery] = useState("");
  return <><div className="table-tools"><label>Search holdings<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by fund" /></label><select aria-label="Sort holdings" defaultValue="allocation"><option value="allocation">Sort: allocation</option><option value="value">Sort: current value</option><option value="name">Sort: fund name</option></select><select aria-label="Filter holdings" defaultValue="all"><option value="all">All categories</option><option value="equity">Equity</option><option value="debt">Debt</option><option value="hybrid">Hybrid</option></select></div><section className="table-shell"><table className="holdings-table"><thead><tr><th><input type="checkbox" aria-label="Select all funds" disabled /></th><th>Fund</th><th>Units</th><th>Invested</th><th>Current value</th><th>Allocation</th></tr></thead><tbody><tr><td colSpan={6}><div className="table-empty"><strong>No holdings to display</strong><span>Import a statement to populate your actual fund positions, values, and allocation.</span><button className="outline-button" onClick={onImport}>Import holdings</button></div></td></tr></tbody></table></section></>;
}

function PortfolioAllocationEmpty({ onImport }: { onImport: () => void }) {
  return <><section className="allocation-empty"><div><p className="eyebrow">PORTFOLIO ANALYSIS</p><h3>Fund, category and sector exposure</h3><p>Allocation charts should render only the values returned by a processed portfolio. No estimated exposure is shown before that.</p><button className="outline-button" onClick={onImport}>Import holdings</button></div><div className="allocation-list" aria-label="Allocation categories awaiting data"><span>Fund allocation<i /></span><span>Category allocation<i /></span><span>Sector exposure<i /></span><span>Top company exposure<i /></span><span>Portfolio concentration<i /></span></div></section><SectorExposure onImport={onImport} /></>;
}

function SectorExposure({ onImport }: { onImport: () => void }) {
  return <section className="sector-exposure"><div className="sector-heading"><div><p className="eyebrow">SECTOR EXPOSURE</p><h3>See the sectors behind your funds</h3><p>Banking, IT, healthcare, energy and other sector weights will appear here after a portfolio analysis is returned.</p></div><button className="outline-button" onClick={onImport}>Import holdings</button></div><div className="sector-visual"><div className="sector-donut" aria-label="Sector allocation awaiting data"><span>Awaiting<br />analysis</span></div><div className="sector-bars" aria-label="Sector bars awaiting data"><div><span>Banking</span><i /><b>—</b></div><div><span>IT</span><i /><b>—</b></div><div><span>Healthcare</span><i /><b>—</b></div><div><span>Energy</span><i /><b>—</b></div><div><span>Others</span><i /><b>—</b></div></div></div><div className="table-shell"><table className="sector-table"><thead><tr><th>Sector</th><th>Exposure</th><th>Underlying funds</th><th>Underlying companies</th></tr></thead><tbody><tr><td colSpan={4}><div className="table-empty"><strong>No sector exposure data yet</strong><span>Selecting a sector will reveal its underlying funds and companies when those records are available.</span></div></td></tr></tbody></table></div></section>;
}

function PortfolioChanges({ onAsk }: { onAsk: (prompt: string) => void }) {
  return <><section className="changes-header"><div><p className="eyebrow">PORTFOLIO CHANGES</p><h3>Compare two portfolio snapshots</h3><p>New, increased, decreased and unchanged positions are calculated from dated portfolio data—not inferred from market movement.</p></div><div className="snapshot-selectors"><label>Newer snapshot<select disabled><option>Awaiting data</option></select></label><label>Older snapshot<select disabled><option>Awaiting data</option></select></label></div></section><section className="change-flow" aria-label="Evidence research flow"><span>Portfolio snapshot</span><i>→</i><span>Historical difference</span><i>→</i><span>Fund factsheet</span><i>→</i><span>Manager commentary</span><i>→</i><span>AI explanation</span><i>→</i><span>Sources</span></section><section className="table-shell"><table className="changes-table"><thead><tr><th>Change</th><th>Company or holding</th><th>Relevant fund</th><th>Source</th><th>Date</th><th /></tr></thead><tbody><tr><td colSpan={6}><div className="table-empty"><strong>No historical comparison yet</strong><span>Import or connect two dated portfolio snapshots to see changes with their supporting evidence.</span></div></td></tr></tbody></table></section><section className="evidence-empty"><strong>No documented explanation was found for this change.</strong><span>When evidence exists, FundLens will show the source, date, relevant fund and supporting document before offering an AI explanation.</span><button className="outline-button" onClick={() => onAsk("What changed in my portfolio, and what evidence supports it?")}>Ask why it changed</button></section></>;
}

function ExplorerView({ tab, onTab, selectedIds, onToggle, onCompare }: { tab: ExplorerTab; onTab: (tab: ExplorerTab) => void; selectedIds: string[]; onToggle: (id: string) => void; onCompare: () => void }) {
  return <div className="view-stack"><ViewHeading eyebrow="FUND RESEARCH" title="Explore funds with context" description="Search, screen, and compare. Demo records are isolated until a fund-data source is connected." />
    <div className="segmented" role="tablist" aria-label="Fund explorer sections"><TabButton active={tab === "scanner"} onClick={() => onTab("scanner")}>Scanner</TabButton><TabButton active={tab === "discovery"} onClick={() => onTab("discovery")}>Fund list</TabButton><TabButton active={tab === "compare"} onClick={() => onTab("compare")}>Compare {selectedIds.length > 0 ? `(${selectedIds.length})` : ""}</TabButton><TabButton active={tab === "commentary"} onClick={() => onTab("commentary")}>Manager commentary</TabButton></div>
    {tab === "scanner" && <Scanner selectedIds={selectedIds} onToggle={onToggle} onCompare={onCompare} />}
    {tab === "discovery" && <FundDiscovery onExplore={() => onTab("scanner")} />}
    {tab === "compare" && <Compare funds={demoFunds.filter((fund) => selectedIds.includes(fund.id))} onToggle={onToggle} onScan={() => onTab("scanner")} />}
    {tab === "commentary" && <Commentary />}
  </div>;
}

function FundDiscovery({ onExplore }: { onExplore: () => void }) {
  const [category, setCategory] = useState("All");
  const [lens, setLens] = useState("High risk-adjusted return");
  const categories = ["All", "Equity", "Debt", "Hybrid", "Index", "Large cap", "Mid cap", "Small cap", "Other"];
  const lenses = ["High risk-adjusted return", "Consistent historical performance", "Lower expense ratio", "Large fund size", "Category comparison"];
  const categoryFunds = demoFunds.filter((fund) => category === "All" || (category === "Equity" && !["Debt", "Index"].includes(fund.category)) || fund.category === category);
  const funds = [...categoryFunds].sort((left, right) => lens === "Lower expense ratio" ? left.expense - right.expense : lens === "Large fund size" ? right.aumCr - left.aumCr : lens === "Consistent historical performance" ? right.rolling3y - left.rolling3y : right.sharpe - left.sharpe);
  return <><div className="demo-notice"><strong>Demo data</strong><span>Discovery labels are research filters only. They are not investment recommendations and will use the connected fund-data source when available.</span></div><section className="discovery-toolbar"><div><p className="eyebrow">FUND LIST</p><h3>Browse by category and research lens</h3></div><button className="outline-button" onClick={onExplore}>Open full scanner</button></section><div className="discovery-filters" aria-label="Fund categories">{categories.map((item) => <button key={item} className={category === item ? "active" : ""} onClick={() => setCategory(item)}>{item}</button>)}</div><div className="research-lenses" aria-label="Fund research lenses">{lenses.map((item) => <button key={item} className={lens === item ? "active" : ""} onClick={() => setLens(item)}>{item}</button>)}</div><div className="table-shell"><table className="discovery-table"><thead><tr><th>Fund</th><th>Category</th><th>Risk-adjusted return</th><th>3Y rolling return</th><th>Expense ratio</th><th>Fund size</th></tr></thead><tbody>{funds.length ? funds.map((fund) => <tr key={fund.id}><td><strong>{fund.name}</strong><small>{fund.manager}</small></td><td><span className="fund-category">{fund.category}</span></td><td><span className="rating-cell"><StarRating score={fund.sharpe} /><small>Sharpe {fund.sharpe}</small></span></td><td className="positive-value">{fund.rolling3y}%</td><td>{fund.expense}%</td><td>{fund.aum}</td></tr>) : <tr><td colSpan={6}><div className="table-empty"><strong>No demo funds in this category</strong><span>This category will fill when the fund-data source supports it.</span></div></td></tr>}</tbody></table></div><details className="methodology"><summary>How are funds listed?</summary><p>The selected research lens changes the sort order of the available fund records. It does not determine whether a fund is suitable for any investor.</p></details></>;
}

function Scanner({ selectedIds, onToggle, onCompare }: { selectedIds: string[]; onToggle: (id: string) => void; onCompare: () => void }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [risk, setRisk] = useState("All");
  const [returnFloor, setReturnFloor] = useState("All");
  const [expenseCap, setExpenseCap] = useState("All");
  const [sizeFloor, setSizeFloor] = useState("All");
  const [ageFloor, setAgeFloor] = useState("All");
  const visibleFunds = useMemo(() => demoFunds.filter((fund) => {
    const matchesName = fund.name.toLowerCase().includes(query.toLowerCase());
    const matchesCategory = category === "All" || fund.category === category;
    const matchesRisk = risk === "All" || fund.risk === risk;
    const matchesReturn = returnFloor === "All" || fund.rolling3y >= Number(returnFloor);
    const matchesExpense = expenseCap === "All" || fund.expense <= Number(expenseCap);
    const matchesSize = sizeFloor === "All" || fund.aumCr >= Number(sizeFloor);
    const matchesAge = ageFloor === "All" || fund.ageYears >= Number(ageFloor);
    return matchesName && matchesCategory && matchesRisk && matchesReturn && matchesExpense && matchesSize && matchesAge;
  }), [query, category, risk, returnFloor, expenseCap, sizeFloor, ageFloor]);
  return <><div className="demo-notice"><strong>Demo data</strong><span>Screen controls and comparison interactions are live; the fund figures are not connected to a live data provider.</span></div><div className="filter-bar">
    <label className="search-field">Search funds<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by fund name" /></label>
    <label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}><option>All</option><option>Large cap</option><option>Flexi cap</option><option>Mid cap</option><option>Index</option><option>Debt</option></select></label>
    <label>Risk<select value={risk} onChange={(event) => setRisk(event.target.value)}><option>All</option><option>Low</option><option>Moderate</option><option>High</option></select></label>
    <label>3Y return<select value={returnFloor} onChange={(event) => setReturnFloor(event.target.value)}><option value="All">All</option><option value="10">10% and above</option><option value="15">15% and above</option></select></label>
    <label>Expense ratio<select value={expenseCap} onChange={(event) => setExpenseCap(event.target.value)}><option value="All">All</option><option value="0.5">Up to 0.5%</option><option value="1.5">Up to 1.5%</option><option value="2">Up to 2%</option></select></label>
    <label>Fund size<select value={sizeFloor} onChange={(event) => setSizeFloor(event.target.value)}><option value="All">All</option><option value="25000">₹25,000 Cr and above</option><option value="50000">₹50,000 Cr and above</option></select></label>
    <label>Fund age<select value={ageFloor} onChange={(event) => setAgeFloor(event.target.value)}><option value="All">All</option><option value="10">10+ years</option><option value="15">15+ years</option></select></label>
    <button className="primary-button" onClick={onCompare}>Compare {selectedIds.length} funds</button>
  </div><section className="rating-definition"><div><p className="eyebrow">RISK-ADJUSTED RETURN</p><h3>Return achieved relative to the risk taken</h3><p>Stars are derived from the displayed Sharpe ratio, not a recommendation. A higher return by itself does not mean a better risk-adjusted result.</p></div><div className="rating-legend"><span><StarRating score={0.25} /> Lower ratio</span><span><StarRating score={0.75} /> Higher ratio</span></div></section><div className="scanner-result-summary"><span>{visibleFunds.length} demo funds match this screen</span><span>Choose 2–5 funds to compare</span></div><div className="table-shell"><table className="scanner-table"><thead><tr><th>Fund</th><th>Category</th><th>Risk</th><th>3Y return</th><th>Risk-adjusted return</th><th>Expense ratio</th><th>Fund size</th><th>Age</th><th>Compare</th></tr></thead><tbody>{visibleFunds.map((fund) => <tr key={fund.id}><td><strong>{fund.name}</strong><small>{fund.manager}</small></td><td><span className="fund-category">{fund.category}</span></td><td>{fund.risk}</td><td className="positive-value">{fund.rolling3y}%</td><td><span className="rating-cell"><StarRating score={fund.sharpe} /><small>Sharpe {fund.sharpe}</small></span></td><td>{fund.expense}%</td><td>{fund.aum}</td><td>{fund.ageYears} years</td><td><label className="compare-check"><input type="checkbox" checked={selectedIds.includes(fund.id)} onChange={() => onToggle(fund.id)} disabled={!selectedIds.includes(fund.id) && selectedIds.length === 5} /><span className="sr-only">Compare {fund.name}</span></label></td></tr>)}</tbody></table></div><details className="methodology"><summary>How is this calculated?</summary><p>The displayed ratio is annualized return divided by annualized volatility, using the fund’s return series where available. FundLens maps the resulting ratio into one to five stars for quick comparison: lower ratios receive fewer stars and higher ratios receive more. The stars are not a buy, sell, or suitability recommendation.</p></details></>;
}

function Compare({ funds, onToggle, onScan }: { funds: DemoFund[]; onToggle: (id: string) => void; onScan: () => void }) {
  if (funds.length < 2) return <section className="empty-state compact"><p className="eyebrow">COMPARE FUNDS</p><h2>Select 2–5 funds to compare</h2><p>Choose funds from the scanner to understand their differences—not to select a universal winner.</p><button className="primary-button" onClick={onScan}>Open fund scanner</button></section>;
  const rows: { label: string; value: (fund: DemoFund) => string | ReactNode }[] = [
    { label: "Category", value: (fund) => fund.category }, { label: "Risk level", value: (fund) => fund.risk }, { label: "1Y return", value: (fund) => `${fund.return1y}%` }, { label: "3Y rolling return", value: (fund) => `${fund.rolling3y}%` }, { label: "Risk-adjusted return", value: (fund) => <span className="rating-cell"><StarRating score={fund.sharpe} /><small>Sharpe {fund.sharpe}</small></span> }, { label: "Expense ratio", value: (fund) => `${fund.expense}%` }, { label: "Fund size", value: (fund) => fund.aum }, { label: "Fund age", value: (fund) => `${fund.ageYears} years` }, { label: "Manager", value: (fund) => fund.manager }, { label: "Manager tenure", value: (fund) => fund.tenure }, { label: "Benchmark performance", value: () => "Not connected" }, { label: "Major holdings / sector exposure", value: () => "Not connected" },
  ];
  return <><div className="demo-notice"><strong>Demo data</strong><span>Comparison layout is ready. Holdings, sector exposure, benchmark and tenure fields will populate when the fund-data source is available.</span></div><div className="comparison-wrap"><table className="comparison-table"><thead><tr><th>Fund metric</th>{funds.map((fund) => <th key={fund.id}><span className="fund-category">{fund.category}</span><strong>{fund.name}</strong><button className="remove-fund" onClick={() => onToggle(fund.id)}>Remove</button></th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.label}><th>{row.label}</th>{funds.map((fund) => <td key={fund.id}>{row.value(fund)}</td>)}</tr>)}</tbody></table></div></>;
}

function Commentary() {
  return <section className="commentary-research"><div><p className="eyebrow">MANAGER COMMENTARY</p><h2>Research notes with source context</h2><p>Commentary is shown only when it can be connected to the relevant fund, publication date and original supporting document.</p></div><details open><summary>Commentary awaiting source data</summary><div className="commentary-grid"><span>Fund <b>Awaiting data</b></span><span>Date <b>Awaiting data</b></span><span>Source <b>Awaiting data</b></span><span>Supporting document <b>Awaiting data</b></span></div><p>No manager commentary is available from the connected data source yet. When it is, this section will present concise key observations and retain the original source for review.</p></details></section>;
}

function OverlapView({ hasHoldingFile, onImport, onAsk }: { hasHoldingFile: boolean; onImport: () => void; onAsk: (prompt: string) => void }) {
  return <div className="view-stack"><ViewHeading eyebrow="PORTFOLIO DIVERSIFICATION" title="Understand where your funds meet" description="Company-level overlap explains whether multiple funds truly diversify your portfolio." />
    <section className="explanation-panel"><span className="risk-ring">?</span><div><h3>Overlap is more than one percentage</h3><p>When the same companies appear across funds, owning both may provide less diversification than it first appears. The analysis should show the companies, funds, and concentrated exposure behind the number.</p></div></section>
    <section className="overlap-data-shell" aria-label="Portfolio overlap results awaiting data"><div className="overlap-data-heading"><div><p className="eyebrow">COMPANY-LEVEL BREAKDOWN</p><h3>Top overlapping companies</h3><p>Company, fund and exposure values will be shown only after your portfolio analysis returns them.</p></div><span>Awaiting data</span></div><div className="table-shell"><table className="overlap-table"><thead><tr><th>Company</th><th>Funds holding</th><th>Combined exposure</th><th>Portfolio contribution</th></tr></thead><tbody><tr><td colSpan={4}><div className="table-empty"><strong>No overlap results yet</strong><span>Import and process your holdings to see the companies repeated across your funds and their combined exposure.</span></div></td></tr></tbody></table></div></section>
    <section className="empty-state compact"><p className="eyebrow">{hasHoldingFile ? "IMPORT WAITING FOR PROCESSING" : "NO HOLDINGS AVAILABLE"}</p><h2>{hasHoldingFile ? "Your overlap analysis is ready to be generated" : "Import holdings to see your real overlap"}</h2><p>{hasHoldingFile ? "The selected statement has not been sent because the current backend has no portfolio-import endpoint." : "Once your holdings are processed, this page will show company-level overlap, common holdings, and concentration explanations."}</p><div className="button-row"><button className="primary-button" onClick={onImport}>Import holdings</button><button className="outline-button" onClick={() => onAsk("Do my mutual funds overlap?")}>Ask the assistant</button></div></section>
  </div>;
}

function CalculatorsView({ tab, onTab, onExplore }: { tab: CalculatorTab; onTab: (tab: CalculatorTab) => void; onExplore: () => void }) {
  return <div className="view-stack"><ViewHeading eyebrow="CALCULATORS" title="Plan with transparent assumptions" description="Calculations are estimates. They help you explore possibilities, not predict or guarantee outcomes." />
    <div className="segmented" role="tablist" aria-label="Calculators"><TabButton active={tab === "sip"} onClick={() => onTab("sip")}>SIP calculator</TabButton><TabButton active={tab === "wealth"} onClick={() => onTab("wealth")}>Expected wealth</TabButton><TabButton active={tab === "rolling"} onClick={() => onTab("rolling")}>Rolling returns</TabButton></div>
    {tab === "sip" && <SipCalculator />}{tab === "wealth" && <WealthCalculator />}{tab === "rolling" && <RollingReturns onExplore={onExplore} />}
  </div>;
}

function SipCalculator() {
  const [monthlySip, setMonthlySip] = useState(15000); const [years, setYears] = useState(10); const [annualReturn, setAnnualReturn] = useState(12);
  return <CalculatorLayout inputs={<><NumberInput label="Monthly investment" value={monthlySip} setValue={setMonthlySip} suffix="₹ per month" step={500} /><NumberInput label="Expected annual return" value={annualReturn} setValue={setAnnualReturn} suffix="% per year" step={0.5} /><NumberInput label="Investment duration" value={years} setValue={setYears} suffix="years" min={1} /></>} />;
}

function WealthCalculator() {
  const [initial, setInitial] = useState(100000); const [additional, setAdditional] = useState(10000); const [frequency, setFrequency] = useState("monthly"); const [years, setYears] = useState(10); const [annualReturn, setAnnualReturn] = useState(12);
  return <CalculatorLayout inputs={<><NumberInput label="Initial investment" value={initial} setValue={setInitial} suffix="₹ once" step={1000} /><NumberInput label="Additional contribution" value={additional} setValue={setAdditional} suffix={`₹ ${frequency}`} step={500} /><ChoiceInput label="Contribution frequency" value={frequency} setValue={setFrequency} options={[{ value: "monthly", label: "Monthly" }, { value: "yearly", label: "Yearly" }]} /><NumberInput label="Expected annual return" value={annualReturn} setValue={setAnnualReturn} suffix="% per year" step={0.5} /><NumberInput label="Investment duration" value={years} setValue={setYears} suffix="years" min={1} /></>} />;
}

function CalculatorLayout({ inputs }: { inputs: ReactNode }) {
  return <section className="planner-layout"><div className="panel planner-controls">{inputs}<small className="calculator-note">Inputs are collected here. The projection must be calculated by the connected deterministic backend tool.</small></div><div className="wealth-card calculation-awaiting"><p>Expected wealth · Estimate</p><h2>—</h2><div className="projection-chart" aria-label="Projection awaiting calculation"><span>Today</span><div className="empty-projection">Awaiting calculation</div><span>Expected wealth</span></div><div className="wealth-formula"><span>Total contributions<strong>—</strong></span><i>+</i><span>Estimated growth<strong>—</strong></span><i>=</i><span>Expected wealth<strong>—</strong></span></div><small>No client-side financial calculation is performed. Results will be shown when the backend calculation tool returns them.</small></div></section>;
}

function NumberInput({ label, value, setValue, suffix, min = 0, step = 1 }: { label: string; value: number; setValue: (value: number) => void; suffix: string; min?: number; step?: number }) {
  return <label>{label}<input type="number" min={min} step={step} value={value} onChange={(event) => setValue(Number(event.target.value))} /><span>{suffix}</span></label>;
}

function ChoiceInput({ label, value, setValue, options }: { label: string; value: string; setValue: (value: string) => void; options: { value: string; label: string }[] }) {
  return <label>{label}<select value={value} onChange={(event) => setValue(event.target.value)}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}

function RollingReturns({ onExplore }: { onExplore: () => void }) {
  const [period, setPeriod] = useState("3Y");
  return <section className="rolling-returns"><div className="rolling-heading"><div><p className="eyebrow">ROLLING RETURNS</p><h3>Consistency across different starting periods</h3><p>Rolling returns show performance across different starting periods instead of only one fixed period.</p></div><div className="rolling-periods" role="tablist" aria-label="Rolling return period">{["1Y", "3Y", "5Y"].map((value) => <button key={value} className={period === value ? "active" : ""} onClick={() => setPeriod(value)}>{value}</button>)}</div></div><div className="rolling-chart"><div className="chart-unavailable"><strong>{period} return history awaiting data</strong><span>A line chart and benchmark comparison will appear when a fund and its historical return series are available.</span></div></div><div className="table-shell"><table className="rolling-table"><thead><tr><th>Fund</th><th>Period</th><th>Minimum</th><th>Median</th><th>Maximum</th><th>Benchmark</th></tr></thead><tbody><tr><td colSpan={6}><div className="table-empty"><strong>No rolling-return series available</strong><span>Select a fund with historical data to compare its return range and benchmark across rolling windows.</span></div></td></tr></tbody></table></div><button className="primary-button" onClick={onExplore}>Explore funds</button></section>;
}

function MarketView() {
  const [tab, setTab] = useState<MarketTab>("india");
  const indiaIndices = ["NIFTY 50", "SENSEX", "NIFTY BANK", "NIFTY IT"];
  return <div className="view-stack"><ViewHeading eyebrow="MARKET" title="A focused market view" description="Market context should complement mutual-fund research, not turn this product into a trading app." />
    <div className="segmented" role="tablist" aria-label="Market regions"><TabButton active={tab === "india"} onClick={() => setTab("india")}>India</TabButton><TabButton active={tab === "us"} onClick={() => setTab("us")}>US</TabButton><TabButton active={tab === "europe"} onClick={() => setTab("europe")}>Europe</TabButton><TabButton active={tab === "currencies"} onClick={() => setTab("currencies")}>Currencies</TabButton><TabButton active={tab === "crypto"} onClick={() => setTab("crypto")}>Crypto</TabButton><TabButton active={tab === "futures"} onClick={() => setTab("futures")}>Futures</TabButton></div>
    <section className="market-search"><label>Search company, stock, or index<input placeholder="Search will be enabled with a market-data provider" disabled /></label><span>Market status unavailable</span></section>
    {tab === "india" ? <section className="market-cards" aria-label="India market indices awaiting data">{indiaIndices.map((index) => <article className="market-index-card" key={index}><p>{index}</p><h3>—</h3><span>Change — · —</span><div className="sparkline-empty">Awaiting market feed</div></article>)}</section> : <section className="market-placeholder"><p className="eyebrow">{tab.toUpperCase()} MARKET OVERVIEW</p><h3>Market data unavailable</h3><p>This region will appear only when a supported data provider is connected.</p></section>}
    <section className="market-summary"><div><p className="eyebrow">{tab === "india" ? "INDIA" : tab.toUpperCase()} MARKET SUMMARY</p><h3>Market summary unavailable</h3><p>Research headlines and a concise data-backed summary will appear here when the selected market is supported by a connected provider.</p></div><div className="source-meta"><span>Source: Awaiting market data</span><span>As of: —</span></div></section>
    <section className="market-watchlist"><div className="watchlist-heading"><div><p className="eyebrow">WATCHLIST</p><h3>Track companies, indices and securities</h3></div><button className="outline-button" disabled>Add to watchlist</button></div><div className="table-shell"><table className="watchlist-table"><thead><tr><th>Company or security</th><th>Price</th><th>Change</th><th>As of</th></tr></thead><tbody><tr><td colSpan={4}><div className="table-empty"><strong>Your watchlist is empty</strong><span>Search and market data must be available before a company, index, or security can be tracked.</span></div></td></tr></tbody></table></div></section>
    <section className="company-flow"><div><p className="eyebrow">COMPANY → FUND → PORTFOLIO</p><h3>Trace a company event to your actual exposure</h3><p>Use this relationship to understand how a company announcement can reach the funds you hold and your portfolio.</p></div><div className="relationship-flow"><span>Company announcement</span><i>↓</i><span>Company</span><i>↓</i><span>Funds holding company</span><i>↓</i><span>Your funds</span><i>↓</i><span>Your portfolio exposure</span></div><div className="company-flow-empty"><strong>No company relationship data available</strong><span>Select a company after the market feed and portfolio analysis are connected to view funds, exposure, sources, and timestamps.</span><div className="source-meta"><span>Source: —</span><span>As of: —</span></div></div></section>
  </div>;
}

function ViewHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className="view-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{description}</p></div></div>;
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return <button role="tab" aria-selected={active} className={active ? "tab-button active" : "tab-button"} onClick={onClick}>{children}</button>;
}

createRoot(document.getElementById("root")!).render(<App />);
