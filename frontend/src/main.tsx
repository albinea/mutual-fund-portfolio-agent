import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, FormEvent, ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Page = "assistant" | "portfolio" | "explorer" | "overlap" | "calculators" | "market";
type ExplorerTab = "scanner" | "discovery" | "compare" | "commentary";
type CalculatorTab = "sip" | "wealth" | "rolling";
type PortfolioTab = "overview" | "holdings" | "allocation" | "changes";
type MarketTab = "india" | "us" | "europe" | "currencies" | "crypto" | "futures";
type Message = { role: "user" | "assistant"; content: string; sources?: Source[]; trace?: ToolTrace[] };
type Source = { name?: string; url?: string | null; data_as_of?: string | null };
type ToolTrace = { activity: string; success: boolean };
type ChatResponse = { success: boolean; answer: string; error_code?: string; sources?: Source[]; tool_trace?: ToolTrace[]; conversation_id?: string };
type ApiEnvelope<T> = { success: boolean; data: T; sources: Source[]; message?: string | null; error_code?: string };
type PortfolioSummary = { total_invested: number; current_value: number; change: number; change_percent: number; fund_count: number; company_count: number | null; as_of?: string | null };
type Holding = { fund_id: string; fund_name: string; category?: string | null; units: number; invested_amount: number; current_value: number; allocation_percent: number };
type AllocationItem = { name: string; value: number; percentage: number; funds: string[] };
type Allocation = { group_by: string; items: AllocationItem[]; as_of?: string | null };
type Overlap = { overall_overlap_percent: number; explanation: string; companies: { company: string; combined_exposure_percent: number; funds: { fund_name: string; fund_holding_percent?: number; portfolio_contribution_percent?: number }[] }[] };
type Fund = { fund_id: string; fund_name: string; category?: string | null; risk_level?: string | null; return_3y?: number | null; expense_ratio?: number | null; fund_size?: number | null; risk_adjusted_rating?: number | null; manager_name?: string | null; as_of?: string | null };
type FundList = { results: Fund[]; total: number; page: number; page_size: number };
type CalculatorResult = { total_invested?: number; total_contribution?: number; estimated_returns?: number; estimated_growth?: number; expected_wealth: number; disclaimer: string; assumptions?: string[]; yearly_projection?: { year: number; total_invested: number; expected_wealth: number }[] };
type WatchlistItem = { id: number; symbol: string; name: string; price?: number | null; change_percent?: number | null; as_of?: string | null; provider?: string | null; data_mode?: string | null };
type MarketQuote = { company_id: string; name: string; symbol: string; exchange: string; currency: string; price: number; change_percent?: number | null; as_of?: string | null; source?: string; data_mode?: string };
type MarketOverview = { configured: boolean; provider: string; data_mode: string; items: MarketQuote[]; unavailable: { company_id: string; name: string; message: string }[] };
type CompanyExposure = { company: { company_id: string; name: string; sector: string }; funds_holding_company: { fund_id: string; fund_name: string; fund_exposure_percent: number; portfolio_contribution_percent?: number; in_user_portfolio: boolean }[]; user_portfolio_exposure_percent: number; data_as_of?: string | null; source_names?: string[] };
type ConversationSummary = { id: string; title: string; latest_message_preview: string; message_count: number; created_at: string; updated_at: string };
type ConversationList = { results: ConversationSummary[] };
type ConversationDetail = { id: string; created_at: string; updated_at: string; messages: { role: "user" | "assistant"; content: string; created_at: string }[] };
type PortfolioImportResult = { import_id: number; holding_count: number; source_file_name: string; source_format: string; snapshot_date: string; is_active: boolean };
type FundDisclosureImportResult = { disclosure_import_id: number; holding_count: number; source_file_name: string; source_format: string; disclosure_date: string };
type PortfolioSnapshot = { id: number; snapshot_date: string; source_file_name: string; source_format: string; holding_count: number; is_active: boolean };
type PortfolioChangesData = { available: boolean; snapshots: PortfolioSnapshot[]; newer_snapshot?: { id: number; snapshot_date: string; source_file_name: string }; older_snapshot?: { id: number; snapshot_date: string; source_file_name: string }; changes: { change_type: "Added" | "Removed" | "Increased" | "Decreased"; fund_name: string; current_value_change: number; invested_amount_change: number; newer_current_value: number; older_current_value: number }[] };
type IconName = "assistant" | "portfolio" | "explorer" | "overlap" | "calculator" | "market" | "compare" | "search" | "settings" | "bell" | "send" | "attach" | "arrow" | "menu";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const navigation: { id: Page; label: string; icon: IconName }[] = [
  { id: "assistant", label: "AI Assistant", icon: "assistant" },
  { id: "portfolio", label: "Portfolio", icon: "portfolio" },
  { id: "explorer", label: "Fund explorer", icon: "explorer" },
  { id: "overlap", label: "Overlap", icon: "overlap" },
  { id: "calculators", label: "Calculators", icon: "calculator" },
  { id: "market", label: "Market", icon: "market" },
];

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || payload.answer || payload.error_code || "The request could not be completed.");
  }
  return payload as T;
}

function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(Boolean(path));

  useEffect(() => {
    let active = true;
    if (!path) {
      setData(null);
      setLoading(false);
      return () => { active = false; };
    }
    setLoading(true);
    setError("");
    apiRequest<ApiEnvelope<T> | T>(path)
      .then((response) => {
        if (!active) return;
        const envelope = response as Partial<ApiEnvelope<T>>;
        setData(envelope.data ?? (response as T));
      })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "Unable to load data."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [path]);

  return { data, error, loading };
}

function money(value: number | null | undefined) {
  return value == null ? "Not available" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);
}

function valueOrUnavailable(value: string | number | null | undefined, suffix = "") {
  return value == null ? "Not available" : `${value}${suffix}`;
}

