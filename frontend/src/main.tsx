import { useEffect, useMemo, useState } from "react";
import type { ChangeEvent, FormEvent, ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Page = "assistant" | "portfolio" | "explorer" | "overlap" | "calculators" | "market";
type AssistantMode = "chat" | "documents";
type ExplorerTab = "discover" | "compare";
type CalculatorTab = "sip" | "wealth" | "rolling";
type PortfolioTab = "overview" | "holdings" | "allocation" | "changes";
type MarketTab = "india" | "us" | "europe" | "currencies" | "crypto" | "futures";
type Message = { role: "user" | "assistant"; content: string; sources?: Source[]; trace?: ToolTrace[]; evidence?: RagEvidenceChunk[]; answerMethod?: string; confidence?: number; usage?: RagUsage[] };
type Source = { name?: string; document?: string; page?: number; labels?: string[]; url?: string | null; data_as_of?: string | null };
type ToolTrace = { activity: string; success: boolean };
type ChatResponse = { success: boolean; answer: string; error_code?: string; sources?: Source[]; tool_trace?: ToolTrace[]; retrieved_chunks?: RagEvidenceChunk[]; answer_method?: string; usage?: RagUsage[]; conversation_id?: string };
type RagEvidenceChunk = { text: string; document?: string | null; page?: number | null; score?: number | null; fund_name?: string | null; document_type?: string | null; published_date?: string | null; visual_fallback?: boolean };
type RagUsage = { role: "answer" | "vision"; model: string; requests: number; input_tokens: number; output_tokens: number; input_reports: number; output_reports: number; estimated_cost: string };
type RagResponse = { success: boolean; answer: string; error_code?: string | null; confidence: number; fund_name?: string | null; answer_method: string; sources: Source[]; retrieved_chunks: RagEvidenceChunk[]; usage: RagUsage[] };
type RagJobAccepted = { job_id: string; status: "queued"; poll_url: string };
type RagJobStatus = { job_id: string; status: "queued" | "running" | "completed" | "failed"; poll_url: string; result?: RagResponse | null };
type ApiEnvelope<T> = { success: boolean; data: T; sources: Source[]; message?: string | null; error_code?: string };
type Account = { user_id: string; email: string; first_name: string; last_name: string; is_staff: boolean };
type AccountEnvelope = { success: boolean; data: Account; message?: string | null };
type PortfolioSummary = { total_invested: number; current_value: number; change: number; change_percent: number; fund_count: number; company_count: number | null; as_of?: string | null };
type Holding = { fund_id: string; fund_name: string; category?: string | null; units: number; invested_amount: number; current_value: number; allocation_percent: number };
type AllocationItem = { name: string; value: number; percentage: number; funds: string[] };
type Allocation = { group_by: string; items: AllocationItem[]; as_of?: string | null };
type Overlap = { overall_overlap_percent: number; explanation: string; companies: { company: string; combined_exposure_percent: number; funds: { fund_name: string; fund_holding_percent?: number; portfolio_contribution_percent?: number }[] }[] };
type MutualFundScheme = { scheme_code: number; scheme_name: string };
type FundSchemeSearchData = { query: string; schemes: MutualFundScheme[] };
type FundNavOverviewData = { scheme_code: number; latest_nav: number; nav_date: string; total_observations: number; returns: { years: number; cagr_percent: number | null; start_date: string | null; end_date: string | null }[] };
type FundNavCompareData = { years: number; funds: { scheme_code: number; cagr_percent: number; annualized_volatility_percent: number; maximum_drawdown_percent: number; start_date?: string; end_date?: string }[] };
type CalculatorResult = { total_invested?: number; total_contribution?: number; estimated_returns?: number; estimated_growth?: number; expected_wealth: number; disclaimer: string; assumptions?: string[]; yearly_projection?: { year: number; total_invested: number; expected_wealth: number }[] };
type WatchlistItem = { id: number; symbol: string; name: string; price?: number | null; change_percent?: number | null; as_of?: string | null; provider?: string | null; data_mode?: string | null };
type MarketQuote = { company_id: string; name: string; symbol: string; exchange: string; currency: string; price: number; change_percent?: number | null; as_of?: string | null; source?: string; data_mode?: string };
type MarketOverview = { configured: boolean; provider: string; data_mode: string; items: MarketQuote[]; unavailable: { company_id: string; name: string; message: string }[] };
type CompanyExposure = { company: { company_id: string; name: string; sector: string }; funds_holding_company: { fund_id: string; fund_name: string; fund_exposure_percent: number; portfolio_contribution_percent?: number; in_user_portfolio: boolean }[]; user_portfolio_exposure_percent: number; data_as_of?: string | null; source_names?: string[] };
type ConversationSummary = { id: string; title: string; latest_message_preview: string; message_count: number; created_at: string; updated_at: string };
type ConversationList = { results: ConversationSummary[] };
type ConversationDetail = { id: string; created_at: string; updated_at: string; messages: { role: "user" | "assistant"; content: string; created_at: string; metadata?: { sources?: Source[]; tool_trace?: ToolTrace[]; retrieved_chunks?: RagEvidenceChunk[]; answer_method?: string; usage?: RagUsage[] } }[] };
type PortfolioImportResult = { import_id: number; holding_count: number; source_file_name: string; source_format: string; snapshot_date: string; is_active: boolean };
type FundDisclosureImportResult = { disclosure_import_id: number; holding_count: number; source_file_name: string; source_format: string; disclosure_date: string };
type PortfolioSnapshot = { id: number; snapshot_date: string; source_file_name: string; source_format: string; holding_count: number; is_active: boolean };
type PortfolioChangesData = { available: boolean; snapshots: PortfolioSnapshot[]; newer_snapshot?: { id: number; snapshot_date: string; source_file_name: string }; older_snapshot?: { id: number; snapshot_date: string; source_file_name: string }; changes: { change_type: "Added" | "Removed" | "Increased" | "Decreased"; fund_name: string; current_value_change: number; invested_amount_change: number; newer_current_value: number; older_current_value: number }[] };
type IconName = "assistant" | "portfolio" | "explorer" | "overlap" | "calculator" | "market" | "compare" | "search" | "settings" | "bell" | "send" | "attach" | "arrow" | "menu";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const ragPollTimeoutMs = 10 * 60 * 1000;

function cookieValue(name: string) {
  const entry = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${name}=`));
  return entry ? decodeURIComponent(entry.slice(name.length + 1)) : "";
}

async function apiFetch(path: string, init: RequestInit = {}) {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
    let csrfToken = cookieValue("csrftoken");
    if (!csrfToken) {
      const csrfResponse = await fetch(`${apiBaseUrl}/auth/csrf/`, { credentials: "same-origin" });
      const csrfPayload = await csrfResponse.json().catch(() => ({}));
      csrfToken = cookieValue("csrftoken") || csrfPayload?.data?.csrf_token || "";
    }
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }
  const apiRoot = apiBaseUrl.replace(/\/+$/, "");
  const url = /^https?:\/\//i.test(path) ? path : `${apiRoot}${path.startsWith("/") ? path : `/${path}`}`;
  return fetch(url, { ...init, headers, credentials: "same-origin" });
}

async function askFundLens(question: string, fundScope: string): Promise<RagResponse> {
  const createResponse = await apiFetch("/rag/jobs/", {
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
  const pollUrl = new URL(job.poll_url, window.location.origin).toString();
  while (Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 1200));
    const statusResponse = await apiFetch(pollUrl);
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

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    const detail = Array.isArray(payload.detail) ? payload.detail.map((item: { msg?: string }) => item.msg).join(" ") : payload.detail;
    const fieldError = Object.values(payload).find((value) => Array.isArray(value) && typeof value[0] === "string") as string[] | undefined;
    throw new Error(payload.message || payload.answer || detail || fieldError?.[0] || payload.error_code || "The request could not be completed.");
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
  const [explorerTab, setExplorerTab] = useState<ExplorerTab>("discover");
  const [calculatorTab, setCalculatorTab] = useState<CalculatorTab>("sip");
  const [portfolioTab, setPortfolioTab] = useState<PortfolioTab>("overview");
  const [quickSearch, setQuickSearch] = useState("");
  const [userId, setUserId] = useState("");
  const [account, setAccount] = useState<Account | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [profileOpen, setProfileOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [assistantMode, setAssistantMode] = useState<AssistantMode>("chat");
  const [fundScope, setFundScope] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationRefresh, setConversationRefresh] = useState(0);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [chatFiles, setChatFiles] = useState<File[]>([]);
  const [portfolioRefresh, setPortfolioRefresh] = useState(0);
  const [selectedSchemes, setSelectedSchemes] = useState<MutualFundScheme[]>([]);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const history = useApi<ConversationList>(userId.trim() ? `/chat/conversations/?refresh=${conversationRefresh}` : null);

  useEffect(() => {
    let active = true;
    apiRequest<AccountEnvelope>("/auth/profile/")
      .then((response) => {
        if (!active) return;
        setAccount(response.data);
        setUserId(response.data.user_id);
      })
      .catch(() => {
        if (active) {
          setAccount(null);
          setUserId("");
        }
      })
      .finally(() => { if (active) setAuthLoading(false); });
    return () => { active = false; };
  }, []);

  function onAuthenticated(nextAccount: Account) {
    setAccount(nextAccount);
    setUserId(nextAccount.user_id);
    setConversationId(null);
    setMessages([]);
    setConversationRefresh((value) => value + 1);
  }

  async function signOut() {
    try {
      await apiRequest("/auth/logout/", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    } catch {
      // Clear local state even if the server cannot be reached; the server-side
      // session still expires according to Django's configured session policy.
    } finally {
      setAccount(null);
      setUserId("");
      setProfileOpen(false);
      setMessages([]);
      setConversationId(null);
      setHistoryOpen(false);
    }
  }

  function openAssistant(prompt = "") {
    setPage("assistant");
    setDraft(prompt);
  }

  function askAboutFund(fundName: string) {
    setAssistantMode("chat");
    setFundScope("");
    openAssistant(`Research ${fundName}. Use MFapi.in for current or historical NAV and NAV-return questions, and use indexed factsheets for the scheme objective, benchmark, risk, fees, and holdings. Cite each source and say clearly when the indexed documents do not contain enough evidence.`);
  }

  function submitQuickSearch(event: FormEvent) {
    event.preventDefault();
    const prompt = quickSearch.trim();
    if (!prompt) return;
    openAssistant(prompt);
    setQuickSearch("");
  }

  function openExplorer(tab: ExplorerTab = "discover") {
    setPage("explorer");
    setExplorerTab(tab);
  }

  function openPortfolio(tab: PortfolioTab = "overview") {
    setPage("portfolio");
    setPortfolioTab(tab);
  }

  function toggleScheme(scheme: MutualFundScheme) {
    setSelectedSchemes((current) => current.some((item) => item.scheme_code === scheme.scheme_code)
      ? current.filter((item) => item.scheme_code !== scheme.scheme_code)
      : current.length === 5 ? current : [...current, scheme]);
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
      const conversation = await apiRequest<ConversationDetail>(`/chat/conversations/${id}/`);
      setConversationId(conversation.id);
      setMessages(conversation.messages.map((message) => ({
        role: message.role,
        content: message.content,
        sources: message.metadata?.sources,
        trace: message.metadata?.tool_trace,
        evidence: message.metadata?.retrieved_chunks,
        answerMethod: message.metadata?.answer_method,
        usage: message.metadata?.usage,
      })));
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
    if (!message || (assistantMode === "chat" && !userId.trim()) || isSending) return;
    const nextMessages = [...messages, { role: "user" as const, content: message }];
    setMessages(nextMessages);
    setDraft("");
    setError("");
    setIsSending(true);
    try {
      if (assistantMode === "documents") {
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
        // Keep the existing portfolio-chat API contract unchanged.
        const response = await apiFetch("/chat/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            ...(conversationId ? { conversation_id: conversationId } : {}),
          }),
        });
        const payload: ChatResponse = await response.json();
        if (!response.ok || !payload.success) {
          throw new Error(payload.answer || payload.error_code || "The assistant could not answer right now.");
        }
        setMessages([...nextMessages, { role: "assistant", content: payload.answer, sources: payload.sources, trace: payload.tool_trace, evidence: payload.retrieved_chunks, answerMethod: payload.answer_method, usage: payload.usage }]);
        setConversationId(payload.conversation_id ?? conversationId);
        setConversationRefresh((current) => current + 1);
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
    link.download = "mutual-fund-analysis.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  if (authLoading) return <main className="auth-page"><p>Loading your account…</p></main>;
  if (!account) return <AuthScreen onAuthenticated={onAuthenticated} />;

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to main content</a>
    {mobileMenuOpen && <button className="mobile-nav-backdrop" aria-label="Close navigation" onClick={() => setMobileMenuOpen(false)} />}
    <aside className={mobileMenuOpen ? "sidebar mobile-open" : "sidebar"}>
      <div className="brand"><span>M</span><div><strong>MF Portfolio Agent</strong><small>Mutual Fund Intelligence</small></div></div>
      <p className="workspace-label">WORKSPACE</p>
      <nav aria-label="Main navigation">
        {navigation.map((item) => <button key={item.id} className={page === item.id ? "nav-item active" : "nav-item"} onClick={() => item.id === "explorer" ? openExplorer("discover") : setPage(item.id)}><b><Icon name={item.icon} /></b>{item.label}</button>)}
        <button className={page === "explorer" && explorerTab === "compare" ? "nav-item active" : "nav-item"} onClick={() => openExplorer("compare")}><b><Icon name="compare" /></b>Compare funds</button>
      </nav>
      <div className="sidebar-section"><div className="sidebar-section-heading"><span>PORTFOLIO</span><button aria-label="Add portfolio">+</button></div><button className="sidebar-link" onClick={() => openPortfolio("holdings")}>Holdings</button><button className="sidebar-link" onClick={() => openPortfolio("allocation")}>Allocation & exposure</button><button className="sidebar-link" onClick={() => openPortfolio("changes")}>Changes</button><button className="sidebar-link" onClick={() => openPortfolio("overview")}>Import holdings <span>→</span></button></div>
      <div className="sidebar-section"><div className="sidebar-section-heading"><span>RESEARCH</span></div><button className="sidebar-link" onClick={() => openExplorer("discover")}>Fund explorer</button></div>
      <div className="sidebar-section"><div className="sidebar-section-heading"><span>MARKET</span></div><button className="sidebar-link" onClick={() => setPage("market")}>Market overview</button><button className="sidebar-link" onClick={() => setPage("market")}>Watchlist</button></div>
      <div className="sidebar-footer"><span className="status-dot" /> Research workspace <small>Evidence-led analysis</small></div>
    </aside>

    <section className="workspace">
      <header className="topbar">
        <div className="topbar-brand"><strong>MF Portfolio Agent</strong><small>Mutual Fund Intelligence</small></div>
        <form className="universal-search" onSubmit={submitQuickSearch}><Icon name="search" size={17} /><input value={quickSearch} onChange={(event) => setQuickSearch(event.target.value)} placeholder="Search funds, companies, or ask a question" aria-label="Ask anything or search" /><button type="submit">Search</button></form>
        <button className="mobile-menu-toggle" aria-label="Open navigation" onClick={() => setMobileMenuOpen(true)}><Icon name="menu" /></button>
        <div className="topbar-actions"><button className="icon-button" aria-label="Settings"><Icon name="settings" /></button><button className="icon-button" aria-label="Notifications"><Icon name="bell" /></button><button className="account-button" onClick={() => setProfileOpen(true)} aria-label="Open account profile"><span className="avatar">{`${account.first_name[0] ?? ""}${account.last_name[0] ?? ""}`.toUpperCase() || "MF"}</span><span>{account.first_name || account.email}</span></button></div>
      </header>
      <main id="main-content" className={page === "assistant" ? "content" : "content app-content"} tabIndex={-1}>
        <div className="page-main">
          {page === "assistant" && <AssistantView userId={userId} messages={messages} conversationId={conversationId} history={history.data?.results ?? []} historyError={history.error} historyLoading={history.loading || historyLoading} historyOpen={historyOpen} draft={draft} setDraft={setDraft} files={chatFiles} error={error} isSending={isSending} assistantMode={assistantMode} setAssistantMode={setAssistantMode} fundScope={fundScope} setFundScope={setFundScope} onFiles={selectChatFiles} onSend={sendMessage} onExport={exportAnswer} onShortcut={openAssistant} onImport={() => openPortfolio("overview")} onNewConversation={startNewConversation} onOpenConversation={reopenConversation} onToggleHistory={() => setHistoryOpen((open) => !open)} />}
          {page === "portfolio" && <PortfolioView userId={userId} tab={portfolioTab} onTab={setPortfolioTab} refreshKey={portfolioRefresh} onImported={() => { setPortfolioRefresh((current) => current + 1); setSelectedSchemes([]); }} onAsk={openAssistant} />}
          {page === "explorer" && <ExplorerView tab={explorerTab} onTab={setExplorerTab} selectedSchemes={selectedSchemes} onToggle={toggleScheme} onAsk={askAboutFund} />}
          {page === "overlap" && <OverlapView userId={userId} canManageDisclosures={account.is_staff} onImport={() => setPage("portfolio")} />}
          {page === "calculators" && <CalculatorsView tab={calculatorTab} onTab={setCalculatorTab} onExplore={() => openExplorer("discover")} />}
          {page === "market" && <MarketView userId={userId} />}
        </div>
      </main>
    </section>
    {profileOpen && <ProfileDialog account={account} onClose={() => setProfileOpen(false)} onUpdated={(nextAccount) => { setAccount(nextAccount); setUserId(nextAccount.user_id); }} onSignOut={signOut} />}
  </div>;
}

function normalizeMarkdown(content: string) {
  return content.replace(/\r\n/g, "\n").replaceAll("\\|", "|");
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (account: Account) => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const path = mode === "signup" ? "/auth/signup/" : "/auth/login/";
      const payload = mode === "signup"
        ? { email, password, first_name: firstName, last_name: lastName }
        : { email, password };
      const response = await apiRequest<AccountEnvelope>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      onAuthenticated(response.data);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to authenticate right now.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="auth-page">
    <section className="auth-card" aria-labelledby="auth-title">
      <div className="auth-brand"><span>M</span><div><strong>MF Portfolio Agent</strong><small>Mutual Fund Intelligence</small></div></div>
      <p className="eyebrow">PRIVATE RESEARCH WORKSPACE</p>
      <h1 id="auth-title">{mode === "signup" ? "Create your account" : "Welcome back"}</h1>
      <p className="auth-intro">Your portfolio, saved chats, and watchlist stay tied to your account.</p>
      <div className="auth-tabs" role="tablist" aria-label="Account access">
        <button type="button" role="tab" aria-selected={mode === "login"} className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
        <button type="button" role="tab" aria-selected={mode === "signup"} className={mode === "signup" ? "active" : ""} onClick={() => { setMode("signup"); setError(""); }}>Create account</button>
      </div>
      <form className="auth-form" onSubmit={submit}>
        {mode === "signup" && <div className="auth-name-fields"><label>First name<input autoComplete="given-name" required value={firstName} onChange={(event) => setFirstName(event.target.value)} /></label><label>Last name <span>(optional)</span><input autoComplete="family-name" value={lastName} onChange={(event) => setLastName(event.target.value)} /></label></div>}
        <label>Email address<input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <label>Password<input type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} minLength={mode === "signup" ? 8 : undefined} required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {mode === "signup" && <small className="auth-hint">Use at least 8 characters. Choose a password that is not commonly used.</small>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="primary-button auth-submit" type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "signup" ? "Create account" : "Sign in"}</button>
      </form>
      <p className="auth-disclaimer">This is an early-access product. Do not upload information you are not comfortable storing in this workspace.</p>
    </section>
  </main>;
}

function ProfileDialog({ account, onClose, onUpdated, onSignOut }: { account: Account; onClose: () => void; onUpdated: (account: Account) => void; onSignOut: () => void }) {
  const [firstName, setFirstName] = useState(account.first_name);
  const [lastName, setLastName] = useState(account.last_name);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const response = await apiRequest<AccountEnvelope>("/auth/profile/", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_name: firstName, last_name: lastName }),
      });
      onUpdated(response.data);
      setSaved(true);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to update your profile.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="profile-dialog" role="dialog" aria-modal="true" aria-labelledby="profile-title">
      <div className="profile-dialog-heading"><div><p className="eyebrow">ACCOUNT</p><h2 id="profile-title">Your profile</h2></div><button type="button" className="dialog-close" onClick={onClose} aria-label="Close profile">×</button></div>
      <form className="auth-form" onSubmit={save}>
        <label>Email address<input type="email" value={account.email} readOnly /></label>
        <label>First name<input autoComplete="given-name" required value={firstName} onChange={(event) => setFirstName(event.target.value)} /></label>
        <label>Last name<input autoComplete="family-name" value={lastName} onChange={(event) => setLastName(event.target.value)} /></label>
        {error && <p className="form-error" role="alert">{error}</p>}
        {saved && <p className="profile-saved" role="status">Profile saved.</p>}
        <button className="primary-button auth-submit" type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
      </form>
      <div className="profile-dialog-footer"><span>Signed in as <strong>{account.email}</strong></span><button type="button" className="outline-button" onClick={onSignOut}>Sign out</button></div>
    </section>
  </div>;
}

function markdownTableToCsv(content: string) {
  const rows = normalizeMarkdown(content).split("\n").map((line) => line.trim()).filter((line) => /^\|?.+\|.+\|?$/.test(line) && !/^\|?\s*:?-{3,}/.test(line));
  if (rows.length < 2) return null;
  return rows.map((row) => row.replace(/^\||\|$/g, "").split("|").map((cell) => `"${cell.trim().replaceAll('"', '""')}"`).join(",")).join("\n");
}

function hasStructuredTable(content: string) {
  return Boolean(markdownTableToCsv(content));
}

function AssistantView({ userId, messages, conversationId, history, historyError, historyLoading, historyOpen, draft, setDraft, files, error, isSending, assistantMode, setAssistantMode, fundScope, setFundScope, onFiles, onSend, onExport, onShortcut, onImport, onNewConversation, onOpenConversation, onToggleHistory }: { userId: string; messages: Message[]; conversationId: string | null; history: ConversationSummary[]; historyError: string; historyLoading: boolean; historyOpen: boolean; draft: string; setDraft: (value: string) => void; files: File[]; error: string; isSending: boolean; assistantMode: AssistantMode; setAssistantMode: (mode: AssistantMode) => void; fundScope: string; setFundScope: (value: string) => void; onFiles: (event: ChangeEvent<HTMLInputElement>) => void; onSend: (event: FormEvent) => void; onExport: (message: Message) => void; onShortcut: (prompt: string) => void; onImport: () => void; onNewConversation: () => void; onOpenConversation: (id: string) => void; onToggleHistory: () => void }) {
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
        <ChatComposer draft={draft} setDraft={setDraft} files={files} isSending={isSending} assistantMode={assistantMode} setAssistantMode={setAssistantMode} fundScope={fundScope} setFundScope={setFundScope} onFiles={onFiles} onSend={onSend} home />
        <div className="prompt-grid" aria-label="Suggested research prompts">{prompts.map((item) => <button key={item.label} onClick={() => onShortcut(item.prompt)}><Icon name="arrow" size={15} />{item.label}</button>)}</div>
        <HomeSnapshots userId={userId} onImport={onImport} />
      </div> : <div className="conversation">{messages.map((item, index) => <ChatMessage key={`${item.role}-${index}`} message={item} onExport={onExport} />)}</div>}
      {isSending && <div className="message assistant loading"><div className="message-label">MF Portfolio Agent</div><p><span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" /> {assistantMode === "documents" ? "Searching indexed fund documents and preparing evidence" : "Reviewing your request"}</p></div>}
    </section>
    {messages.length > 0 && <ChatComposer draft={draft} setDraft={setDraft} files={files} isSending={isSending} assistantMode={assistantMode} setAssistantMode={setAssistantMode} fundScope={fundScope} setFundScope={setFundScope} onFiles={onFiles} onSend={onSend} />}
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
      {message.answerMethod && <div className="message-meta"><span>Answer method: {message.answerMethod.replaceAll("_", " ")}</span>{typeof message.confidence === "number" && <span>Confidence: {Math.round(message.confidence * 100)}%</span>}</div>}
      {message.sources?.length ? <div className="sources">{message.sources.map((source, index) => source.url ? <a key={`${source.document ?? source.name}-${source.page ?? index}`} href={source.url} target="_blank" rel="noreferrer">Source: {source.document ?? source.name ?? "Source"}{source.page ? ` · page ${source.page}` : ""}{source.labels?.length ? ` · ${source.labels.join(", ")}` : ""}{source.data_as_of ? ` · As of ${source.data_as_of}` : ""}</a> : <span key={`${source.document ?? source.name}-${source.page ?? index}`}>Source: {source.document ?? source.name ?? "Source"}{source.page ? ` · page ${source.page}` : ""}{source.labels?.length ? ` · ${source.labels.join(", ")}` : ""}{source.data_as_of ? ` · As of ${source.data_as_of}` : ""}</span>)}</div> : null}
      {exportable && <button className="text-action" onClick={() => onExport(message)}>Export CSV</button>}
    </>}
  </article>;
}

