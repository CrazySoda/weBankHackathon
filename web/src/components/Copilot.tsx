import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { ClipboardEvent, ReactNode } from "react";
import { Activity, ArrowLeft, ArrowRight, ArrowUp, Check, Copy, FileSearch, FileText, History, LineChart, Pencil, Plus, Search, Sparkles, Square, Trash2, X } from "lucide-react";
import { api } from "../api";
import type { CashProjectionState, CopilotCardKind, DealState, Finding, FxOption } from "../api";
import { formatMoney } from "../api";
import { useConfirm } from "./ConfirmDialog";

export type CopilotTab = "findings" | "fx" | "cash" | "documents" | "audit";

/** Card data is snapshotted when the answer is given, so an old answer never changes under you. */
type CardSnapshot =
  | { kind: "findings"; findings: Finding[]; focus: string[] }
  | { kind: "fx"; routes: FxOption[] }
  | { kind: "cash"; projection: CashProjectionState }
  | { kind: "documents"; documents: Array<{ filename: string; kind: string }> };

type Message = {
  id: string;
  role: "assistant" | "user";
  text: string;
  card?: CardSnapshot;
  followUps?: string[];
  /** "model" = AI copilot; "local" = built-in answer from the deal record */
  source?: "model" | "local";
  note?: string;
  streaming?: boolean;
};

type Conversation = { id: string; title: string; createdAt: number; updatedAt: number; messages: Message[] };
type ActivityStep = { label: string; detail: string; status: "active" | "done" };
type Intent = "findings" | "fx" | "cash" | "documents" | "next" | "none";

const STORAGE_PREFIX = "cleartrade.copilot.";
const MAX_CONVERSATIONS = 30;
const MAX_MESSAGES = 200;
const GREETING = "Hi! I can help you understand this deal. Ask about a finding, FX options, cash flow, or what to do next.";
const STARTER_PROMPTS = ["What needs attention?", "Compare FX routes", "Show cash flow", "What should I do next?"];