function StarRating({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="muted">Not available</span>;
  const stars = Math.max(1, Math.min(5, Math.round(score)));
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
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationRefresh, setConversationRefresh] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [chatFiles, setChatFiles] = useState<File[]>([]);
  const [portfolioRefresh, setPortfolioRefresh] = useState(0);
  const [selectedFundIds, setSelectedFundIds] = useState<string[]>(["F001", "F002"]);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const history = useApi<ConversationList>(userId.trim() ? `/chat/conversations/?user_id=${encodeURIComponent(userId.trim())}&refresh=${conversationRefresh}` : null);

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

  function startNewConversation() {
    setConversationId(null);
    setMessages([]);
    setDraft("");
    setError("");
  }

  async function reopenConversation(id: string) {
    if (!userId.trim() || historyLoading) return;
    setHistoryLoading(true);
    setError("");
    try {
      const conversation = await apiRequest<ConversationDetail>(`/chat/conversations/${id}/?user_id=${encodeURIComponent(userId.trim())}`);
      setConversationId(conversation.id);
      setMessages(conversation.messages.map((message) => ({ role: message.role, content: message.content })));
      setHistoryOpen(false);
      setPage("assistant");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to load this conversation.");
    } finally {
      setHistoryLoading(false);
    }
  }

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
      // Existing chat API contract is intentionally preserved.
      const response = await fetch(`${apiBaseUrl}/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId.trim(),
          message,
          ...(conversationId ? { conversation_id: conversationId } : {}),
        }),
      });
      const payload: ChatResponse = await response.json();
      if (!response.ok || !payload.success) {
        throw new Error(payload.answer || payload.error_code || "The assistant could not answer right now.");
      }
      setMessages([...nextMessages, { role: "assistant", content: payload.answer, sources: payload.sources, trace: payload.tool_trace }]);
      setConversationId(payload.conversation_id ?? conversationId);
      setConversationRefresh((current) => current + 1);
      setChatFiles([]);
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
    link.download = "mutual-fund-analysis.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to main content</a>
    {mobileMenuOpen && <button className="mobile-nav-backdrop" aria-label="Close navigation" onClick={() => setMobileMenuOpen(false)} />}
    <aside className={mobileMenuOpen ? "sidebar mobile-open" : "sidebar"}>
      <div className="brand"><span>M</span><div><strong>MF Portfolio Agent</strong><small>Mutual Fund Intelligence</small></div></div>
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
        <div className="topbar-brand"><strong>MF Portfolio Agent</strong><small>Mutual Fund Intelligence</small></div>
        <form className="universal-search" onSubmit={submitQuickSearch}><Icon name="search" size={17} /><input value={quickSearch} onChange={(event) => setQuickSearch(event.target.value)} placeholder="Search funds, companies, or ask a question" aria-label="Ask anything or search" /><button type="submit">Search</button></form>
        <button className="mobile-menu-toggle" aria-label="Open navigation" onClick={() => setMobileMenuOpen(true)}><Icon name="menu" /></button>
        <div className="topbar-actions"><label className="user-select">Portfolio <input value={userId} onChange={(event) => { setUserId(event.target.value); setConversationId(null); setMessages([]); setHistoryOpen(false); }} aria-label="Portfolio user ID" /></label><button className="icon-button" aria-label="Settings"><Icon name="settings" /></button><button className="icon-button" aria-label="Notifications"><Icon name="bell" /></button><button className="avatar" aria-label="Account">MF</button></div>
      </header>
      <main id="main-content" className={page === "assistant" ? "content" : "content app-content"} tabIndex={-1}>
        <div className="page-main">
          {page === "assistant" && <AssistantView userId={userId} messages={messages} conversationId={conversationId} history={history.data?.results ?? []} historyError={history.error} historyLoading={history.loading || historyLoading} historyOpen={historyOpen} draft={draft} setDraft={setDraft} files={chatFiles} error={error} isSending={isSending} onFiles={selectChatFiles} onSend={sendMessage} onExport={exportAnswer} onShortcut={openAssistant} onImport={() => openPortfolio("overview")} onNewConversation={startNewConversation} onOpenConversation={reopenConversation} onToggleHistory={() => setHistoryOpen((open) => !open)} />}
          {page === "portfolio" && <PortfolioView userId={userId} tab={portfolioTab} onTab={setPortfolioTab} refreshKey={portfolioRefresh} onImported={() => setPortfolioRefresh((current) => current + 1)} onAsk={openAssistant} />}
          {page === "explorer" && <ExplorerView tab={explorerTab} onTab={setExplorerTab} selectedIds={selectedFundIds} onToggle={toggleFund} onCompare={() => setExplorerTab("compare")} />}
          {page === "overlap" && <OverlapView userId={userId} onImport={() => setPage("portfolio")} />}
          {page === "calculators" && <CalculatorsView tab={calculatorTab} onTab={setCalculatorTab} onExplore={() => openExplorer("scanner")} />}
          {page === "market" && <MarketView userId={userId} />}
        </div>
      </main>
    </section>
  </div>;
}

function normalizeMarkdown(content: string) {
  return content.replace(/\r\n/g, "\n").replaceAll("\\|", "|");
}

function markdownTableToCsv(content: string) {
  const rows = normalizeMarkdown(content).split("\n").map((line) => line.trim()).filter((line) => /^\|?.+\|.+\|?$/.test(line) && !/^\|?\s*:?-{3,}/.test(line));
  if (rows.length < 2) return null;
  return rows.map((row) => row.replace(/^\||\|$/g, "").split("|").map((cell) => `"${cell.trim().replaceAll('"', '""')}"`).join(",")).join("\n");
}

function hasStructuredTable(content: string) {
  return Boolean(markdownTableToCsv(content));
}

function AssistantView({ userId, messages, conversationId, history, historyError, historyLoading, historyOpen, draft, setDraft, files, error, isSending, onFiles, onSend, onExport, onShortcut, onImport, onNewConversation, onOpenConversation, onToggleHistory }: { userId: string; messages: Message[]; conversationId: string | null; history: ConversationSummary[]; historyError: string; historyLoading: boolean; historyOpen: boolean; draft: string; setDraft: (value: string) => void; files: File[]; error: string; isSending: boolean; onFiles: (event: ChangeEvent<HTMLInputElement>) => void; onSend: (event: FormEvent) => void; onExport: (message: Message) => void; onShortcut: (prompt: string) => void; onImport: () => void; onNewConversation: () => void; onOpenConversation: (id: string) => void; onToggleHistory: () => void }) {
  const prompts = [
    { label: "Analyze", prompt: "Analyze my portfolio" },
    { label: "Compare", prompt: "Compare my funds" },
    { label: "Explore", prompt: "Explain this fund" },
    { label: "Exposure", prompt: "What sectors am I exposed to?" },
    { label: "Risk", prompt: "Explain the risk of my portfolio" },
    { label: "Changes", prompt: "What changed in my portfolio?" },
  ];
  return <div className="assistant-page">
    <div className="assistant-toolbar">
      <div className="conversation-status"><span className="conversation-status-dot" /><div><p className="eyebrow">AI ASSISTANT</p><strong>{conversationId ? "Current conversation" : "New conversation"}</strong></div></div>
      <div className="conversation-actions"><button className="conversation-action new-chat" type="button" onClick={onNewConversation}><span aria-hidden="true">+</span> New chat</button><button className={historyOpen ? "conversation-action history-toggle active" : "conversation-action history-toggle"} type="button" aria-expanded={historyOpen} onClick={onToggleHistory}><span aria-hidden="true">◷</span> Past chats</button></div>
    </div>
    {historyOpen && <ConversationHistory conversations={history} activeId={conversationId} loading={historyLoading} error={historyError} onOpen={onOpenConversation} />}
    <section className="chat-stage" aria-live="polite">
      {messages.length === 0 ? <div className="assistant-welcome">
        <h2>Search and understand your portfolio</h2>
        <p>Ask a question, compare funds, or explore the data behind your investments.</p>
        <ChatComposer draft={draft} setDraft={setDraft} files={files} isSending={isSending} onFiles={onFiles} onSend={onSend} home />
        <div className="prompt-grid" aria-label="Suggested research prompts">{prompts.map((item) => <button key={item.label} onClick={() => onShortcut(item.prompt)}><Icon name="arrow" size={15} />{item.label}</button>)}</div>
        <HomeSnapshots userId={userId} onImport={onImport} />
      </div> : <div className="conversation">{messages.map((item, index) => <ChatMessage key={`${item.role}-${index}`} message={item} onExport={onExport} />)}</div>}
      {isSending && <div className="message assistant loading"><div className="message-label">MF Portfolio Agent</div><p><span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" /> Reviewing your request</p></div>}
    </section>
    {messages.length > 0 && <ChatComposer draft={draft} setDraft={setDraft} files={files} isSending={isSending} onFiles={onFiles} onSend={onSend} />}
    {error && <p className="error" role="alert" aria-live="assertive">{error}</p>}
  </div>;
}

function historyPreview(content: string) {
  const plainText = normalizeMarkdown(content)
    .replace(/```[\s\S]*?```/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[\*_`#>]/g, "")
    .replace(/\|/g, " · ")
    .replace(/\s+/g, " ")
    .trim();
  return plainText.length > 150 ? `${plainText.slice(0, 147).trimEnd()}…` : plainText;
}

function formatHistoryDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

function ConversationHistory({ conversations, activeId, loading, error, onOpen }: { conversations: ConversationSummary[]; activeId: string | null; loading: boolean; error: string; onOpen: (id: string) => void }) {
  return <section className="conversation-history" aria-label="Past conversations">
    <header className="conversation-history-heading"><div><p className="eyebrow">SAVED CONVERSATIONS</p><h2>Continue where you left off</h2><span>Only chats for this portfolio user are shown.</span></div><b className="history-count">{conversations.length}</b></header>
    {loading ? <p className="history-feedback">Loading conversations…</p> : error ? <p className="form-error">{error}</p> : conversations.length ? <div className="conversation-history-list">{conversations.map((conversation) => <button type="button" key={conversation.id} className={conversation.id === activeId ? "history-item active" : "history-item"} aria-current={conversation.id === activeId ? "page" : undefined} onClick={() => onOpen(conversation.id)}><span className="history-item-icon" aria-hidden="true">◷</span><span className="history-item-copy"><strong>{historyPreview(conversation.title) || "New conversation"}</strong><span>{historyPreview(conversation.latest_message_preview) || "No messages yet"}</span><small><span>{conversation.message_count} {conversation.message_count === 1 ? "message" : "messages"}</span><span>{formatHistoryDate(conversation.updated_at)}</span></small></span><span className="history-item-arrow" aria-hidden="true">›</span></button>)}</div> : <p className="history-feedback">No saved conversations for this portfolio user yet.</p>}
  </section>;
}

function ChatComposer({ draft, setDraft, files, isSending, onFiles, onSend, home = false }: { draft: string; setDraft: (value: string) => void; files: File[]; isSending: boolean; onFiles: (event: ChangeEvent<HTMLInputElement>) => void; onSend: (event: FormEvent) => void; home?: boolean }) {
  return <form className={home ? "composer home-composer" : "composer"} onSubmit={onSend}>{files.length > 0 && <div className="attachment-list">{files.map((file) => <span key={`${file.name}-${file.size}`}>{file.name}</span>)}<small>Selected files will be supported when the document-ingestion endpoint is connected.</small></div>}<textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask anything about your mutual funds" rows={home ? 2 : 3} /><div className="composer-footer"><label className="attach-control"><input type="file" accept=".pdf,.xlsx,.xls,.csv" multiple onChange={onFiles} /><Icon name="attach" size={16} />Attach</label><span>Evidence-led research, not investment advice.</span><button className="send-button" disabled={isSending || !draft.trim()} aria-label="Send message"><Icon name="send" size={16} /></button></div></form>;
}

function renderInlineMarkdown(value: string): ReactNode[] {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\)|\*[^*]+\*)/g;
  return value.split(pattern).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("*") && part.endsWith("*")) return <em key={index}>{part.slice(1, -1)}</em>;
    const link = /^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/.exec(part);
    if (link) return <a key={index} href={link[2]} target="_blank" rel="noreferrer">{link[1]}</a>;
    return part;
  });
}

function splitMarkdownTableRow(line: string) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function isMarkdownTableDivider(line: string) {
  const cells = splitMarkdownTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function MarkdownMessage({ content }: { content: string }) {
  const lines = normalizeMarkdown(content).split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    if (line.startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) { code.push(lines[index]); index += 1; }
      if (index < lines.length) index += 1;
      blocks.push(<pre key={`code-${index}`}><code>{code.join("\n")}</code></pre>);
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      const Heading = `h${heading[1].length}` as "h1" | "h2" | "h3";
      blocks.push(<Heading key={`heading-${index}`}>{renderInlineMarkdown(heading[2])}</Heading>);
      index += 1;
      continue;
    }
    if (line.includes("|") && index + 1 < lines.length && isMarkdownTableDivider(lines[index + 1])) {
      const headers = splitMarkdownTableRow(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) { rows.push(splitMarkdownTableRow(lines[index])); index += 1; }
      blocks.push(<div className="markdown-table-wrap" key={`table-${index}`}><table><thead><tr>{headers.map((header, headerIndex) => <th key={headerIndex}>{renderInlineMarkdown(header)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{headers.map((_, cellIndex) => <td key={cellIndex}>{renderInlineMarkdown(row[cellIndex] ?? "")}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
      blocks.push(<hr key={`rule-${index}`} />);
      index += 1;
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*[-*+]\s+/.test(lines[index])) { items.push(lines[index].replace(/^\s*[-*+]\s+/, "")); index += 1; }
      blocks.push(<ul key={`list-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{renderInlineMarkdown(item)}</li>)}</ul>);
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) { items.push(lines[index].replace(/^\s*\d+[.)]\s+/, "")); index += 1; }
      blocks.push(<ol key={`ordered-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}>{renderInlineMarkdown(item)}</li>)}</ol>);
      continue;
    }
    if (line.startsWith(">")) {
      blocks.push(<blockquote key={`quote-${index}`}>{renderInlineMarkdown(line.replace(/^>\s?/, ""))}</blockquote>);
      index += 1;
      continue;
    }
    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() && !lines[index].startsWith("```") && !/^(#{1,3})\s+/.test(lines[index]) && !/^\s*[-*+]\s+/.test(lines[index]) && !/^\s*\d+[.)]\s+/.test(lines[index]) && !lines[index].startsWith(">")) { paragraph.push(lines[index]); index += 1; }
    blocks.push(<p key={`paragraph-${index}`}>{paragraph.map((part, partIndex) => <span key={partIndex}>{renderInlineMarkdown(part)}{partIndex < paragraph.length - 1 && <br />}</span>)}</p>);
  }
  return <div className="markdown-message">{blocks}</div>;
}