function HomeSnapshots({ userId, onImport }: { userId: string; onImport: () => void }) {
  const summary = useApi<PortfolioSummary>(userId.trim() ? "/portfolio/summary/" : null);
  return <section className="home-snapshots" aria-label="Portfolio and market snapshots"><article><p className="eyebrow">YOUR PORTFOLIO</p><h3>{summary.loading ? "Loading portfolio…" : summary.error ? "Portfolio unavailable" : money(summary.data?.current_value)}</h3><p>{summary.error ? summary.error : `${summary.data?.fund_count ?? 0} funds · invested ${money(summary.data?.total_invested)}`}</p><button className="text-action" type="button" onClick={onImport}>View portfolio</button></article><article><p className="eyebrow">MARKET</p><h3>Market data is currently unavailable</h3><p>India indices and a concise market summary will appear when a supported provider is connected.</p><div className="source-meta"><span>Source: —</span><span>As of: —</span></div></article></section>;
}

function PortfolioView({ userId, tab, onTab, refreshKey, onImported, onAsk }: { userId: string; tab: PortfolioTab; onTab: (tab: PortfolioTab) => void; refreshKey: number; onImported: () => void; onAsk: (prompt: string) => void }) {
  const summary = useApi<PortfolioSummary>(userId ? `/portfolio/summary/?refresh=${refreshKey}` : null);
  const holdings = useApi<{ results: Holding[]; total: number }>(userId ? `/portfolio/holdings/?refresh=${refreshKey}` : null);
  const allocation = useApi<Allocation>(userId ? `/portfolio/allocation/?group_by=category&refresh=${refreshKey}` : null);
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
      formData.append("file", file);
      if (asOfDate) formData.append("as_of_date", asOfDate);
      const response = await apiFetch("/portfolio/import/", { method: "POST", body: formData });
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

const portfolioChartPalette = ["#1d704f", "#4d8d67", "#c39342", "#4f7ea5", "#8b70a5", "#c27658"];

function chartPercent(value: number) {
  return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
}

function allocationDonutGradient(items: AllocationItem[]) {
  const values = items.map((item) => Math.max(0, Number.isFinite(item.percentage) ? item.percentage : 0));
  const total = values.reduce((sum, value) => sum + value, 0);
  if (total <= 0) return "conic-gradient(#e7ece8 0% 100%)";
  let start = 0;
  const segments = values.map((value, index) => {
    const end = start + (value / total) * 100;
    const segment = value > 0 ? `${portfolioChartPalette[index % portfolioChartPalette.length]} ${start.toFixed(2)}% ${end.toFixed(2)}%` : "";
    start = end;
    return segment;
  }).filter(Boolean);
  return `conic-gradient(${segments.join(", ")})`;
}

function PortfolioTable({ holdings, loading, error }: { holdings: Holding[]; loading: boolean; error: string }) {
  const [query, setQuery] = useState("");
  const rows = holdings.filter((holding) => holding.fund_name.toLowerCase().includes(query.toLowerCase()));
  const rankedHoldings = [...holdings].sort((left, right) => right.current_value - left.current_value);
  const largestHoldings = rankedHoldings.slice(0, 5);
  const otherHoldings = rankedHoldings.slice(5);
  const positionBars = [
    ...largestHoldings.map((holding) => ({ key: holding.fund_id, name: holding.fund_name, percentage: holding.allocation_percent })),
    ...(otherHoldings.length ? [{ key: "other-holdings", name: "Other holdings", percentage: otherHoldings.reduce((total, holding) => total + holding.allocation_percent, 0) }] : []),
  ];
  const largestWeight = Math.max(0, ...positionBars.map((item) => item.percentage));
  return <section className="holdings-panel"><div className="holdings-toolbar"><div><p className="eyebrow">FUND HOLDINGS</p><h3>{holdings.length} funds in this portfolio</h3></div><div className="table-tools"><label>Search holdings<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by fund" /></label></div></div>{!loading && !error && positionBars.length > 0 && <section className="holdings-insight-chart" aria-label="Largest portfolio positions"><div className="chart-card-heading"><div><p className="eyebrow">PORTFOLIO WEIGHT</p><h4>Where your portfolio is concentrated</h4><p>Largest positions by current value. Bar lengths are relative; labels show each position’s share.</p></div><span className="chart-period-label">Top {largestHoldings.length}{otherHoldings.length ? " + rest" : ""}</span></div><div className="position-chart-list" role="list">{positionBars.map((item, index) => <div className="position-chart-row" key={item.key} role="listitem"><span className="position-chart-name" title={item.name}>{item.name}</span><div className="position-chart-track" aria-hidden="true"><span style={{ width: `${chartPercent(largestWeight > 0 ? Math.max(0, item.percentage) / largestWeight * 100 : 0)}%`, backgroundColor: portfolioChartPalette[index % portfolioChartPalette.length] }} /></div><strong>{item.percentage.toFixed(1)}%</strong></div>)}</div></section>}<section className="table-shell"><table className="holdings-table"><thead><tr><th>Fund</th><th>Category</th><th>Units</th><th>Invested</th><th>Current value</th><th>Allocation</th></tr></thead><tbody>{loading ? <tr><td colSpan={6}>Loading holdings…</td></tr> : error ? <tr><td colSpan={6}>{error}</td></tr> : rows.length ? rows.map((holding) => <tr key={holding.fund_id}><td><strong>{holding.fund_name}</strong></td><td><span className="category-pill">{holding.category ?? "Not available"}</span></td><td className="numeric-cell">{new Intl.NumberFormat("en-IN", { maximumFractionDigits: 4 }).format(holding.units)}</td><td className="numeric-cell">{money(holding.invested_amount)}</td><td className="numeric-cell current-value">{money(holding.current_value)}</td><td className="numeric-cell"><span className="allocation-value">{holding.allocation_percent.toFixed(2)}%</span></td></tr>) : <tr><td colSpan={6}><div className="table-empty"><strong>No matching holdings</strong><span>Try a different fund name.</span></div></td></tr>}</tbody></table></section></section>;
}

function PortfolioAllocation({ allocation, loading, error }: { allocation: Allocation | null; loading: boolean; error: string }) {
  const items = allocation?.items ?? [];
  const chartItems = [...items].sort((left, right) => right.percentage - left.percentage);
  const totalValue = items.reduce((total, item) => total + item.value, 0);
  const chartLabel = chartItems.map((item) => `${item.name}: ${item.percentage}%`).join("; ");
  return <section className="sector-exposure"><div className="sector-heading"><div><p className="eyebrow">PORTFOLIO ALLOCATION</p><h3>See the categories behind your funds</h3><p>Allocation is calculated from the active portfolio snapshot. Company and sector exposure need verified fund-disclosure mappings.</p></div></div>{!loading && !error && items.length > 0 && <section className="allocation-visuals" aria-label="Portfolio allocation charts"><div className="allocation-donut-card"><div className="chart-card-heading"><div><p className="eyebrow">PORTFOLIO MIX</p><h4>Value by category</h4></div></div><div className="allocation-donut-wrap"><div className="allocation-donut" role="img" aria-label={`Portfolio allocation by category. ${chartLabel}`} style={{ background: allocationDonutGradient(items) }}><div className="allocation-donut-center"><strong>{items.length}</strong><span>categories</span></div></div><div className="allocation-total"><strong>{money(totalValue)}</strong><span>Current portfolio value</span></div></div></div><div className="allocation-breakdown-card"><div className="chart-card-heading"><div><p className="eyebrow">CATEGORY BREAKDOWN</p><h4>How each category contributes</h4></div></div><div className="allocation-breakdown-list" role="list">{chartItems.map((item, index) => <div className="allocation-breakdown-row" key={item.name} role="listitem"><div className="allocation-breakdown-heading"><span><i style={{ backgroundColor: portfolioChartPalette[index % portfolioChartPalette.length] }} />{item.name}</span><strong>{item.percentage.toFixed(1)}%</strong></div><div className="allocation-breakdown-track" aria-hidden="true"><span style={{ width: `${chartPercent(item.percentage)}%`, backgroundColor: portfolioChartPalette[index % portfolioChartPalette.length] }} /></div><small>{money(item.value)}</small></div>)}</div></div></section>}<div className="table-shell"><table className="sector-table"><thead><tr><th>Category</th><th>Value</th><th>Percentage</th><th>Underlying funds</th></tr></thead><tbody>{loading ? <tr><td colSpan={4}>Loading allocation…</td></tr> : error ? <tr><td colSpan={4}>{error}</td></tr> : allocation?.items.map((item) => <tr key={item.name}><td>{item.name}</td><td>{money(item.value)}</td><td>{item.percentage}%</td><td>{item.funds.length ? item.funds.join(", ") : "Not available"}</td></tr>)}</tbody></table></div></section>;
}

function PortfolioChanges({ userId, refreshKey, onAsk }: { userId: string; refreshKey: number; onAsk: (prompt: string) => void }) {
  const snapshots = useApi<{ results: PortfolioSnapshot[] }>(userId ? `/portfolio/snapshots/?refresh=${refreshKey}` : null);
  const [newerId, setNewerId] = useState("");
  const [olderId, setOlderId] = useState("");
  const availableSnapshots = snapshots.data?.results ?? [];
  useEffect(() => { if (availableSnapshots.length >= 2) { setNewerId((current) => availableSnapshots.some((item) => String(item.id) === current) ? current : String(availableSnapshots[0].id)); setOlderId((current) => availableSnapshots.some((item) => String(item.id) === current) && current !== String(availableSnapshots[0].id) ? current : String(availableSnapshots[1].id)); } }, [availableSnapshots]);
  const comparison = useApi<PortfolioChangesData>(newerId && olderId && newerId !== olderId ? `/portfolio/changes/?newer_snapshot_id=${newerId}&older_snapshot_id=${olderId}` : null);
  const formatSnapshot = (snapshot: PortfolioSnapshot) => `${snapshot.snapshot_date} · ${snapshot.source_file_name}`;
  return <><section className="changes-header"><div><p className="eyebrow">PORTFOLIO CHANGES</p><h3>Compare two portfolio snapshots</h3><p>Added, removed, increased, and decreased fund positions are calculated from your dated imported statements.</p></div><div className="snapshot-selectors"><label>Newer snapshot<select value={newerId} onChange={(event) => setNewerId(event.target.value)} disabled={availableSnapshots.length < 2}><option value="">Select snapshot</option>{availableSnapshots.map((snapshot) => <option key={snapshot.id} value={snapshot.id}>{formatSnapshot(snapshot)}</option>)}</select></label><label>Older snapshot<select value={olderId} onChange={(event) => setOlderId(event.target.value)} disabled={availableSnapshots.length < 2}><option value="">Select snapshot</option>{availableSnapshots.map((snapshot) => <option key={snapshot.id} value={snapshot.id}>{formatSnapshot(snapshot)}</option>)}</select></label></div></section>{snapshots.loading ? <section className="changes-empty">Loading snapshots…</section> : snapshots.error ? <section className="changes-empty form-error">{snapshots.error}</section> : availableSnapshots.length < 2 ? <section className="changes-empty"><strong>Import two dated statements to compare changes.</strong><span>Choose the correct snapshot date during import; the latest import remains your active portfolio.</span></section> : <><section className="change-flow" aria-label="Portfolio comparison flow"><span>Older snapshot</span><i>→</i><span>Newer snapshot</span><i>→</i><span>Holding-level difference</span><i>→</i><span>Review changes</span></section><section className="table-shell changes-table-shell"><table className="changes-table"><thead><tr><th>Change</th><th>Fund holding</th><th>Previous value</th><th>New value</th><th>Value change</th></tr></thead><tbody>{comparison.loading ? <tr><td colSpan={5}>Comparing imported snapshots…</td></tr> : comparison.error ? <tr><td colSpan={5}>{comparison.error}</td></tr> : comparison.data?.changes.length ? comparison.data.changes.map((change) => <tr key={change.fund_name}><td><span className={`change-badge ${change.change_type.toLowerCase()}`}>{change.change_type}</span></td><td><strong>{change.fund_name}</strong></td><td>{money(change.older_current_value)}</td><td>{money(change.newer_current_value)}</td><td className={change.current_value_change >= 0 ? "positive-value" : "negative-value"}>{change.current_value_change > 0 ? "+" : ""}{money(change.current_value_change)}</td></tr>) : <tr><td colSpan={5}><div className="table-empty"><strong>No value changes between these snapshots</strong><span>The same funds and values appear in both statements.</span></div></td></tr>}</tbody></table></section><section className="evidence-empty"><strong>Change values come directly from the two imported statements.</strong><span>Explanations, manager commentary, and company-level causes need verified fund disclosures and document evidence before they can be shown.</span><button className="outline-button" onClick={() => onAsk("How should I interpret changes between two mutual-fund portfolio snapshots?")}>Ask about interpreting changes</button></section></>}</>;
}

function ExplorerView({ tab, onTab, selectedSchemes, onToggle, onAsk }: { tab: ExplorerTab; onTab: (tab: ExplorerTab) => void; selectedSchemes: MutualFundScheme[]; onToggle: (scheme: MutualFundScheme) => void; onAsk: (fundName: string) => void }) {
  return <div className="view-stack">
    <ViewHeading eyebrow="MARKET-WIDE FUND RESEARCH" title="Find a fund, then compare its evidence" description="Search the public Indian mutual-fund scheme catalogue, inspect recent NAV and historical NAV returns, or send a precisely named scheme to the research assistant." />
    <div className="explorer-provenance">Scheme names and NAV history are queried from MFapi.in. This market-wide catalogue is separate from your personal portfolio and indexed factsheets.</div>
    <div className="segmented" role="tablist" aria-label="Fund explorer sections"><TabButton active={tab === "discover"} onClick={() => onTab("discover")}>Find funds</TabButton><TabButton active={tab === "compare"} onClick={() => onTab("compare")}>Compare selected{selectedSchemes.length ? ` (${selectedSchemes.length})` : ""}</TabButton></div>
    {tab === "discover"
      ? <FundSchemeDiscovery selectedSchemes={selectedSchemes} onToggle={onToggle} onCompare={() => onTab("compare")} onAsk={onAsk} />
      : <FundSchemeCompare selectedSchemes={selectedSchemes} onToggle={onToggle} onBrowse={() => onTab("discover")} />}
  </div>;
}

function FundSchemeDiscovery({ selectedSchemes, onToggle, onCompare, onAsk }: { selectedSchemes: MutualFundScheme[]; onToggle: (scheme: MutualFundScheme) => void; onCompare: () => void; onAsk: (fundName: string) => void }) {
  const [query, setQuery] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [detailScheme, setDetailScheme] = useState<MutualFundScheme | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(() => setSearchTerm(query.trim()), 350);
    return () => window.clearTimeout(timer);
  }, [query]);
  const search = useApi<FundSchemeSearchData>(searchTerm.length >= 2 ? `/funds/search/?q=${encodeURIComponent(searchTerm)}&limit=12` : null);
  const overview = useApi<FundNavOverviewData>(detailScheme ? `/funds/nav-overview/${detailScheme.scheme_code}/` : null);
  const results = search.data?.query.toLowerCase() === searchTerm.toLowerCase() ? search.data.schemes : [];
  const selected = (scheme: MutualFundScheme) => selectedSchemes.some((item) => item.scheme_code === scheme.scheme_code);
  const nav = (value: number) => new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(value);
  const returnItems = overview.data?.returns ?? [];
  const maxReturnMagnitude = Math.max(1, ...returnItems.map((item) => Math.abs(item.cagr_percent ?? 0)));
  return <>
    <section className="fund-discovery-search">
      <form className="fund-discovery-search-row" onSubmit={(event) => { event.preventDefault(); setSearchTerm(query.trim()); }}>
        <label className="search-field">Search by fund or AMC name<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Try: HDFC ELSS, SBI Bluechip, Nifty 50 index" autoComplete="off" /></label>
        <button className="primary-button" type="submit" disabled={query.trim().length < 2}>Search schemes</button>
      </form>
      <div className="fund-discovery-meta"><span>Enter at least 2 characters · exact plan and option names are preserved</span><button className="text-action" type="button" onClick={onCompare} disabled={selectedSchemes.length < 2}>Compare selected ({selectedSchemes.length})</button></div>
    </section>
    {searchTerm.length < 2 ? <section className="fund-discovery-empty"><strong>Search beyond your own portfolio.</strong><span>Type an AMC or scheme name to search MFapi.in’s market-wide catalogue.</span></section>
      : search.loading ? <section className="fund-discovery-empty">Searching scheme catalogue…</section>
        : search.error ? <section className="fund-discovery-empty form-error"><strong>Could not search MFapi.in</strong><span>{search.error}</span><small>Try again in a moment; the public data provider can rate-limit requests.</small></section>
          : results.length === 0 ? <section className="fund-discovery-empty"><strong>No matching schemes found.</strong><span>Try a shorter AMC name or a different spelling.</span></section>
            : <section className="fund-scheme-results" aria-label="Mutual fund scheme search results">
              <div className="fund-scheme-results-heading"><div><p className="eyebrow">MATCHING SCHEMES</p><h3>{results.length} result{results.length === 1 ? "" : "s"} for “{searchTerm}”</h3></div><span>MFapi.in</span></div>
              {results.map((scheme) => <article className="fund-scheme-card" key={scheme.scheme_code}>
                <div className="fund-scheme-copy"><h4>{scheme.scheme_name}</h4><small>Scheme code {scheme.scheme_code} · Exact plan/option variant</small></div>
                <div className="fund-scheme-actions"><button className={selected(scheme) ? "outline-button selected" : "outline-button"} type="button" onClick={() => onToggle(scheme)} disabled={!selected(scheme) && selectedSchemes.length >= 5}>{selected(scheme) ? "Selected for compare" : "Add to compare"}</button><button className="text-action" type="button" onClick={() => setDetailScheme((current) => current?.scheme_code === scheme.scheme_code ? null : scheme)}>{detailScheme?.scheme_code === scheme.scheme_code ? "Hide NAV" : "NAV & returns"}</button><button className="text-action" type="button" onClick={() => onAsk(scheme.scheme_name)}>Ask assistant</button></div>
              </article>)}
              <small className="fund-provider-disclaimer">MFapi.in supplies scheme names and NAV history. It does not provide a verified risk rating, fund size, benchmark comparison, or investment recommendation here.</small>
            </section>}
    {detailScheme && <section className="fund-nav-overview"><div className="fund-scheme-results-heading"><div><p className="eyebrow">LIVE NAV SNAPSHOT</p><h3>{detailScheme.scheme_name}</h3></div><button className="text-action" type="button" onClick={() => setDetailScheme(null)}>Close</button></div>
      {overview.loading ? <p>Loading latest available NAV and return history…</p> : overview.error ? <p className="form-error">{overview.error}</p> : overview.data && <>
        <div className="fund-nav-highlight"><span>Latest NAV<strong>₹{nav(overview.data.latest_nav)}</strong></span><span>NAV date<strong>{overview.data.nav_date}</strong></span><span>History<strong>{overview.data.total_observations.toLocaleString("en-IN")} observations</strong></span></div>
        <div className="fund-nav-return-grid">{overview.data.returns.map((item) => <span key={item.years}>{item.years}-year NAV CAGR<strong>{item.cagr_percent == null ? "Not enough history" : `${item.cagr_percent.toFixed(2)}%`}</strong>{item.end_date && <small>Through {item.end_date}</small>}</span>)}</div>
        <section className="nav-return-chart" aria-label="Historical NAV CAGR by period"><div className="chart-card-heading"><div><p className="eyebrow">HISTORICAL NAV</p><h4>Return by period</h4><p>Bars show relative magnitude; the percentage labels are the reported annualized returns.</p></div></div><div className="nav-return-chart-list" role="list">{returnItems.map((item) => <div className="nav-return-chart-row" key={item.years} role="listitem"><span>{item.years}-year</span><div className="nav-return-track" aria-hidden="true"><i className={item.cagr_percent != null && item.cagr_percent < 0 ? "negative" : "positive"} style={{ width: `${item.cagr_percent == null ? 0 : Math.abs(item.cagr_percent) / maxReturnMagnitude * 100}%` }} /></div><strong>{item.cagr_percent == null ? "—" : `${item.cagr_percent.toFixed(2)}%`}</strong></div>)}</div></section>
        <small>Trailing annualized NAV return, calculated against the latest available NAV; excludes benchmark comparison and does not predict future returns. Source: MFapi.in.</small>
      </>}
    </section>}
  </>;
}