let idCounter = 0;
const newId = () => `${Date.now().toString(36)}-${(idCounter++).toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
const greeting = (): Message => ({ id: newId(), role: "assistant", text: GREETING });
const blankConversation = (): Conversation => ({ id: newId(), title: "New conversation", createdAt: Date.now(), updatedAt: Date.now(), messages: [greeting()] });
const hasUserTurn = (conversation: Conversation) => conversation.messages.some((message) => message.role === "user");

function storageKey(dealId: string) {
  return `${STORAGE_PREFIX}${dealId}`;
}

function loadConversations(dealId: string | null): Conversation[] {
  if (!dealId) return [];
  try {
    const raw = localStorage.getItem(storageKey(dealId));
    const parsed = raw ? (JSON.parse(raw) as Conversation[]) : [];
    return Array.isArray(parsed) ? parsed.filter((item) => item && Array.isArray(item.messages)) : [];
  } catch {
    return [];
  }
}

function saveConversations(dealId: string, conversations: Conversation[]) {
  const kept = conversations
    .filter(hasUserTurn)
    .sort((a, b) => b.updatedAt - a.updatedAt)
    .slice(0, MAX_CONVERSATIONS)
    .map((conversation) => ({ ...conversation, messages: conversation.messages.slice(-MAX_MESSAGES).map((message) => ({ ...message, streaming: false })) }));
  try {
    if (kept.length) localStorage.setItem(storageKey(dealId), JSON.stringify(kept));
    else localStorage.removeItem(storageKey(dealId));
  } catch {
    /* storage full or unavailable: history is a convenience, not a record */
  }
}

/** Remove a deal's saved conversations (called when a deal is removed from the console). */
export function clearCopilotHistory(dealId?: string) {
  if (dealId) {
    localStorage.removeItem(storageKey(dealId));
    return;
  }
  Object.keys(localStorage).filter((key) => key.startsWith(STORAGE_PREFIX)).forEach((key) => localStorage.removeItem(key));
}

function titleFrom(question: string) {
  const clean = question.replace(/\s+/g, " ").trim();
  return clean.length > 48 ? `${clean.slice(0, 47)}…` : clean || "Image upload";
}

function relativeTime(ts: number) {
  const minutes = Math.round((Date.now() - ts) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days < 7 ? `${days} d ago` : new Date(ts).toLocaleDateString();
}

// ---------- built-in answers (used when the AI copilot is unavailable) ----------

const INTENT_PATTERNS: Array<[Intent, RegExp]> = [
  // whole words only: "accurate" must not match "rate", "profile" must not match "file"
  ["fx", /\b(fx|forex|exchange|routes?|rates?|convert\w*|conversion|currenc(y|ies)|spread)\b/g],
  ["cash", /\b(cash|cashflow|fund\w*|runway|financ\w*|balances?|projection|liquidity|working capital)\b/g],
  ["documents", /\b(documents?|docs?|uploads?|uploaded|files?|paperwork|invoices?|packing list)\b/g],
  ["next", /\b(approv\w*|next|what should|what now|ready|proceed|pay ?out|sign)\b/g],
  ["findings", /\b(block\w*|issues?|findings?|problems?|discrepanc\w*|risks?|attention|wrong|mismatch\w*)\b/g],
];

/** Most matched intent wins; ties go to the more specific intent (list order). */
export function classify(question: string): Intent {
  const q = question.toLowerCase();
  let best: Intent = "none";
  let bestScore = 0;
  for (const [intent, pattern] of INTENT_PATTERNS) {
    const score = q.match(pattern)?.length ?? 0;
    if (score > bestScore) {
      best = intent;
      bestScore = score;
    }
  }
  return best;
}

/** `focus` = the finding being explained (card narrows to it); `related` = findings an answer mentions. */
function snapshot(kind: CopilotCardKind | Intent, state: DealState, focus: string[] = [], related: string[] = []): CardSnapshot | undefined {
  if (kind === "findings") return { kind, findings: state.findings.filter((finding) => finding.status === "open" || focus.includes(finding.check_id) || related.includes(finding.check_id)), focus };
  if (kind === "fx" && state.fx_options.length) return { kind, routes: state.fx_options };
  if (kind === "cash" && state.cash_projection) return { kind, projection: state.cash_projection };
  if (kind === "documents") return { kind, documents: state.documents.map((doc) => ({ filename: doc.filename, kind: doc.kind })) };
  return undefined;
}

function explainLocally(finding: Finding): string {
  const fix = finding.fixable
    ? "A corrected document can resolve it: upload the fixed version in Documents and run the review again."
    : finding.severity === "block"
      ? "It cannot be fixed with a corrected document, so the deal cannot be approved while it is open."
      : "It does not stop the deal, but review it before approving.";
  return [`**${finding.summary}**`, finding.explanation, fix].filter(Boolean).join("\n\n");
}

function localAnswer(question: string, state: DealState, focusId?: string | null): { text: string; card?: CardSnapshot; followUps: string[] } {
  const open = state.findings.filter((finding) => finding.status === "open");
  const blocks = open.filter((finding) => finding.severity === "block");
  const focused = focusId ? state.findings.find((finding) => finding.check_id === focusId) : undefined;
  if (focused) return { text: explainLocally(focused), card: snapshot("findings", state, [focused.check_id]), followUps: ["What should I do next?"] };

  switch (classify(question)) {
    case "findings":
      return {
        text: open.length
          ? `I found ${open.length} open finding${open.length === 1 ? "" : "s"}${blocks.length ? `, including ${blocks.length} blocking ${blocks.length === 1 ? "issue" : "issues"}` : ""}. Here’s what needs attention:`
          : "There are no open findings in this deal record.",
        card: snapshot("findings", state),
        followUps: open.length ? ["What should I do next?"] : ["Compare FX routes"],
      };
    case "fx": {
      if (!state.fx_options.length) return { text: "FX routes have not been calculated yet. Run the deal review and I can compare the available synthetic routes.", followUps: [] };
      const best = state.fx_options.reduce((a, b) => (b.net_minor > a.net_minor ? b : a));
      return { text: `${state.fx_options.length} synthetic route${state.fx_options.length === 1 ? " is" : "s are"} available. **${best.provider}** currently returns the highest net amount, ${formatMoney(best.net_minor, best.buy_currency)}.`, card: snapshot("fx", state), followUps: ["Show cash flow"] };
    }
    case "cash": {
      const projection = state.cash_projection;
      if (!projection) return { text: "A cash flow projection is not available yet. Run the deal review to calculate it.", followUps: [] };
      return {
        text: `This illustrative forecast assumes zero opening cash, a 30% deposit on day 0, and the LC amount arriving at maturity. It reaches ${formatMoney(projection.min_balance_minor, projection.currency)} on day ${projection.min_balance_day} and stays below zero for ${projection.days_below_zero} days. It does not represent an actual account balance.`,
        card: snapshot("cash", state),
        followUps: ["What needs attention?"],
      };
    }
    case "documents":
      return { text: `This deal has ${state.documents.length} document${state.documents.length === 1 ? "" : "s"} attached and ${state.extracted.length} extraction${state.extracted.length === 1 ? "" : "s"} recorded.`, card: snapshot("documents", state), followUps: ["What needs attention?"] };
    case "next":
      return { text: nextStep(state, open, blocks), card: blocks.length ? snapshot("findings", state) : undefined, followUps: blocks.length ? [`Explain: ${blocks[0].summary}`] : [] };
    default:
      return { text: "I can help explain this deal’s findings, documents, FX routes, cash flow, or next step. Try one of these:", followUps: STARTER_PROMPTS.slice(0, 3) };
  }
}

function nextStep(state: DealState, open: Finding[], blocks: Finding[]): string {
  if (state.receipt) return "This deal has completed its sandbox payout. The receipt and audit trail are available in the review.";
  if (state.escalation_reason) return "A person needs to review this deal before it can continue. Check the supporting documents and review history for next steps.";
  if (blocks.length) return `The next step is to address the ${blocks.length} blocking finding${blocks.length === 1 ? "" : "s"} before approval. First: ${blocks[0].summary}`;
  if (!state.documents.length) return "Start by adding the deal documents (letter of credit, invoice, packing list), then run the review.";
  if (!state.policy) return "The review has not reached the policy check yet. Run the deal review to check documents, FX and cash flow.";
  if (state.policy.decision === "deny") return `The policy check denied this deal${state.policy.reason ? `: ${state.policy.reason}` : "."} It cannot be approved as it stands.`;
  if (state.policy.decision === "escalate") return `The policy check sent this deal to a person for review${state.policy.reason ? `: ${state.policy.reason}` : "."}`;
  if (open.length) return `The policy check allows this deal. ${open.length} non-blocking finding${open.length === 1 ? " is" : "s are"} still open, so review ${open.length === 1 ? "it" : "them"}, then use the approval action when you are ready.`;
  return "The policy check allows this deal. Review the approval details, then use the approval action when you are ready.";
}

function activityFor(question: string, focused: boolean): string {
  if (focused) return "Finding and rule details";
  return { fx: "FX route comparison", cash: "Cash flow projection", documents: "Document register", next: "Findings and policy status", findings: "Deal findings", none: "Deal summary" }[classify(question)];
}

function fallbackNote(error: unknown): string {
  const detail = error instanceof Error ? error.message : "";
  if (detail === "unverified_numbers") return "The AI answer quoted a figure that is not in the deal record, so it was withheld. Showing the built-in answer.";
  if (detail === "limit") return "The AI copilot limit for this deal is reached. Showing the built-in answer.";
  return "The AI copilot is unavailable right now. Showing the built-in answer.";
}

// ---------- rendering ----------

/** Tiny, safe markdown subset: paragraphs, "- " / "1. " lists, **bold**, `code`. No HTML injection. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) return <code key={index}>{part.slice(1, -1)}</code>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function RichText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const items = list.items.map((item, index) => <li key={index}>{inline(item)}</li>);
    blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
    list = null;
  };
  for (const line of text.split("\n")) {
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const ordered = !bullet;
      if (list && list.ordered !== ordered) flush();
      list ??= { ordered, items: [] };
      list.items.push((bullet ?? numbered)![1]);
      continue;
    }
    flush();
    if (line.trim()) blocks.push(<p key={blocks.length}>{inline(line)}</p>);
  }
  flush();
  return <>{blocks}</>;
}

function OpenTab({ label, tab, onNavigate }: { label: string; tab: CopilotTab; onNavigate?: (tab: CopilotTab) => void }) {
  if (!onNavigate) return null;
  return <button type="button" className="chat-card-link" onClick={() => onNavigate(tab)}>{label} <ArrowRight size={12} /></button>;
}

function FindingsCard({ card, onExplain, onNavigate, disabled }: { card: Extract<CardSnapshot, { kind: "findings" }>; onExplain: (finding: Finding) => void; onNavigate?: (tab: CopilotTab) => void; disabled: boolean }) {
  const shown = card.focus.length ? card.findings.filter((finding) => card.focus.includes(finding.check_id)) : card.findings;
  const list = shown.length ? shown : card.findings;
  return <div className="chat-data-card"><div className="chat-card-head"><span className="chat-card-icon amber"><FileSearch size={15} /></span><div><strong>{card.focus.length ? "Finding details" : "Issues to review"}</strong><small>Snapshot from this answer</small></div><span className="chat-card-count">{list.length}</span></div>
    {list.length ? <div className="chat-finding-list">{list.slice(0, 5).map((finding) => <div className="chat-finding" key={finding.check_id}><span className={`severity-dot ${finding.severity}`} /><div><strong>{finding.summary}</strong><small>{finding.status !== "open" ? `Status: ${finding.status}` : finding.fixable ? "A corrected document may help" : finding.severity === "block" ? "Needs to be resolved before approval" : "Review recommended"}</small></div><button type="button" className="chat-explain" disabled={disabled} onClick={() => onExplain(finding)}>Explain</button></div>)}</div> : <div className="chat-card-empty"><Check size={15} /> No open issues</div>}
    <div className="chat-card-foot"><OpenTab label="Open Issues" tab="findings" onNavigate={onNavigate} /></div>
  </div>;
}

function FxCard({ routes, onNavigate }: { routes: FxOption[]; onNavigate?: (tab: CopilotTab) => void }) {
  const best = routes.reduce((a, b) => (b.net_minor > a.net_minor ? b : a));
  const currencyGroups = routes.reduce((groups, route) => {
    const group = groups.get(route.buy_currency) ?? [];
    group.push(route);
    groups.set(route.buy_currency, group);
    return groups;
  }, new Map<string, FxOption[]>());
  return <div className="chat-data-card"><div className="chat-card-head"><span className="chat-card-icon green"><LineChart size={15} /></span><div><strong>FX route comparison</strong><small>Synthetic quotes · net proceeds</small></div></div>
    <div className="chat-fx-chart" aria-label="Estimated payout comparison">
      {[...currencyGroups.entries()].map(([currency, options]) => {
        const max = Math.max(...options.map((route) => route.net_minor), 1);
        return <div className="chat-fx-chart-group" key={currency}>
          {currencyGroups.size > 1 && <small>Payout in {currency}</small>}
          {options.map((route) => <div className="chat-fx-chart-row" key={route.route_id}>
            <span>{route.provider}</span><div><i className={route.route_id === best.route_id ? "best" : ""} style={{ width: `${Math.max(2, route.net_minor / max * 100)}%` }}/></div>
            <b>{formatMoney(route.net_minor, currency)}</b>
          </div>)}
        </div>;
      })}
    </div>
    <div className="chat-fx-list">{routes.slice().sort((a, b) => b.net_minor - a.net_minor).slice(0, 4).map((route) => <div className={`chat-fx-row ${route.route_id === best.route_id ? "best" : ""}`} key={route.route_id}><div><strong>{route.provider}</strong><small>{route.sell_currency} → {route.buy_currency}{route.route_id === best.route_id ? " · Best net" : ""}</small></div><b>{formatMoney(route.net_minor, route.buy_currency)}</b></div>)}</div>
    <div className="chat-card-foot"><OpenTab label="Open FX" tab="fx" onNavigate={onNavigate} /></div>
  </div>;
}

function CashCard({ projection, onNavigate }: { projection: CashProjectionState; onNavigate?: (tab: CopilotTab) => void }) {
  const values = projection.daily_balance_minor;
  const horizonDays = Math.max(0, values.length - 1);
  const min = Math.min(...values, 0); const max = Math.max(...values, 0); const range = max - min || 1;
  const points = values.map((value, index) => `${values.length < 2 ? 50 : index / (values.length - 1) * 280},${8 + (max - value) / range * 82}`).join(" ");
  return <div className="chat-data-card"><div className="chat-card-head"><span className="chat-card-icon green"><LineChart size={15} /></span><div><strong>Cash flow projection</strong><small>{horizonDays}-day illustrative forecast · {projection.currency}</small></div></div>
    <div className="chat-chart"><svg viewBox="0 0 280 104" role="img" aria-label="Projected daily cash balance"><line x1="0" x2="280" y1={8 + (max / range) * 82} y2={8 + (max / range) * 82} stroke="#dce7e3" strokeDasharray="4 4" /><polyline points={points} fill="none" stroke="#187b70" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" /></svg></div>
    <div className="chat-cash-stats"><span>Lowest balance<strong>{formatMoney(projection.min_balance_minor, projection.currency)}</strong></span><span>Lowest day<strong>Day {projection.min_balance_day}</strong></span><span>Days below zero<strong>{projection.days_below_zero}</strong></span></div>
    <div className="chat-card-foot"><small className="faint">Assumes zero starting cash, a 30% upfront deposit, and LC receipt at maturity.</small><OpenTab label="Open Cash flow" tab="cash" onNavigate={onNavigate} /></div>
  </div>;
}

function DocumentsCard({ documents, onNavigate }: { documents: Array<{ filename: string; kind: string }>; onNavigate?: (tab: CopilotTab) => void }) {
  return <div className="chat-data-card"><div className="chat-card-head"><span className="chat-card-icon green"><FileText size={15} /></span><div><strong>Documents</strong><small>Attached to this deal</small></div><span className="chat-card-count">{documents.length}</span></div>
    {documents.length ? <div className="chat-finding-list">{documents.slice(0, 6).map((doc, index) => <div className="chat-finding" key={`${doc.filename}-${index}`}><FileText size={13} /><div><strong>{doc.filename}</strong><small>{doc.kind.replace(/_/g, " ")}</small></div></div>)}</div> : <div className="chat-card-empty">No documents yet</div>}
    <div className="chat-card-foot"><OpenTab label="Open Documents" tab="documents" onNavigate={onNavigate} /></div>
  </div>;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return <button type="button" className="chat-action" aria-label="Copy answer" title="Copy answer" onClick={() => { void navigator.clipboard?.writeText(text).then(() => { setCopied(true); window.setTimeout(() => setCopied(false), 1400); }); }}>{copied ? <Check size={13} /> : <Copy size={13} />}</button>;
}

// ---------- component ----------

export default function Copilot({ state, onClose, open, dealId, onDocumentUploaded, onNavigate }: { state: DealState | null; onClose: () => void; open: boolean; dealId: string | null; onDocumentUploaded?: () => void; onNavigate?: (tab: CopilotTab) => void }) {
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations(dealId));
  const [current, setCurrent] = useState<Conversation>(() => conversations[0] ?? blankConversation());
  const [view, setView] = useState<"chat" | "history">("chat");
  const [search, setSearch] = useState("");
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null);
  const [steps, setSteps] = useState<ActivityStep[]>([]);
  const [thinking, setThinking] = useState(false);
  const [pastedImage, setPastedImage] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState("");
  const [draft, setDraft] = useState("");
  const [confirm, confirmDialog] = useConfirm();
  const endRef = useRef<HTMLDivElement>(null);
  const runRef = useRef(0); // bumped to cancel an in-flight answer
  const messages = current.messages;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, steps, view]);

  // persist the active conversation into the deal's history whenever it changes
  useEffect(() => {
    if (!dealId || !hasUserTurn(current) || current.messages.some((message) => message.streaming)) return;
    setConversations((list) => {
      const next = [current, ...list.filter((item) => item.id !== current.id)];
      saveConversations(dealId, next);
      return next;
    });
  }, [current, dealId]);

  useEffect(() => () => { runRef.current += 1; }, []);

  const updateMessages = (conversationId: string, update: (messages: Message[]) => Message[]) => {
    setCurrent((conversation) => conversation.id === conversationId ? { ...conversation, messages: update(conversation.messages), updatedAt: Date.now() } : conversation);
  };

  const stop = () => {
    runRef.current += 1;
    setCurrent((conversation) => ({ ...conversation, messages: conversation.messages.map((message) => (message.streaming ? { ...message, streaming: false } : message)) }));
    setSteps([]);
    setThinking(false);
  };

  const startNew = () => {
    if (thinking) stop();
    setCurrent(blankConversation());
    setDraft("");
    setView("chat");
  };

  const openConversation = (conversation: Conversation) => {
    if (thinking) stop();
    setCurrent(conversation);
    setView("chat");
  };

  const deleteConversation = (id: string) => {
    if (!dealId) return;
    const next = conversations.filter((item) => item.id !== id);
    setConversations(next);
    saveConversations(dealId, next);
    // stay in the history list; the active chat just becomes a fresh one
    if (current.id === id) { if (thinking) stop(); setCurrent(blankConversation()); }
  };

  const confirmDelete = async (conversation: Conversation) => {
    const ok = await confirm({
      title: "Delete this conversation?",
      message: <>“{conversation.title}” will be removed from this browser. The deal record and its audit trail are not affected.</>,
      confirmLabel: "Delete conversation",
    });
    if (ok) deleteConversation(conversation.id);
  };

  const commitRename = () => {
    if (!renaming || !dealId) return;
    const title = renaming.title.trim() || "Untitled conversation";
    const next = conversations.map((item) => (item.id === renaming.id ? { ...item, title } : item));
    setConversations(next);
    saveConversations(dealId, next);
    if (current.id === renaming.id) setCurrent((conversation) => ({ ...conversation, title }));
    setRenaming(null);
  };

  const send = async (text = draft, focusId: string | null = null) => {
    const question = text.trim();
    if ((!question && !pastedImage) || thinking) return;
    const run = ++runRef.current;
    const conversationId = current.id;
    // earlier turns, minus the greeting, give the model the conversation's context
    const priorTurns = messages.filter((message, index) => !(index === 0 && message.role === "assistant") && message.text).map((message) => ({ role: message.role, text: message.text }));
    let attachment: File | null = null;
    if (pastedImage) {
      if (!dealId) { setUploadError("Choose a deal before adding an image."); return; }
      attachment = pastedImage;
      setThinking(true);
      setSteps([{ label: "Adding image to deal documents", detail: attachment.name, status: "active" }]);
      setPastedImage(null);
      setUploadError("");
      try {
        await api.uploadDocument(dealId, attachment, "unknown");
        onDocumentUploaded?.();
      } catch (cause) {
        setThinking(false);
        setSteps([]);
        setPastedImage(attachment);
        setUploadError(cause instanceof Error ? cause.message : "The image could not be added to this deal.");
        return;
      }
    }
    setDraft("");
    const userText = [question, attachment ? `Image added to Documents: ${attachment.name}` : ""].filter(Boolean).join("\n");
    setCurrent((conversation) => ({
      ...conversation,
      title: hasUserTurn(conversation) ? conversation.title : titleFrom(question || attachment?.name || ""),
      updatedAt: Date.now(),
      messages: [...conversation.messages, { id: newId(), role: "user", text: userText }],
    }));
    setThinking(true);

    let reply: Omit<Message, "id" | "role"> = { text: "", followUps: [] };
    if (attachment) {
      setSteps([{ label: "Adding image to deal documents", detail: attachment.name, status: "done" }]);
      reply = { text: "The image has been added to this deal’s documents. Run a review to extract its details and check it alongside the other paperwork.", followUps: ["Show documents"] };
    } else if (!state || !dealId) {
      reply = { text: "Select a deal and I can look up its current status.", followUps: [] };
    } else {
      const lookup = { label: "Reading deal record", detail: activityFor(question, Boolean(focusId)), status: "done" as const };
      setSteps([lookup, { label: "Asking the deal copilot", detail: "Answers are checked against the deal record", status: "active" }]);
      try {
        const answer = await api.askCopilot(dealId, { question, history: priorTurns, focus_check_id: focusId });
        if (run !== runRef.current) return;
        reply = {
          // some models emit a literal backslash-n inside the JSON string
          text: answer.answer.replace(/\\n/g, "\n"),
          card: answer.declined ? undefined : snapshot(answer.card, state, focusId ? [focusId] : [], answer.finding_ids),
          followUps: answer.follow_ups,
          source: "model",
        };
      } catch (error) {
        if (run !== runRef.current) return;
        const local = localAnswer(question, state, focusId);
        reply = { ...local, source: "local", note: fallbackNote(error) };
      }
      setSteps([lookup, { label: "Asking the deal copilot", detail: reply.source === "model" ? "Answer checked" : "Used built-in answer", status: "done" }]);
    }
    if (run !== runRef.current) return;

    const id = newId();
    updateMessages(conversationId, (list) => [...list, { id, role: "assistant", ...reply, streaming: true, text: "" }]);
    // reveal the answer in short chunks; "stop" or a new chat cancels it
    const words = reply.text.split(/(\s+)/);
    for (let index = 0; index < words.length; index += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 14));
      if (run !== runRef.current) return;
      const chunk = words[index];
      updateMessages(conversationId, (list) => list.map((message) => (message.id === id ? { ...message, text: message.text + chunk } : message)));
    }
    updateMessages(conversationId, (list) => list.map((message) => (message.id === id ? { ...message, streaming: false } : message)));
    setSteps([]);
    setThinking(false);
  };

  const explain = (finding: Finding) => void send(`Explain: ${finding.summary}`, finding.check_id);

  const followUp = (prompt: string) => {
    const match = prompt.match(/^Explain: (.*)$/);
    const finding = match ? state?.findings.find((item) => item.summary === match[1]) : undefined;
    void send(prompt, finding?.check_id ?? null);
  };

  const pasteImage = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const item = Array.from(event.clipboardData.items).find((clipboardItem) => clipboardItem.type.startsWith("image/"));
    if (!item) return;
    const blob = item.getAsFile();
    if (!blob) return;
    event.preventDefault();
    if (!/^(image\/png|image\/jpeg)$/.test(blob.type)) { setUploadError("Paste a PNG or JPG image."); return; }
    if (blob.size > 10 * 1024 * 1024) { setUploadError("Images must be smaller than 10 MB."); return; }
    const extension = blob.type.split("/")[1]?.replace("jpeg", "jpg") || "png";
    setPastedImage(new File([blob], `pasted-image-${Date.now()}.${extension}`, { type: blob.type }));
    setUploadError("");
  };

  const history = useMemo(() => {
    const q = search.trim().toLowerCase();
    const all = conversations.filter(hasUserTurn).sort((a, b) => b.updatedAt - a.updatedAt);
    return q ? all.filter((item) => item.title.toLowerCase().includes(q) || item.messages.some((message) => message.text.toLowerCase().includes(q))) : all;
  }, [conversations, search]);

  const lastAssistant = [...messages].reverse().find((message) => message.role === "assistant");
  const showStarters = !thinking && !hasUserTurn(current) && Boolean(state);

  return <aside className={`copilot-panel conversation-panel ${open ? "" : "copilot-hidden"}`} aria-label="Deal copilot" aria-hidden={!open}>
    <header className="copilot-head">
      {view === "history"
        ? <button className="icon-button" onClick={() => setView("chat")} aria-label="Back to conversation"><ArrowLeft size={17} /></button>
        : <div className="copilot-avatar"><Sparkles size={17} /></div>}
      <div className="copilot-title"><strong>{view === "history" ? "Conversation history" : "Deal copilot"}</strong><span>{view === "history" ? `${history.length} saved for this deal` : hasUserTurn(current) ? current.title : state ? "Here to help with this deal" : "Choose a deal to get started"}</span></div>
      <button className={`icon-button history-toggle ${view === "history" ? "active" : ""}`} title="Conversation history" aria-label="Conversation history" aria-pressed={view === "history"} disabled={!dealId} onClick={() => setView((value) => (value === "history" ? "chat" : "history"))}><History size={17} /></button>
      <button className="icon-button" title="New conversation" aria-label="New conversation" onClick={startNew}><Plus size={17} /></button>
      <button className="icon-button" onClick={onClose} aria-label="Close copilot"><X size={18} /></button>
    </header>

    {view === "history" ? <div className="copilot-history">
      <label className="history-search"><Search size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search conversations" aria-label="Search conversations" /></label>
      <button type="button" className="history-new" onClick={startNew}><Plus size={14} /> New conversation</button>
      {history.length === 0 && <div className="history-empty">{search ? "No conversations match your search." : "No saved conversations for this deal yet. Ask a question to start one."}</div>}
      <ul className="history-list">{history.map((item) => <li key={item.id} className={item.id === current.id ? "active" : ""}>
        {renaming?.id === item.id
          ? <form className="history-rename" onSubmit={(event) => { event.preventDefault(); commitRename(); }}><input autoFocus value={renaming.title} onChange={(event) => setRenaming({ id: item.id, title: event.target.value })} onBlur={commitRename} onKeyDown={(event) => { if (event.key === "Escape") setRenaming(null); }} aria-label="Conversation title" maxLength={80} /></form>
          : <button type="button" className="history-open" onClick={() => openConversation(item)}><strong>{item.title}</strong><small>{relativeTime(item.updatedAt)} · {item.messages.filter((message) => message.role === "user").length} question{item.messages.filter((message) => message.role === "user").length === 1 ? "" : "s"}</small></button>}
        <button type="button" className="chat-action" title="Rename" aria-label={`Rename ${item.title}`} onClick={() => setRenaming({ id: item.id, title: item.title })}><Pencil size={13} /></button>
        <button type="button" className="chat-action danger" title="Delete" aria-label={`Delete ${item.title}`} onClick={() => void confirmDelete(item)}><Trash2 size={13} /></button>
      </li>)}</ul>
    </div> : <div className="copilot-messages conversation-messages">
      {messages.map((message) => <article key={message.id} className={`chat-turn ${message.role}`}>
        {message.role === "assistant" && <div className="chat-turn-avatar"><Sparkles size={14} /></div>}
        <div className="chat-turn-body">
          {message.note && !message.streaming && <div className="chat-note">{message.note}</div>}
          {message.text && <div className="chat-turn-text">{message.role === "assistant" ? <RichText text={message.text} /> : message.text}{message.streaming && <span className="typing-caret" />}</div>}
          {!message.streaming && message.card?.kind === "findings" && <FindingsCard card={message.card} onExplain={explain} onNavigate={onNavigate} disabled={thinking} />}
          {!message.streaming && message.card?.kind === "fx" && <FxCard routes={message.card.routes} onNavigate={onNavigate} />}
          {!message.streaming && message.card?.kind === "cash" && <CashCard projection={message.card.projection} onNavigate={onNavigate} />}
          {!message.streaming && message.card?.kind === "documents" && <DocumentsCard documents={message.card.documents} onNavigate={onNavigate} />}
          {message.role === "assistant" && !message.streaming && message.source && <div className="chat-meta"><span>{message.source === "model" ? "AI answer · checked against deal record" : "Built-in answer"}</span><CopyButton text={message.text} /></div>}
          {message === lastAssistant && !thinking && !message.streaming && Boolean(message.followUps?.length) && <div className="chat-followups">{message.followUps!.map((prompt) => <button type="button" key={prompt} onClick={() => followUp(prompt)}>{prompt}</button>)}</div>}
        </div>
      </article>)}
      {thinking && steps.length > 0 && <div className="chat-activity"><div className="chat-turn-avatar"><Activity size={14} /></div><div className="chat-activity-body">{steps.map((step) => <div className="chat-activity-step" key={step.label}><span className={`activity-state ${step.status}`}>{step.status === "done" ? <Check size={12} /> : <span className="activity-spinner" />}</span><span>{step.label}<small>{step.detail}</small></span></div>)}</div></div>}
      {showStarters && <div className="copilot-prompts">{STARTER_PROMPTS.map((prompt) => <button key={prompt} onClick={() => void send(prompt)}>{prompt}</button>)}</div>}
      <div ref={endRef} />
    </div>}

    {view === "chat" && <form className={`copilot-compose conversation-compose ${pastedImage ? "has-pasted-image" : ""}`} onSubmit={(event) => { event.preventDefault(); void send(); }}>
      {pastedImage && <div className="pasted-image-chip"><span>{pastedImage.name}</span><button type="button" aria-label="Remove pasted image" onClick={() => setPastedImage(null)}><X size={14} /></button></div>}
      <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onPaste={pasteImage} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); } }} placeholder="Message or paste an image…" aria-label="Message copilot" rows={1} maxLength={1000} />
      {thinking
        ? <button type="button" aria-label="Stop answer" title="Stop" onClick={stop}><Square size={14} /></button>
        : <button aria-label="Send message" disabled={!draft.trim() && !pastedImage}><ArrowUp size={18} /></button>}
    </form>}
    {uploadError && <div className="copilot-upload-error" role="alert">{uploadError}</div>}
    {confirmDialog}
    <div className="copilot-foot">Synthetic data. Answers use this deal’s record only; check original documents before acting.</div>
  </aside>;
}