function ChatMessage({ message, onExport }: { message: Message; onExport: (message: Message) => void }) {
  const exportable = message.role === "assistant" && hasStructuredTable(message.content);
  return <article className={`message ${message.role}`}><div className="message-label">{message.role === "user" ? "You" : "MF Portfolio Agent"}</div><div className="message-content">{message.role === "assistant" ? <MarkdownMessage content={message.content} /> : <p>{message.content}</p>}</div>
    {message.role === "assistant" && <><div className="message-meta">{message.trace?.filter((step) => step.success).map((step) => <span key={step.activity}>✓ {step.activity}</span>)}</div>
      {message.sources?.length ? <div className="sources">{message.sources.map((source, index) => source.url ? <a key={`${source.name}-${index}`} href={source.url} target="_blank" rel="noreferrer">Source: {source.name ?? "Source"}{source.data_as_of ? ` · As of ${source.data_as_of}` : ""}</a> : <span key={`${source.name}-${index}`}>Source: {source.name ?? "Source"}{source.data_as_of ? ` · As of ${source.data_as_of}` : ""}</span>)}</div> : null}
      {exportable && <button className="text-action" onClick={() => onExport(message)}>Export CSV</button>}
    </>}
  </article>;
}

function HomeSnapshots({ userId, onImport }: { userId: string; onImport: () => void }) {
  const summary = useApi<PortfolioSummary>(userId.trim() ? `/portfolio/summary/?user_id=${encodeURIComponent(userId.trim())}` : null);
  return <section className="home-snapshots" aria-label="Portfolio and market snapshots"><article><p className="eyebrow">YOUR PORTFOLIO</p><h3>{summary.loading ? "Loading portfolio…" : summary.error ? "Portfolio unavailable" : money(summary.data?.current_value)}</h3><p>{summary.error ? summary.error : `${summary.data?.fund_count ?? 0} funds · invested ${money(summary.data?.total_invested)}`}</p><button className="text-action" type="button" onClick={onImport}>View portfolio</button></article><article><p className="eyebrow">MARKET</p><h3>Market data is currently unavailable</h3><p>India indices and a concise market summary will appear when a supported provider is connected.</p><div className="source-meta"><span>Source: —</span><span>As of: —</span></div></article></section>;
}

function PortfolioView({ userId, tab, onTab, refreshKey, onImported, onAsk }: { userId: string; tab: PortfolioTab; onTab: (tab: PortfolioTab) => void; refreshKey: number; onImported: () => void; onAsk: (prompt: string) => void }) {
  const encodedUser = encodeURIComponent(userId);
  const summary = useApi<PortfolioSummary>(userId ? `/portfolio/summary/?user_id=${encodedUser}&refresh=${refreshKey}` : null);
  const holdings = useApi<{ results: Holding[]; total: number }>(userId ? `/portfolio/holdings/?user_id=${encodedUser}&refresh=${refreshKey}` : null);
  const allocation = useApi<Allocation>(userId ? `/portfolio/allocation/?user_id=${encodedUser}&group_by=category&refresh=${refreshKey}` : null);
  return <div className="view-stack">
    <ViewHeading eyebrow="YOUR PORTFOLIO" title="Understand the portfolio you already own" description="Verified portfolio values are supplied by the Django API." />
    <div className="segmented" role="tablist" aria-label="Portfolio sections"><TabButton active={tab === "overview"} onClick={() => onTab("overview")}>Overview</TabButton><TabButton active={tab === "holdings"} onClick={() => onTab("holdings")}>Holdings</TabButton><TabButton active={tab === "allocation"} onClick={() => onTab("allocation")}>Allocation & exposure</TabButton><TabButton active={tab === "changes"} onClick={() => onTab("changes")}>What changed?</TabButton></div>
    {tab === "overview" && <><PortfolioSummary summary={summary.data} loading={summary.loading} error={summary.error} /><PortfolioImportPanel userId={userId} onImported={onImported} /></>}
    {tab === "holdings" && <PortfolioTable holdings={holdings.data?.results ?? []} loading={holdings.loading} error={holdings.error} />}
    {tab === "allocation" && <PortfolioAllocation allocation={allocation.data} loading={allocation.loading} error={allocation.error} />}
    {tab === "changes" && <PortfolioChanges userId={userId} refreshKey={refreshKey} onAsk={onAsk} />}
  </div>;
}