function FundSchemeCompare({ selectedSchemes, onToggle, onBrowse }: { selectedSchemes: MutualFundScheme[]; onToggle: (scheme: MutualFundScheme) => void; onBrowse: () => void }) {
  const [years, setYears] = useState(3);
  const [comparison, setComparison] = useState<FundNavCompareData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setComparison(null); setError(""); }, [selectedSchemes, years]);
  async function compare() {
    setLoading(true);
    setError("");
    try {
      const response = await apiRequest<ApiEnvelope<FundNavCompareData>>("/funds/nav-compare/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scheme_codes: selectedSchemes.map((scheme) => scheme.scheme_code), years }) });
      setComparison(response.data);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not compare NAV histories.");
    } finally {
      setLoading(false);
    }
  }
  if (selectedSchemes.length < 2) return <section className="fund-discovery-empty"><strong>Select at least two exact schemes to compare.</strong><span>Use Find funds to search the market and add two to five scheme variants.</span><button className="primary-button" type="button" onClick={onBrowse}>Find funds</button></section>;
  const metrics = comparison?.funds ?? [];
  const maxCagrMagnitude = Math.max(1, ...metrics.map((fund) => Math.abs(fund.cagr_percent)));
  return <section className="fund-nav-compare">
    <div className="fund-nav-compare-heading"><div><p className="eyebrow">NAV-BASED COMPARISON</p><h3>Compare selected schemes</h3><p>Compare trailing return and historical NAV variability—not fund size, portfolio holdings, or benchmark alpha.</p></div><div className="fund-nav-controls"><label>Period<select value={years} onChange={(event) => setYears(Number(event.target.value))}><option value={1}>1 year</option><option value={3}>3 years</option><option value={5}>5 years</option><option value={10}>10 years</option></select></label><button className="primary-button" type="button" onClick={compare} disabled={loading}>{loading ? "Comparing…" : `Compare ${selectedSchemes.length} funds`}</button></div></div>
    <div className="fund-selected-list">{selectedSchemes.map((scheme) => <span key={scheme.scheme_code}>{scheme.scheme_name}<button type="button" aria-label={`Remove ${scheme.scheme_name}`} onClick={() => onToggle(scheme)}>×</button></span>)}</div>
    {error && <p className="form-error">{error}</p>}
    {comparison && <section className="fund-compare-chart" aria-label={`${years}-year annualized return comparison`}><div className="chart-card-heading"><div><p className="eyebrow">RETURN COMPARISON</p><h4>{years}-year annualized return</h4><p>Historical NAV CAGR only. Bars show relative magnitude; negative returns are shown in red.</p></div></div><div className="fund-compare-chart-list" role="list">{selectedSchemes.map((scheme, index) => {
      const fund = metrics.find((item) => item.scheme_code === scheme.scheme_code);
      return <div className="fund-compare-chart-row" key={scheme.scheme_code} role="listitem"><span className="fund-compare-chart-name" title={scheme.scheme_name}>{scheme.scheme_name}</span><div className="fund-compare-track" aria-hidden="true"><i className={fund && fund.cagr_percent < 0 ? "negative" : "positive"} style={{ width: `${fund ? Math.abs(fund.cagr_percent) / maxCagrMagnitude * 100 : 0}%`, backgroundColor: fund && fund.cagr_percent < 0 ? undefined : portfolioChartPalette[index % portfolioChartPalette.length] }} /></div><strong>{fund ? `${fund.cagr_percent.toFixed(2)}%` : "—"}</strong></div>;
    })}</div></section>}
    {comparison && <div className="table-shell"><table className="fund-nav-compare-table"><thead><tr><th>Scheme</th><th>{years}-year CAGR</th><th>Annualized volatility</th><th>Maximum drawdown</th></tr></thead><tbody>{selectedSchemes.map((scheme) => {
      const fund = metrics.find((item) => item.scheme_code === scheme.scheme_code);
      return <tr key={scheme.scheme_code}><td><strong>{scheme.scheme_name}</strong><small>Code {scheme.scheme_code}{fund?.end_date ? ` · through ${fund.end_date}` : ""}</small></td><td>{fund ? `${fund.cagr_percent.toFixed(2)}%` : "Not available"}</td><td>{fund ? `${fund.annualized_volatility_percent.toFixed(2)}%` : "Not available"}</td><td>{fund ? `${fund.maximum_drawdown_percent.toFixed(2)}%` : "Not available"}</td></tr>;
    })}</tbody></table></div>}
    <small className="fund-provider-disclaimer">Calculated from daily NAV history provided by MFapi.in; historical volatility and drawdown are not forecasts. These figures are not benchmark-adjusted and are not investment advice.</small>
  </section>;
}

function HoldingsScanner({ holdings, selectedIds, onToggle, onCompare, onAsk, asOf }: { holdings: Holding[]; selectedIds: string[]; onToggle: (id: string) => void; onCompare: () => void; onAsk: (fundName: string) => void; asOf: string | null }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [sort, setSort] = useState("-current_value");
  const [page, setPage] = useState(1);
  const [detailId, setDetailId] = useState<string | null>(null);
  const pageSize = 20;
  const categories = ["All", ...Array.from(new Set(holdings.map((holding) => holding.category).filter((item): item is string => Boolean(item))))];
  const filtered = useMemo(() => holdings.filter((holding) => holding.fund_name.toLowerCase().includes(query.trim().toLowerCase()) && (category === "All" || holding.category === category)).sort((left, right) => {
    const field = sort.replace(/^-/, "") as "fund_name" | "current_value" | "invested_amount" | "allocation_percent";
    const comparison = field === "fund_name" ? left.fund_name.localeCompare(right.fund_name) : left[field] - right[field];
    return sort.startsWith("-") ? -comparison : comparison;
  }), [holdings, query, category, sort]);
  useEffect(() => { setPage(1); }, [query, category, sort]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const visibleHoldings = filtered.slice((page - 1) * pageSize, page * pageSize);
  const detail = holdings.find((holding) => holding.fund_id === detailId);
  const units = (value: number) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: 4 }).format(value);
  return <>
    <div className="filter-bar explorer-filter-bar"><label className="search-field">Search your funds<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by scheme name" /></label><label>Category<select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item}>{item}</option>)}</select></label><label>Sort by<select value={sort} onChange={(event) => setSort(event.target.value)}><option value="-current_value">Current value: high to low</option><option value="current_value">Current value: low to high</option><option value="-invested_amount">Invested: high to low</option><option value="-allocation_percent">Portfolio weight: high to low</option><option value="fund_name">Fund name: A to Z</option></select></label><button className="primary-button" type="button" onClick={onCompare} disabled={selectedIds.length < 2}>Compare {selectedIds.length} selected</button></div>
    <div className="scanner-result-summary"><span>{filtered.length} holding{filtered.length === 1 ? "" : "s"} in this snapshot{asOf ? ` · as of ${asOf}` : ""}</span><span>Select 2–5 to compare · values come from your imported statement</span></div>
    <div className="table-shell"><table className="scanner-table holdings-explorer-table"><thead><tr><th>Fund</th><th>Category</th><th>Units</th><th>Invested</th><th>Current value</th><th>Portfolio weight</th><th>Compare</th><th>Details</th></tr></thead><tbody>{visibleHoldings.length ? visibleHoldings.map((holding) => <tr key={holding.fund_id}><td><strong>{holding.fund_name}</strong></td><td>{holding.category || "Not provided"}</td><td className="numeric-cell">{units(holding.units)}</td><td className="numeric-cell">{money(holding.invested_amount)}</td><td className="numeric-cell">{money(holding.current_value)}</td><td className="numeric-cell">{holding.allocation_percent.toFixed(2)}%</td><td><label className="compare-check"><input type="checkbox" aria-label={`Compare ${holding.fund_name}`} checked={selectedIds.includes(holding.fund_id)} onChange={() => onToggle(holding.fund_id)} disabled={!selectedIds.includes(holding.fund_id) && selectedIds.length >= 5} /></label></td><td><button className="text-action" type="button" onClick={() => setDetailId((current) => current === holding.fund_id ? null : holding.fund_id)}>{detailId === holding.fund_id ? "Close" : "Details"}</button></td></tr>) : <tr><td colSpan={8}><div className="table-empty"><strong>No matching holdings</strong><span>Change the search or category filter.</span></div></td></tr>}</tbody></table></div>
    {filtered.length > pageSize && <nav className="explorer-pagination" aria-label="Fund holdings pages"><button className="outline-button" type="button" onClick={() => setPage((current) => Math.max(1, current - 1))} disabled={page === 1}>Previous</button><span>Page {page} of {pageCount}</span><button className="outline-button" type="button" onClick={() => setPage((current) => Math.min(pageCount, current + 1))} disabled={page === pageCount}>Next</button></nav>}
    {detail && <section className="explorer-detail"><div className="explorer-detail-heading"><div><p className="eyebrow">PORTFOLIO HOLDING</p><h3>{detail.fund_name}</h3><p>{detail.category || "Category not provided"}{asOf ? ` · statement as of ${asOf}` : ""}</p></div><button className="primary-button" type="button" onClick={() => onAsk(detail.fund_name)}>Ask FundLens about this fund</button></div><div className="explorer-detail-metrics"><span>Units<strong>{units(detail.units)}</strong></span><span>Amount invested<strong>{money(detail.invested_amount)}</strong></span><span>Current value<strong>{money(detail.current_value)}</strong></span><span>Portfolio weight<strong>{detail.allocation_percent.toFixed(2)}%</strong></span></div><small>These values are from your imported statement, not a live NAV or return feed. FundLens can answer document questions only when a matching factsheet is indexed.</small></section>}
  </>;
}