function PortfolioSummary({ summary, loading, error }: { summary: PortfolioSummary | null; loading: boolean; error: string }) {
  return <section className="portfolio-summary" aria-label="Portfolio summary">{loading ? <div><p>Loading portfolio…</p></div> : error ? <div><p>{error}</p></div> : <><div><p className="eyebrow">MY PORTFOLIO</p><h3>Portfolio summary</h3><small>As of {summary?.as_of ?? "Not available"}</small></div><div className="summary-metric"><span>Total invested</span><strong>{money(summary?.total_invested)}</strong></div><div className="summary-metric"><span>Current value</span><strong>{money(summary?.current_value)}</strong></div><div className="summary-metric"><span>Change</span><strong>{money(summary?.change)} {summary ? `(${summary.change_percent}%)` : ""}</strong></div></>}</section>;
}

function PortfolioImportPanel({ userId, onImported }: { userId: string; onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [asOfDate, setAsOfDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [result, setResult] = useState<PortfolioImportResult | null>(null);
  const [error, setError] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setResult(null);
    setError("");
  }

  async function uploadStatement() {
    if (!file || !userId.trim() || isUploading) return;
    setIsUploading(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("user_id", userId.trim());
      formData.append("file", file);
      if (asOfDate) formData.append("as_of_date", asOfDate);
      const response = await fetch(`${apiBaseUrl}/portfolio/import/`, { method: "POST", body: formData });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.success) throw new Error(payload.message || "The statement could not be imported.");
      setResult(payload.data as PortfolioImportResult);
      onImported();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to import this statement.");
    } finally {
      setIsUploading(false);
    }
  }

  return <><section className="import-state"><div><span className="import-symbol">↓</span><h3>Import holdings</h3><p>Upload a portfolio statement for {userId || "the selected user"}. The newest snapshot date becomes this user’s active portfolio.</p><small>CSV or XLSX only · Required columns: <code>fund_name</code>, <code>invested_amount</code>, <code>current_value</code> · Optional: <code>units</code>, <code>category</code>. PDF statements are not supported yet.</small></div><div className="import-actions"><label className="snapshot-date">Snapshot date<input type="date" value={asOfDate} onChange={(event) => setAsOfDate(event.target.value)} /></label><label className="primary-button import-button"><input type="file" accept=".csv,.xlsx" onChange={chooseFile} />Choose a statement</label>{file && <button className="outline-button" type="button" onClick={uploadStatement} disabled={isUploading}>{isUploading ? "Importing…" : "Import statement"}</button>}</div></section>{file && <section className="upload-ready"><div className="upload-status"><span>{result ? "✓" : "↑"}</span><div><strong>{file.name}</strong><p>{result ? `Imported ${result.holding_count} holdings for ${userId}.` : "Ready to validate and import this statement."}</p></div></div>{result ? <div className="upload-detection"><span>{result.is_active ? "Active snapshot" : "Historical snapshot"}<b>{result.snapshot_date}</b></span><span>File type <b>{result.source_format.toUpperCase()}</b></span></div> : <div className="upload-detection"><span>Supported files <b>CSV, XLSX</b></span><span>Maximum size <b>2 MB</b></span></div>}{error && <p className="form-error">{error}</p>}{result && <small className="integration-note">{result.is_active ? "Overview, holdings, and category allocation now use this imported snapshot." : "This older statement is saved for comparison; the newer dated snapshot remains active."} Company-level overlap and the AI agent still need fund-disclosure mapping before they can use imported data.</small>}</section>}</>;
}

function PortfolioTable({ holdings, loading, error }: { holdings: Holding[]; loading: boolean; error: string }) {
  const [query, setQuery] = useState("");
  const rows = holdings.filter((holding) => holding.fund_name.toLowerCase().includes(query.toLowerCase()));
  return <section className="holdings-panel"><div className="holdings-toolbar"><div><p className="eyebrow">FUND HOLDINGS</p><h3>{holdings.length} funds in this portfolio</h3></div><div className="table-tools"><label>Search holdings<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by fund" /></label></div></div><section className="table-shell"><table className="holdings-table"><thead><tr><th>Fund</th><th>Category</th><th>Units</th><th>Invested</th><th>Current value</th><th>Allocation</th></tr></thead><tbody>{loading ? <tr><td colSpan={6}>Loading holdings…</td></tr> : error ? <tr><td colSpan={6}>{error}</td></tr> : rows.length ? rows.map((holding) => <tr key={holding.fund_id}><td><strong>{holding.fund_name}</strong></td><td><span className="category-pill">{holding.category ?? "Not available"}</span></td><td className="numeric-cell">{new Intl.NumberFormat("en-IN", { maximumFractionDigits: 4 }).format(holding.units)}</td><td className="numeric-cell">{money(holding.invested_amount)}</td><td className="numeric-cell current-value">{money(holding.current_value)}</td><td className="numeric-cell"><span className="allocation-value">{holding.allocation_percent.toFixed(2)}%</span></td></tr>) : <tr><td colSpan={6}><div className="table-empty"><strong>No matching holdings</strong><span>Try a different fund name.</span></div></td></tr>}</tbody></table></section></section>;
}

function PortfolioAllocation({ allocation, loading, error }: { allocation: Allocation | null; loading: boolean; error: string }) {
  return <section className="sector-exposure"><div className="sector-heading"><div><p className="eyebrow">PORTFOLIO ALLOCATION</p><h3>See the categories behind your funds</h3><p>Allocation is calculated from the active portfolio snapshot. Company and sector exposure need verified fund-disclosure mappings.</p></div></div><div className="table-shell"><table className="sector-table"><thead><tr><th>Category</th><th>Value</th><th>Percentage</th><th>Underlying funds</th></tr></thead><tbody>{loading ? <tr><td colSpan={4}>Loading allocation…</td></tr> : error ? <tr><td colSpan={4}>{error}</td></tr> : allocation?.items.map((item) => <tr key={item.name}><td>{item.name}</td><td>{money(item.value)}</td><td>{item.percentage}%</td><td>{item.funds.length ? item.funds.join(", ") : "Not available"}</td></tr>)}</tbody></table></div></section>;
}

function PortfolioChanges({ userId, refreshKey, onAsk }: { userId: string; refreshKey: number; onAsk: (prompt: string) => void }) {
  const snapshots = useApi<{ results: PortfolioSnapshot[] }>(userId ? `/portfolio/snapshots/?user_id=${encodeURIComponent(userId)}&refresh=${refreshKey}` : null);
  const [newerId, setNewerId] = useState("");
  const [olderId, setOlderId] = useState("");
  const availableSnapshots = snapshots.data?.results ?? [];
  useEffect(() => { if (availableSnapshots.length >= 2) { setNewerId((current) => availableSnapshots.some((item) => String(item.id) === current) ? current : String(availableSnapshots[0].id)); setOlderId((current) => availableSnapshots.some((item) => String(item.id) === current) && current !== String(availableSnapshots[0].id) ? current : String(availableSnapshots[1].id)); } }, [availableSnapshots]);
  const comparison = useApi<PortfolioChangesData>(newerId && olderId && newerId !== olderId ? `/portfolio/changes/?user_id=${encodeURIComponent(userId)}&newer_snapshot_id=${newerId}&older_snapshot_id=${olderId}` : null);
  const formatSnapshot = (snapshot: PortfolioSnapshot) => `${snapshot.snapshot_date} · ${snapshot.source_file_name}`;
  return <><section className="changes-header"><div><p className="eyebrow">PORTFOLIO CHANGES</p><h3>Compare two portfolio snapshots</h3><p>Added, removed, increased, and decreased fund positions are calculated from your dated imported statements.</p></div><div className="snapshot-selectors"><label>Newer snapshot<select value={newerId} onChange={(event) => setNewerId(event.target.value)} disabled={availableSnapshots.length < 2}><option value="">Select snapshot</option>{availableSnapshots.map((snapshot) => <option key={snapshot.id} value={snapshot.id}>{formatSnapshot(snapshot)}</option>)}</select></label><label>Older snapshot<select value={olderId} onChange={(event) => setOlderId(event.target.value)} disabled={availableSnapshots.length < 2}><option value="">Select snapshot</option>{availableSnapshots.map((snapshot) => <option key={snapshot.id} value={snapshot.id}>{formatSnapshot(snapshot)}</option>)}</select></label></div></section>{snapshots.loading ? <section className="changes-empty">Loading snapshots…</section> : snapshots.error ? <section className="changes-empty form-error">{snapshots.error}</section> : availableSnapshots.length < 2 ? <section className="changes-empty"><strong>Import two dated statements to compare changes.</strong><span>Choose the correct snapshot date during import; the latest import remains your active portfolio.</span></section> : <><section className="change-flow" aria-label="Portfolio comparison flow"><span>Older snapshot</span><i>→</i><span>Newer snapshot</span><i>→</i><span>Holding-level difference</span><i>→</i><span>Review changes</span></section><section className="table-shell changes-table-shell"><table className="changes-table"><thead><tr><th>Change</th><th>Fund holding</th><th>Previous value</th><th>New value</th><th>Value change</th></tr></thead><tbody>{comparison.loading ? <tr><td colSpan={5}>Comparing imported snapshots…</td></tr> : comparison.error ? <tr><td colSpan={5}>{comparison.error}</td></tr> : comparison.data?.changes.length ? comparison.data.changes.map((change) => <tr key={change.fund_name}><td><span className={`change-badge ${change.change_type.toLowerCase()}`}>{change.change_type}</span></td><td><strong>{change.fund_name}</strong></td><td>{money(change.older_current_value)}</td><td>{money(change.newer_current_value)}</td><td className={change.current_value_change >= 0 ? "positive-value" : "negative-value"}>{change.current_value_change > 0 ? "+" : ""}{money(change.current_value_change)}</td></tr>) : <tr><td colSpan={5}><div className="table-empty"><strong>No value changes between these snapshots</strong><span>The same funds and values appear in both statements.</span></div></td></tr>}</tbody></table></section><section className="evidence-empty"><strong>Change values come directly from the two imported statements.</strong><span>Explanations, manager commentary, and company-level causes need verified fund disclosures and document evidence before they can be shown.</span><button className="outline-button" onClick={() => onAsk("How should I interpret changes between two mutual-fund portfolio snapshots?")}>Ask about interpreting changes</button></section></>}</>;
}

function ExplorerView({ tab, onTab, selectedIds, onToggle, onCompare }: { tab: ExplorerTab; onTab: (tab: ExplorerTab) => void; selectedIds: string[]; onToggle: (id: string) => void; onCompare: () => void }) {
  const { data, loading, error } = useApi<FundList>("/funds/?page_size=100");
  const funds = data?.results ?? [];
  return <div className="view-stack"><ViewHeading eyebrow="FUND RESEARCH" title="Explore funds with context" description="Search, screen, and compare records provided by the Django fund API." />
    <div className="segmented" role="tablist" aria-label="Fund explorer sections"><TabButton active={tab === "scanner"} onClick={() => onTab("scanner")}>Scanner</TabButton><TabButton active={tab === "discovery"} onClick={() => onTab("discovery")}>Fund list</TabButton><TabButton active={tab === "compare"} onClick={() => onTab("compare")}>Compare {selectedIds.length > 0 ? `(${selectedIds.length})` : ""}</TabButton><TabButton active={tab === "commentary"} onClick={() => onTab("commentary")}>Manager commentary</TabButton></div>
    {tab === "scanner" && <Scanner funds={funds} loading={loading} error={error} selectedIds={selectedIds} onToggle={onToggle} onCompare={onCompare} />}
    {tab === "discovery" && <FundDiscovery funds={funds} loading={loading} error={error} onExplore={() => onTab("scanner")} />}
    {tab === "compare" && <Compare fundIds={selectedIds} onToggle={onToggle} onScan={() => onTab("scanner")} />}
    {tab === "commentary" && <Commentary />}
  </div>;
}

function FundDiscovery({ funds, loading, error, onExplore }: { funds: Fund[]; loading: boolean; error: string; onExplore: () => void }) {
  const [category, setCategory] = useState("All");
  const categories = ["All", ...Array.from(new Set(funds.map((fund) => fund.category).filter((item): item is string => Boolean(item))))];
  const rows = funds.filter((fund) => category === "All" || fund.category === category);
  return <><section className="discovery-toolbar"><div><p className="eyebrow">FUND LIST</p><h3>Browse configured fund records</h3></div><button className="outline-button" onClick={onExplore}>Open full scanner</button></section><div className="discovery-filters" aria-label="Fund categories">{categories.map((item) => <button key={item} className={category === item ? "active" : ""} onClick={() => setCategory(item)}>{item}</button>)}</div><div className="table-shell"><table className="discovery-table"><thead><tr><th>Fund</th><th>Category</th><th>Risk level</th><th>3Y return</th><th>Expense ratio</th><th>Fund size</th></tr></thead><tbody>{loading ? <tr><td colSpan={6}>Loading fund records…</td></tr> : error ? <tr><td colSpan={6}>{error}</td></tr> : rows.length ? rows.map((fund) => <tr key={fund.fund_id}><td><strong>{fund.fund_name}</strong></td><td><span className="fund-category">{valueOrUnavailable(fund.category)}</span></td><td>{valueOrUnavailable(fund.risk_level)}</td><td className="positive-value">{valueOrUnavailable(fund.return_3y, "%")}</td><td>{valueOrUnavailable(fund.expense_ratio, "%")}</td><td>{valueOrUnavailable(fund.fund_size)}</td></tr>) : <tr><td colSpan={6}><div className="table-empty"><strong>No funds in this category</strong><span>Try another category, or add data to the configured fund source.</span></div></td></tr>}</tbody></table></div><details className="methodology"><summary>How are funds listed?</summary><p>This list displays the fund master data exposed by the backend. Missing return or rating fields are deliberately shown as unavailable instead of being estimated in the browser.</p></details></>;
}

function Scanner({ funds, loading, error, selectedIds, onToggle, onCompare }: { funds: Fund[]; loading: boolean; error: string; selectedIds: string[]; onToggle: (id: string) => void; onCompare: () => void }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [risk, setRisk] = useState("All");
  const visibleFunds = useMemo(() => funds.filter((fund) => fund.fund_name.toLowerCase().includes(query.toLowerCase()) && (category === "All" || fund.category === category) && (risk === "All" || fund.risk_level === risk)), [funds, query, category, risk]);
  const categories = ["All", ...Array.from(new Set(funds.map((fund) => fund.category).filter((item): item is string => Boolean(item))))];
  const risks = ["All", ...Array.from(new Set(funds.map((fund) => fund.risk_level).filter((item): item is string => Boolean(item))))];
  return <><div className="filter-bar"><label className="search-field">Search funds<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by fund name" /></label><label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label><label>Risk<select value={risk} onChange={(event) => setRisk(event.target.value)}>{risks.map((item) => <option key={item}>{item}</option>)}</select></label><button className="primary-button" onClick={onCompare} disabled={selectedIds.length < 2}>Compare {selectedIds.length} funds</button></div><section className="rating-definition"><div><p className="eyebrow">AVAILABLE FUND METRICS</p><h3>Compare data without browser-generated values</h3><p>Returns and risk-adjusted ratings appear only when the connected fund source supplies them.</p></div></section><div className="scanner-result-summary"><span>{visibleFunds.length} configured funds match this screen</span><span>Choose 2–5 funds to compare</span></div><div className="table-shell"><table className="scanner-table"><thead><tr><th>Fund</th><th>Category</th><th>Risk</th><th>3Y return</th><th>Risk-adjusted return</th><th>Expense ratio</th><th>Fund size</th><th>Compare</th></tr></thead><tbody>{loading ? <tr><td colSpan={8}>Loading fund records…</td></tr> : error ? <tr><td colSpan={8}>{error}</td></tr> : visibleFunds.map((fund) => <tr key={fund.fund_id}><td><strong>{fund.fund_name}</strong></td><td><span className="fund-category">{valueOrUnavailable(fund.category)}</span></td><td>{valueOrUnavailable(fund.risk_level)}</td><td className="positive-value">{valueOrUnavailable(fund.return_3y, "%")}</td><td><StarRating score={fund.risk_adjusted_rating} /></td><td>{valueOrUnavailable(fund.expense_ratio, "%")}</td><td>{valueOrUnavailable(fund.fund_size)}</td><td><label className="compare-check"><input type="checkbox" checked={selectedIds.includes(fund.fund_id)} onChange={() => onToggle(fund.fund_id)} disabled={!selectedIds.includes(fund.fund_id) && selectedIds.length === 5} /><span className="sr-only">Compare {fund.fund_name}</span></label></td></tr>)}</tbody></table></div></>;
}