function HoldingsCompare({ holdings, selectedCount, onToggle, onBrowse, asOf }: { holdings: Holding[]; selectedCount: number; onToggle: (id: string) => void; onBrowse: () => void; asOf: string | null }) {
  if (holdings.length < 2) return <section className="empty-state compact"><p className="eyebrow">COMPARE HOLDINGS</p><h2>Select 2–5 funds from your holdings</h2><p>Comparison uses values from the same imported portfolio snapshot; it does not compare historical fund performance.</p><button className="primary-button" type="button" onClick={onBrowse}>Choose funds</button>{selectedCount > 0 && <button className="text-action" type="button" onClick={() => holdings.forEach((holding) => onToggle(holding.fund_id))}>Clear selection</button>}</section>;
  const rows: { label: string; value: (holding: Holding) => ReactNode }[] = [
    { label: "Category", value: (holding) => holding.category || "Not provided" },
    { label: "Units", value: (holding) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: 4 }).format(holding.units) },
    { label: "Amount invested", value: (holding) => money(holding.invested_amount) },
    { label: "Current value", value: (holding) => money(holding.current_value) },
    { label: "Portfolio weight", value: (holding) => `${holding.allocation_percent.toFixed(2)}%` },
  ];
  return <section className="holdings-comparison"><div className="comparison-heading"><div><p className="eyebrow">SAME PORTFOLIO SNAPSHOT</p><h3>Compare your selected funds</h3><p>Statement values only{asOf ? ` · as of ${asOf}` : ""}. Historical returns and risk data are not available here.</p></div><button className="outline-button" type="button" onClick={onBrowse}>Edit selection</button></div><div className="comparison-wrap"><table className="comparison-table"><thead><tr><th>Portfolio value</th>{holdings.map((holding) => <th key={holding.fund_id}><strong>{holding.fund_name}</strong><button className="remove-fund" type="button" onClick={() => onToggle(holding.fund_id)}>Remove</button></th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.label}><th>{row.label}</th>{holdings.map((holding) => <td key={holding.fund_id}>{row.value(holding)}</td>)}</tr>)}</tbody></table></div></section>;
}