function Compare({ fundIds, onToggle, onScan }: { fundIds: string[]; onToggle: (id: string) => void; onScan: () => void }) {
  const [funds, setFunds] = useState<Fund[]>([]); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  useEffect(() => { let active = true; if (fundIds.length < 2) { setFunds([]); return () => { active = false; }; } setLoading(true); setError(""); apiRequest<ApiEnvelope<{ funds: Fund[] }>>("/funds/compare/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fund_ids: fundIds }) }).then((response) => { if (active) setFunds(response.data.funds); }).catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "Unable to compare funds."); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [fundIds]);
  if (fundIds.length < 2) return <section className="empty-state compact"><p className="eyebrow">COMPARE FUNDS</p><h2>Select 2–5 funds to compare</h2><p>Choose funds from the scanner to compare the backend-provided fields side by side.</p><button className="primary-button" onClick={onScan}>Open fund scanner</button></section>;
  const rows: { label: string; value: (fund: Fund) => ReactNode }[] = [{ label: "Category", value: (fund) => valueOrUnavailable(fund.category) }, { label: "Risk level", value: (fund) => valueOrUnavailable(fund.risk_level) }, { label: "3Y return", value: (fund) => valueOrUnavailable(fund.return_3y, "%") }, { label: "Risk-adjusted return", value: (fund) => <StarRating score={fund.risk_adjusted_rating} /> }, { label: "Expense ratio", value: (fund) => valueOrUnavailable(fund.expense_ratio, "%") }, { label: "Fund size", value: (fund) => valueOrUnavailable(fund.fund_size) }, { label: "Manager", value: (fund) => valueOrUnavailable(fund.manager_name) }, { label: "As of", value: (fund) => valueOrUnavailable(fund.as_of) }];
  return <>{error && <section className="empty-state compact"><strong>{error}</strong></section>}{loading ? <section className="empty-state compact">Loading comparison…</section> : funds.length > 0 && <div className="comparison-wrap"><table className="comparison-table"><thead><tr><th>Fund metric</th>{funds.map((fund) => <th key={fund.fund_id}><span className="fund-category">{valueOrUnavailable(fund.category)}</span><strong>{fund.fund_name}</strong><button className="remove-fund" onClick={() => onToggle(fund.fund_id)}>Remove</button></th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.label}><th>{row.label}</th>{funds.map((fund) => <td key={fund.fund_id}>{row.value(fund)}</td>)}</tr>)}</tbody></table></div>}</>;
}

function Commentary() {
  return <section className="commentary-research"><div><p className="eyebrow">MANAGER COMMENTARY</p><h2>Research notes with source context</h2><p>Commentary is shown only when it can be connected to the relevant fund, publication date and original supporting document.</p></div><details open><summary>Commentary awaiting source data</summary><div className="commentary-grid"><span>Fund <b>Awaiting data</b></span><span>Date <b>Awaiting data</b></span><span>Source <b>Awaiting data</b></span><span>Supporting document <b>Awaiting data</b></span></div><p>No manager commentary is available from the connected data source yet. When it is, this section will present concise key observations and retain the original source for review.</p></details></section>;
}

function OverlapView({ userId, onImport }: { userId: string; onImport: () => void }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, loading, error } = useApi<Overlap>(userId.trim() ? `/portfolio/overlap/?user_id=${encodeURIComponent(userId.trim())}&refresh=${refreshKey}` : null);
  const unavailable = Boolean(error);
  const overlapPercent = (data?.overall_overlap_percent ?? 0).toFixed(2);
  const status = loading ? "Loading" : unavailable ? "Unavailable" : `${overlapPercent}% shared`;
  return <div className="view-stack"><ViewHeading eyebrow="PORTFOLIO DIVERSIFICATION" title="Understand where your funds meet" description="Company-level overlap explains whether multiple funds truly diversify your portfolio." />
    <section className="explanation-panel"><span className={unavailable ? "risk-ring unavailable" : "risk-ring"}>{loading ? "…" : unavailable ? "—" : `${overlapPercent}%`}</span><div><h3>{unavailable ? "Overlap needs verified fund holdings" : "Shared-company exposure"}</h3><p>{unavailable ? "Your statement was imported successfully, but company-level overlap requires each fund to be matched with a verified holdings disclosure." : "This is the portion of your portfolio routed to companies held through two or more funds. It is an exposure measure, not a fund-similarity score."}</p></div></section>
    <section className="overlap-data-shell" aria-label="Portfolio overlap results"><div className="overlap-data-heading"><div><p className="eyebrow">COMPANY-LEVEL BREAKDOWN</p><h3>Top shared companies</h3><p>{unavailable ? "Overlap cannot be calculated from statement totals alone." : "Each result combines your weighted exposure to the same company across multiple funds."}</p></div><span>{status}</span></div>{unavailable ? <div className="overlap-unavailable"><strong>Company overlap is unavailable for this imported statement.</strong><p>{error}</p><span>Portfolio summary, holdings, allocation, and snapshot comparison still work from your imported CSV/XLSX data.</span><button className="outline-button" type="button" onClick={onImport}>View imported holdings</button></div> : <div className="table-shell"><table className="overlap-table"><thead><tr><th>Company</th><th>Funds holding it</th><th>Your shared exposure</th></tr></thead><tbody>{loading ? <tr><td colSpan={3}>Loading overlap results…</td></tr> : data?.companies.length ? data.companies.map((company) => <tr key={company.company}><td className="overlap-company"><strong>{company.company}</strong><small>{company.funds.length} funds</small></td><td><div className="overlap-fund-tags">{company.funds.map((fund) => <span key={fund.fund_name} title={`${fund.fund_name}${fund.portfolio_contribution_percent != null ? ` · ${fund.portfolio_contribution_percent.toFixed(2)}% of your portfolio` : ""}`}>{fund.fund_name}</span>)}</div></td><td className="overlap-exposure"><strong>{company.combined_exposure_percent.toFixed(2)}%</strong><small>of your portfolio</small></td></tr>) : <tr><td colSpan={3}><div className="table-empty"><strong>No shared-company exposure found</strong><span>No company is currently held in more than one fund for this portfolio.</span></div></td></tr>}</tbody></table></div>}</section>
    <FundDisclosureUploadPanel onImported={() => setRefreshKey((current) => current + 1)} />
  </div>;
}

function FundDisclosureUploadPanel({ onImported }: { onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [disclosureDate, setDisclosureDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [sourceName, setSourceName] = useState("Official fund disclosure");
  const [sourceUrl, setSourceUrl] = useState("");
  const [result, setResult] = useState<FundDisclosureImportResult | null>(null);
  const [error, setError] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  async function uploadDisclosure() {
    if (!file) return;
    setIsUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("disclosure_date", disclosureDate);
      form.append("source_name", sourceName.trim() || "Manual disclosure upload");
      if (sourceUrl.trim()) form.append("source_url", sourceUrl.trim());
      const response = await apiRequest<ApiEnvelope<FundDisclosureImportResult>>("/portfolio/disclosures/import/", { method: "POST", body: form });
      setResult(response.data);
      onImported();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to import this disclosure file.");
    } finally {
      setIsUploading(false);
    }
  }

  return <section className="disclosure-upload"><div><p className="eyebrow">FUND DISCLOSURE DATA</p><h3>Upload company holdings for overlap</h3><p>For the demo, upload one normalized CSV/XLSX containing company holdings for every fund in the active portfolio. This is separate from a user’s portfolio statement.</p><small>Required: <code>fund_name</code>, <code>company_name</code>, <code>holding_weight</code>. Optional: <code>isin</code>, <code>sector</code>. The fund name must match the portfolio statement.</small></div><div className="disclosure-controls"><label>Disclosure date<input type="date" value={disclosureDate} onChange={(event) => setDisclosureDate(event.target.value)} /></label><label>Source name<input value={sourceName} onChange={(event) => setSourceName(event.target.value)} placeholder="AMC / AMFI disclosure" /></label><label>Source URL <input type="url" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://…" /></label><label className="outline-button file-choice"><input type="file" accept=".csv,.xlsx" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setResult(null); setError(""); }} />Choose disclosure file</label>{file && <button className="primary-button" type="button" onClick={uploadDisclosure} disabled={isUploading}>{isUploading ? "Importing…" : "Import disclosure"}</button>}</div>{file && <div className="disclosure-file"><strong>{file.name}</strong>{result ? <span>Imported {result.holding_count} company holdings dated {result.disclosure_date}.</span> : <span>Ready to validate company weights and fund-name matches.</span>}{error && <p className="form-error">{error}</p>}</div>}</section>;
}

function CalculatorsView({ tab, onTab, onExplore }: { tab: CalculatorTab; onTab: (tab: CalculatorTab) => void; onExplore: () => void }) {
  return <div className="view-stack"><ViewHeading eyebrow="CALCULATORS" title="Plan with transparent assumptions" description="Calculations are estimates. They help you explore possibilities, not predict or guarantee outcomes." />
    <div className="segmented" role="tablist" aria-label="Calculators"><TabButton active={tab === "sip"} onClick={() => onTab("sip")}>SIP calculator</TabButton><TabButton active={tab === "wealth"} onClick={() => onTab("wealth")}>Expected wealth</TabButton><TabButton active={tab === "rolling"} onClick={() => onTab("rolling")}>Rolling returns</TabButton></div>
    {tab === "sip" && <SipCalculator />}{tab === "wealth" && <WealthCalculator />}{tab === "rolling" && <RollingReturns onExplore={onExplore} />}
  </div>;
}

function SipCalculator() {
  const [monthlySip, setMonthlySip] = useState(15000); const [years, setYears] = useState(10); const [annualReturn, setAnnualReturn] = useState(12);
  const [result, setResult] = useState<CalculatorResult | null>(null); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  async function calculate() { setLoading(true); setError(""); try { const response = await apiRequest<ApiEnvelope<CalculatorResult>>("/calculators/sip/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ monthly_investment: monthlySip, expected_annual_return: annualReturn, duration_years: years }) }); setResult(response.data); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to calculate SIP projection."); } finally { setLoading(false); } }
  return <CalculatorLayout onCalculate={calculate} loading={loading} error={error} result={result} inputs={<><NumberInput label="Monthly investment" value={monthlySip} setValue={setMonthlySip} suffix="₹ per month" step={500} /><NumberInput label="Expected annual return" value={annualReturn} setValue={setAnnualReturn} suffix="% per year" step={0.5} /><NumberInput label="Investment duration" value={years} setValue={setYears} suffix="years" min={1} /></>} />;
}

function WealthCalculator() {
  const [initial, setInitial] = useState(100000); const [additional, setAdditional] = useState(10000); const [frequency, setFrequency] = useState("monthly"); const [years, setYears] = useState(10); const [annualReturn, setAnnualReturn] = useState(12);
  const [result, setResult] = useState<CalculatorResult | null>(null); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  async function calculate() { setLoading(true); setError(""); try { const response = await apiRequest<ApiEnvelope<CalculatorResult>>("/calculators/expected-wealth/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ initial_investment: initial, additional_investment: additional, frequency, expected_annual_return: annualReturn, duration_years: years }) }); setResult(response.data); } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Unable to calculate wealth projection."); } finally { setLoading(false); } }
  return <CalculatorLayout onCalculate={calculate} loading={loading} error={error} result={result} inputs={<><NumberInput label="Initial investment" value={initial} setValue={setInitial} suffix="₹ once" step={1000} /><NumberInput label="Additional contribution" value={additional} setValue={setAdditional} suffix={`₹ ${frequency}`} step={500} /><ChoiceInput label="Contribution frequency" value={frequency} setValue={setFrequency} options={[{ value: "monthly", label: "Monthly" }, { value: "yearly", label: "Yearly" }]} /><NumberInput label="Expected annual return" value={annualReturn} setValue={setAnnualReturn} suffix="% per year" step={0.5} /><NumberInput label="Investment duration" value={years} setValue={setYears} suffix="years" min={1} /></>} />;
}

function CalculatorLayout({ inputs, onCalculate, loading, error, result }: { inputs: ReactNode; onCalculate: () => void; loading: boolean; error: string; result: CalculatorResult | null }) {
  const contributions = result?.total_invested ?? result?.total_contribution;
  const growth = result?.estimated_returns ?? result?.estimated_growth;
  return <section className="planner-layout"><div className="panel planner-controls"><div className="planner-intro"><span className="planner-icon"><Icon name="calculator" size={17} /></span><div><strong>Set your assumptions</strong><small>Change an input, then calculate a new estimate.</small></div></div>{inputs}<button type="button" className="primary-button calculator-submit" onClick={onCalculate} disabled={loading}>{loading ? "Calculating…" : "Calculate estimate"}</button>{error && <small className="form-error">{error}</small>}<small className="calculator-note">Calculated by the Django API. Nothing is projected in the browser.</small></div><div className={`wealth-card${result ? "" : " calculation-awaiting"}`}><div className="wealth-card-heading"><div><p className="eyebrow">PROJECTION</p><p className="wealth-label">Expected wealth</p></div><span className="estimate-badge">Estimate</span></div><h2>{result ? money(result.expected_wealth) : "—"}</h2><ProjectionChart projection={result?.yearly_projection} /><div className="wealth-metrics"><span><small>Total contributions</small><strong>{money(contributions)}</strong></span><span><small>Estimated growth</small><strong>{money(growth)}</strong></span><span><small>Projected value</small><strong>{money(result?.expected_wealth)}</strong></span></div>{result?.assumptions && <ul className="projection-assumptions">{result.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>}<small className="wealth-disclaimer">{result?.disclaimer ?? "Calculate to see an API-backed estimate and its assumptions."}</small></div></section>;
}

function ProjectionChart({ projection }: { projection?: CalculatorResult["yearly_projection"] }) {
  if (!projection?.length) return <div className="projection-chart projection-chart-empty"><span>Start</span><div>Calculate to view your API-backed projection</div><span>Goal</span></div>;
  const width = 520;
  const height = 130;
  const paddingX = 10;
  const paddingY = 13;
  const values = [0, ...projection.map((point) => point.expected_wealth)];
  const maximum = Math.max(...values, 1);
  const points = values.map((value, index) => {
    const x = paddingX + (index / (values.length - 1)) * (width - paddingX * 2);
    const y = height - paddingY - (value / maximum) * (height - paddingY * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const area = `M ${paddingX},${height - paddingY} L ${points.join(" L ")} L ${width - paddingX},${height - paddingY} Z`;
  const finalYear = projection[projection.length - 1].year;
  return <div className="projection-chart" aria-label={`Estimated wealth projection over ${finalYear} years`}><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-hidden="true"><defs><linearGradient id="projection-fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#b8dc92" stopOpacity=".45" /><stop offset="100%" stopColor="#b8dc92" stopOpacity="0" /></linearGradient></defs><path className="projection-gridline" d={`M ${paddingX} ${height - paddingY} H ${width - paddingX}`} /><path d={area} fill="url(#projection-fill)" /><polyline points={points.join(" ")} fill="none" stroke="#c9ea9e" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><circle cx={width - paddingX} cy={Number(points[points.length - 1].split(",")[1])} r="4" fill="#f3ffe6" stroke="#b8dc92" strokeWidth="3" /></svg><div className="projection-axis"><span>Today</span><span>Year {finalYear}</span></div></div>;
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

function MarketQuoteCards({ overview, loading, error }: { overview: MarketOverview | null; loading: boolean; error: string }) {
  if (loading) return <section className="market-cards" aria-label="Latest available Indian equity quotes"><div className="market-placeholder"><strong>Loading latest available quotes…</strong></div></section>;
  if (!overview?.configured) return <section className="market-placeholder"><p className="eyebrow">PRICE FEED</p><h3>Connect Twelve Data to load quotes</h3><p>{error || "Add TWELVE_DATA_API_KEY to backend/.env, then restart Django. No key is stored in the frontend."}</p></section>;
  return <section className="market-cards" aria-label="Latest available Indian equity quotes">
    {overview.items.map((quote) => <article className="market-index-card" key={quote.company_id}><p>{quote.name}</p><h3>{money(quote.price)}</h3><span>{quote.symbol} · {quote.exchange}</span><div className={quote.change_percent != null && quote.change_percent < 0 ? "quote-change negative" : "quote-change"}>{quote.change_percent == null ? "Change unavailable" : `${quote.change_percent >= 0 ? "+" : ""}${quote.change_percent.toFixed(2)}%`}<small>{quote.source ?? "Market-data provider"} · {quote.as_of ?? "timestamp unavailable"}</small></div></article>)}
    {overview.unavailable.map((company) => <article className="market-index-card unavailable" key={company.company_id}><p>{company.name}</p><h3>Not available</h3><span>Provider access unavailable</span><div className="quote-change"><small>{company.message}</small></div></article>)}
  </section>;
}

function MarketView({ userId }: { userId: string }) {
  const [tab, setTab] = useState<MarketTab>("india");
  const [symbol, setSymbol] = useState("C001");
  const [refresh, setRefresh] = useState(0);
  const [actionError, setActionError] = useState("");
  const userQuery = encodeURIComponent(userId.trim());
  const watchlist = useApi<{ items: WatchlistItem[] }>(userId.trim() ? `/watchlist/?user_id=${userQuery}&refresh=${refresh}` : null);
  const company = useApi<CompanyExposure>(userId.trim() ? `/companies/${symbol}/fund-exposure/?user_id=${userQuery}` : null);
  const marketOverview = useApi<MarketOverview>("/market/overview/");
  const marketConnected = Boolean(marketOverview.data?.configured && marketOverview.data.items.length);
  async function addToWatchlist() { setActionError(""); try { await apiRequest<ApiEnvelope<{ id: number }>>("/watchlist/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: userId.trim(), symbol }) }); setRefresh((value) => value + 1); } catch (requestError) { setActionError(requestError instanceof Error ? requestError.message : "Unable to add this company to the watchlist."); } }
  async function removeFromWatchlist(itemId: number) { setActionError(""); try { await apiRequest<unknown>(`/watchlist/${itemId}/?user_id=${userQuery}`, { method: "DELETE" }); setRefresh((value) => value + 1); } catch (requestError) { setActionError(requestError instanceof Error ? requestError.message : "Unable to remove this watchlist item."); } }
  return <div className="view-stack"><ViewHeading eyebrow="MARKET" title="A focused market view" description="Market context should complement mutual-fund research, not turn this product into a trading app." />
    <div className="segmented" role="tablist" aria-label="Market regions"><TabButton active={tab === "india"} onClick={() => setTab("india")}>India</TabButton><TabButton active={tab === "us"} onClick={() => setTab("us")}>US</TabButton><TabButton active={tab === "europe"} onClick={() => setTab("europe")}>Europe</TabButton><TabButton active={tab === "currencies"} onClick={() => setTab("currencies")}>Currencies</TabButton><TabButton active={tab === "crypto"} onClick={() => setTab("crypto")}>Crypto</TabButton><TabButton active={tab === "futures"} onClick={() => setTab("futures")}>Futures</TabButton></div>
    <section className="market-search"><label>Configured NSE equities<input placeholder="Quote search will be added with a symbol-search endpoint" disabled /></label><span>{marketOverview.loading ? "Connecting to price feed…" : marketConnected ? `${marketOverview.data?.items.length ?? 0} of 5 configured quotes available` : "Price feed not configured"}</span></section>
    {tab === "india" ? <MarketQuoteCards overview={marketOverview.data} loading={marketOverview.loading} error={marketOverview.error} /> : <section className="market-placeholder"><p className="eyebrow">{tab.toUpperCase()} MARKET OVERVIEW</p><h3>Market data unavailable</h3><p>This region will appear only when a supported provider is connected for that region.</p></section>}
    <section className="market-summary"><div className="market-summary-copy"><p className="eyebrow">QUOTE DATA</p><h3>{marketConnected ? "Price source and timing" : "Price feed unavailable"}</h3><p>{marketConnected ? "Use these values to understand your portfolio context, not to trade. Each quote card identifies its provider and the most recent timestamp or delay." : "Price cards will appear when a market-data provider returns a quote."}</p></div><div className="market-provider-meta"><span className="market-status-pill">{marketConnected ? "Latest available" : "Unavailable"}</span><small>{marketOverview.data?.provider ?? "Awaiting market data"}</small><small>{marketOverview.data?.data_mode ?? "—"}</small></div></section>
    <section className="market-watchlist"><div className="watchlist-heading"><div><p className="eyebrow">WATCHLIST</p><h3>Track companies you want to revisit</h3></div><div className="button-row"><label className="sr-only" htmlFor="watchlist-company">Company</label><select id="watchlist-company" value={symbol} onChange={(event) => setSymbol(event.target.value)}><option value="C001">HDFC Bank</option><option value="C002">Reliance Industries</option><option value="C003">Infosys</option><option value="C004">ICICI Bank</option><option value="C005">Larsen & Toubro</option></select><button className="outline-button" onClick={addToWatchlist} disabled={!userId.trim()}>Add to watchlist</button></div></div>{actionError && <p className="form-error">{actionError}</p>}{watchlist.loading ? <div className="watchlist-state">Loading watchlist…</div> : watchlist.error ? <div className="watchlist-state error">{watchlist.error}</div> : watchlist.data?.items.length ? <div className="table-shell"><table className="watchlist-table"><thead><tr><th>Company or security</th><th>Price</th><th>Change</th><th>As of</th><th /></tr></thead><tbody>{watchlist.data.items.map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small className="table-caption">{item.data_mode ?? "Price feed unavailable"}</small></td><td>{item.price == null ? "Not available" : money(item.price)}</td><td className={item.change_percent != null && item.change_percent < 0 ? "negative-value" : "positive-value"}>{item.change_percent == null ? "Not available" : `${item.change_percent >= 0 ? "+" : ""}${item.change_percent.toFixed(2)}%`}</td><td>{valueOrUnavailable(item.as_of)}</td><td><button className="remove-fund" onClick={() => removeFromWatchlist(item.id)}>Remove</button></td></tr>)}</tbody></table></div> : <div className="watchlist-empty"><div><p className="eyebrow">NO SAVED COMPANIES</p><h3>Build a short watchlist</h3><p>Save a company to keep its latest available quote close to your portfolio research.</p></div><button className="primary-button" onClick={addToWatchlist} disabled={!userId.trim()}>Track {company.data?.company.name ?? "selected company"}</button></div>}</section>
    <section className="company-flow"><div className="company-flow-intro"><p className="eyebrow">DISCLOSED PORTFOLIO EXPOSURE</p><h3>Where {company.data?.company.name ?? "this company"} appears in your funds</h3><p>This calculation uses your active statement and uploaded fund disclosures. It is separate from the market-price cards above.</p><div className="company-selected"><span>Selected company</span><strong>{company.data?.company.name ?? "Loading company…"}</strong></div></div><div className="company-exposure-result">{company.loading ? <strong>Loading disclosed exposure…</strong> : company.error ? <strong>{company.error}</strong> : <><div className="company-exposure-header"><div><span>YOUR LOOK-THROUGH EXPOSURE</span><strong>{company.data?.user_portfolio_exposure_percent?.toFixed(2)}%</strong><small>Across {company.data?.funds_holding_company.length ?? 0} fund{company.data?.funds_holding_company.length === 1 ? "" : "s"}</small></div><span className="evidence-chip">Disclosure backed</span></div>{company.data?.funds_holding_company.length ? <div className="company-exposure-funds">{company.data.funds_holding_company.map((fund) => <article key={fund.fund_id}><b>{fund.fund_name}</b><small>{fund.fund_exposure_percent}% inside fund</small><strong>{fund.portfolio_contribution_percent}% <span>of portfolio</span></strong></article>)}</div> : <p>This company is not held in the uploaded disclosures for your active portfolio.</p>}<div className="company-source-meta"><span>{company.data?.source_names?.join(", ") ?? "Disclosure source unavailable"}</span><span>As of {company.data?.data_as_of ?? "—"}</span><span>{company.data?.company.sector ?? "Sector unavailable"}</span></div></>}</div></section>
  </div>;
}

function ViewHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <div className="view-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2><p>{description}</p></div></div>;
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return <button role="tab" aria-selected={active} className={active ? "tab-button active" : "tab-button"} onClick={onClick}>{children}</button>;
}

createRoot(document.getElementById("root")!).render(<App />);