function OverlapView({ userId, canManageDisclosures, onImport }: { userId: string; canManageDisclosures: boolean; onImport: () => void }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const { data, loading, error } = useApi<Overlap>(userId.trim() ? `/portfolio/overlap/?refresh=${refreshKey}` : null);
  const unavailable = Boolean(error);
  const overlapPercent = (data?.overall_overlap_percent ?? 0).toFixed(2);
  const status = loading ? "Loading" : unavailable ? "Unavailable" : `${overlapPercent}% shared`;
  return <div className="view-stack"><ViewHeading eyebrow="PORTFOLIO DIVERSIFICATION" title="Understand where your funds meet" description="Company-level overlap explains whether multiple funds truly diversify your portfolio." />
    <section className="explanation-panel"><span className={unavailable ? "risk-ring unavailable" : "risk-ring"}>{loading ? "…" : unavailable ? "—" : `${overlapPercent}%`}</span><div><h3>{unavailable ? "Overlap needs verified fund holdings" : "Shared-company exposure"}</h3><p>{unavailable ? "Your statement was imported successfully, but company-level overlap requires each fund to be matched with a verified holdings disclosure." : "This is the portion of your portfolio routed to companies held through two or more funds. It is an exposure measure, not a fund-similarity score."}</p></div></section>
    <section className="overlap-data-shell" aria-label="Portfolio overlap results"><div className="overlap-data-heading"><div><p className="eyebrow">COMPANY-LEVEL BREAKDOWN</p><h3>Top shared companies</h3><p>{unavailable ? "Overlap cannot be calculated from statement totals alone." : "Each result combines your weighted exposure to the same company across multiple funds."}</p></div><span>{status}</span></div>{unavailable ? <div className="overlap-unavailable"><strong>Company overlap is unavailable for this imported statement.</strong><p>{error}</p><span>Portfolio summary, holdings, allocation, and snapshot comparison still work from your imported CSV/XLSX data.</span><button className="outline-button" type="button" onClick={onImport}>View imported holdings</button></div> : <div className="table-shell"><table className="overlap-table"><thead><tr><th>Company</th><th>Funds holding it</th><th>Your shared exposure</th></tr></thead><tbody>{loading ? <tr><td colSpan={3}>Loading overlap results…</td></tr> : data?.companies.length ? data.companies.map((company) => <tr key={company.company}><td className="overlap-company"><strong>{company.company}</strong><small>{company.funds.length} funds</small></td><td><div className="overlap-fund-tags">{company.funds.map((fund) => <span key={fund.fund_name} title={`${fund.fund_name}${fund.portfolio_contribution_percent != null ? ` · ${fund.portfolio_contribution_percent.toFixed(2)}% of your portfolio` : ""}`}>{fund.fund_name}</span>)}</div></td><td className="overlap-exposure"><strong>{company.combined_exposure_percent.toFixed(2)}%</strong><small>of your portfolio</small></td></tr>) : <tr><td colSpan={3}><div className="table-empty"><strong>No shared-company exposure found</strong><span>No company is currently held in more than one fund for this portfolio.</span></div></td></tr>}</tbody></table></div>}</section>
    {canManageDisclosures && <FundDisclosureUploadPanel onImported={() => setRefreshKey((current) => current + 1)} />}
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
  const watchlist = useApi<{ items: WatchlistItem[] }>(userId.trim() ? `/watchlist/?refresh=${refresh}` : null);
  const company = useApi<CompanyExposure>(userId.trim() ? `/companies/${symbol}/fund-exposure/` : null);
  const marketOverview = useApi<MarketOverview>("/market/overview/");
  const marketConnected = Boolean(marketOverview.data?.configured && marketOverview.data.items.length);
  async function addToWatchlist() { setActionError(""); try { await apiRequest<ApiEnvelope<{ id: number }>>("/watchlist/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol }) }); setRefresh((value) => value + 1); } catch (requestError) { setActionError(requestError instanceof Error ? requestError.message : "Unable to add this company to the watchlist."); } }
  async function removeFromWatchlist(itemId: number) { setActionError(""); try { await apiRequest<unknown>(`/watchlist/${itemId}/`, { method: "DELETE" }); setRefresh((value) => value + 1); } catch (requestError) { setActionError(requestError instanceof Error ? requestError.message : "Unable to remove this watchlist item."); } }
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
