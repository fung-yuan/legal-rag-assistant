"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Home,
  MessageSquare,
  BookOpen,
  Layers,
  Search,
  ChevronDown,
  Plus,
  MoreHorizontal,
  Pin,
  ArrowUp,
  Paperclip,
  Sparkles,
  Database,
  Shield,
  Scale,
  KeyRound,
  Check,
  Copy,
  Terminal,
  Globe,
  Cpu,
  BrainCircuit,
  HelpCircle,
  BarChart3,
  Table,
  List
} from "lucide-react";

interface Message {
  id: string;
  sender: "user" | "assistant";
  text: string;
  agent1Brief?: string;
  agent2Brief?: string;
  resources?: { title: string; url: string; snippet?: string }[];
  citations?: {
    document_id: string;
    provision_ref: string;
    title?: string;
    content: string;
    metadata?: {
      year?: string;
      bulletin?: string;
      language?: string;
      pages?: string;
      doc_number?: string;
    };
  }[];
}

interface AgentState {
  status: "idle" | "running" | "done" | "error";
  agent1: "pending" | "running" | "done";
  agent2: "pending" | "running" | "done";
  agent3: "pending" | "running" | "done";
  currentMessage: string;
}

interface LegalDocument {
  id: string;
  title: string;
  status: string;
  issued_date: string;
  description: string;
  short_name?: string;
  provision_count: number;
}

interface Provision {
  id: string;
  provision_ref: string;
  title: string;
  content: string;
  metadata?: Record<string, any>;
}

interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
}

const baseLaws = [
  {
    name: "Bulletins Officiels (1999–2024)",
    tag: "Official Gazette",
    desc: "Archive of Moroccan official bulletins and decrees published over the last 25 years.",
    query: "What major legal updates and decrees were published in the Official Bulletins?",
    icon: BookOpen,
    className: "gradient-card-1",
    textColor: "text-blue-600"
  },
  {
    name: "Moudawana (Code de la Famille)",
    tag: "Family Code",
    desc: "Family law codification: marriage, divorce, custody, inheritance, and guardianship.",
    query: "ما هي شروط الزواج والأهلية في مدونة الأسرة؟",
    icon: BookOpen,
    className: "gradient-card-2",
    textColor: "text-rose-600"
  },
  {
    name: "Code de Commerce",
    tag: "Commercial Code",
    desc: "Commercial obligations, corporate entities (SARL/SA), and trading regulations.",
    query: "What are the legal requirements for commercial company setup under the Commercial Code?",
    icon: Layers,
    className: "gradient-card-3",
    textColor: "text-amber-600"
  },
  {
    name: "Code du Travail",
    tag: "Labor Code",
    desc: "Employment contracts, employee rights, dismissal protocols, and social security.",
    query: "ما هي شروط وإجراءات فصل الأجير في قانون الشغل؟",
    icon: BrainCircuit,
    className: "gradient-card-4",
    textColor: "text-emerald-600"
  },
  {
    name: "Code Foncier",
    tag: "Property Code",
    desc: "Real estate acquisition, land registration (conservation foncière), and property rights.",
    query: "How does property registration work under Moroccan real estate law?",
    icon: Globe,
    className: "gradient-card-1",
    textColor: "text-sky-600"
  },
  {
    name: "Code Pénal",
    tag: "Penal Code",
    desc: "Criminal codification defining criminal liability, infractions, and penal sanctions.",
    query: "What are the general principles of penal liability under the Moroccan Penal Code?",
    icon: Shield,
    className: "gradient-card-2",
    textColor: "text-purple-600"
  },
  {
    name: "Code de Procédure Civile",
    tag: "Civil Procedure",
    desc: "Judicial administration, court jurisdictions, litigation protocols, and legal appeals.",
    query: "ما هي قواعد الاختصاص القضائي في قانون المسطرة المدنية؟",
    icon: Scale,
    className: "gradient-card-3",
    textColor: "text-teal-600"
  },
  {
    name: "Dahir des Obligations et Contrats",
    tag: "Civil Obligations (DOC)",
    desc: "General civil law governing contractual obligations, liability, and legal deeds.",
    query: "What are the essential conditions for contract validity under the Dahir des Obligations et Contrats?",
    icon: Database,
    className: "gradient-card-4",
    textColor: "text-indigo-600"
  },
];

const suggestionChips = [
  "ما هي شروط الزواج في مدونة الأسرة؟",
  "What are the lawful grounds for termination under the Labor Code?",
  "ما هي إلتزامات التاجر في قانون التجارة؟",
  "How does land registration work under Moroccan property law?",
  "ما هي شروط العقد في قانون الالتزامات والعقود؟",
  "What major decrees were published in recent Official Bulletins?",
  "ما هي قواعد المسطرة المدنية في المحاكم المغربية؟",
  "What are the general principles of the Moroccan Penal Code?"
];





const getApiBase = () => {
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
};

export default function HomeApp() {
  const [query, setQuery] = useState("");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sidebarSearchQuery, setSidebarSearchQuery] = useState("");
  
  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const messages = activeSession ? activeSession.messages : [];

  const [agentState, setAgentState] = useState<AgentState>({
    status: "idle",
    agent1: "pending",
    agent2: "pending",
    agent3: "pending",
    currentMessage: "",
  });

  const [activeAgent1Brief, setActiveAgent1Brief] = useState("");
  const [activeAgent2Brief, setActiveAgent2Brief] = useState("");
  const [openBriefs, setOpenBriefs] = useState<Record<string, boolean>>({});
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<any | null>(null);

  const [modalLang, setModalLang] = useState<string | null>(null);
  const [modalPageNum, setModalPageNum] = useState<string | null>(null);
  const [loadingModalPage, setLoadingModalPage] = useState(false);

  const [viewMode, setViewMode] = useState<"chat" | "statistics">("chat");
  const [stats, setStats] = useState<any>(null);
  const [loadingStats, setLoadingStats] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load chat history and view mode from localStorage on mount (Keeping only marriage conversation)
  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedSessions = localStorage.getItem("morocco_law_chat_sessions");
      if (savedSessions) {
        try {
          const parsed = JSON.parse(savedSessions);
          // Filter to keep only the marriage conversation
          const marriageSessions = parsed.filter((s: any) => 
            s.title.includes("الزواج") || s.title.toLowerCase().includes("marriage") ||
            s.messages.some((m: any) => m.text.includes("الزواج") || m.text.toLowerCase().includes("marriage"))
          );
          
          if (marriageSessions.length > 0) {
            setSessions(marriageSessions);
            setActiveSessionId(marriageSessions[0].id);
            localStorage.setItem("morocco_law_chat_sessions", JSON.stringify(marriageSessions));
            localStorage.setItem("morocco_law_active_session_id", marriageSessions[0].id);
          } else {
            setSessions([]);
            setActiveSessionId(null);
            localStorage.removeItem("morocco_law_chat_sessions");
            localStorage.removeItem("morocco_law_active_session_id");
          }
        } catch (e) {
          console.error("Failed to parse saved chat sessions:", e);
        }
      }
      const savedView = localStorage.getItem("morocco_law_view_mode");
      if (savedView) {
        setViewMode(savedView as any);
      }
    }
  }, []);

  // Save chat history to localStorage on change
  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("morocco_law_chat_sessions", JSON.stringify(sessions));
    }
  }, [sessions]);

  // Save active session id to localStorage on change
  useEffect(() => {
    if (typeof window !== "undefined") {
      if (activeSessionId) {
        localStorage.setItem("morocco_law_active_session_id", activeSessionId);
      } else {
        localStorage.removeItem("morocco_law_active_session_id");
      }
    }
  }, [activeSessionId]);

  const deleteSession = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeSessionId === id) {
      setActiveSessionId(null);
    }
  };

  useEffect(() => {
    if (viewMode === "chat") {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, agentState, viewMode]);

  useEffect(() => {
    if (viewMode === "statistics") {
      fetchStats();
    }
  }, [viewMode]);

  const fetchStats = async () => {
    setLoadingStats(true);
    try {
      const res = await fetch(`${getApiBase()}/api/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error("Error fetching stats:", err);
    } finally {
      setLoadingStats(false);
    }
  };

  const [modalContent, setModalContent] = useState<string | null>(null);
  const [modalDocId, setModalDocId] = useState<string | null>(null);
  const [modalProvisionRef, setModalProvisionRef] = useState<string | null>(null);
  const [modalMetadata, setModalMetadata] = useState<any | null>(null);

  useEffect(() => {
    if (selectedCitation) {
      const initialLang = selectedCitation.metadata?.language || "FR";
      const pagesRaw = selectedCitation.metadata?.pages || "1";
      const firstPageMatch = pagesRaw.toString().match(/\d+/);
      const initialPage = firstPageMatch ? firstPageMatch[0] : "1";
      
      setModalLang(initialLang.toUpperCase());
      setModalPageNum(initialPage);
      setModalContent(selectedCitation.content || "");
      setModalDocId(selectedCitation.document_id || "");
      setModalProvisionRef(selectedCitation.provision_ref || "");
      setModalMetadata(selectedCitation.metadata || null);
    } else {
      setModalLang(null);
      setModalPageNum(null);
      setModalContent(null);
      setModalDocId(null);
      setModalProvisionRef(null);
      setModalMetadata(null);
    }
  }, [selectedCitation]);

  const toggleModalLanguage = async (targetLang: string) => {
    if (!selectedCitation || targetLang === modalLang || !modalDocId || !modalProvisionRef) return;
    
    setLoadingModalPage(true);
    try {
      const res = await fetch(`${getApiBase()}/api/provisions/correspond?document_id=${encodeURIComponent(modalDocId)}&provision_ref=${encodeURIComponent(modalProvisionRef)}&target_lang=${encodeURIComponent(targetLang)}`);
      if (res.ok) {
        const data = await res.json();
        if (data) {
          if (data.page) {
            const match = data.page.toString().match(/\d+/);
            setModalPageNum(match ? match[0] : "1");
          }
          if (data.content) {
            setModalContent(data.content);
          }
          if (data.document_id) {
            setModalDocId(data.document_id);
          }
          if (data.provision_ref) {
            setModalProvisionRef(data.provision_ref);
          }
          if (data.metadata) {
            setModalMetadata(data.metadata);
          } else {
            setModalMetadata({
              language: targetLang,
              year: modalMetadata?.year || selectedCitation.metadata?.year || "Unknown",
              bulletin: targetLang === "AR"
                ? (modalMetadata?.bulletin || selectedCitation.metadata?.bulletin || "").replace("_Fr", "_Ar").replace("_fr", "_Ar")
                : (modalMetadata?.bulletin || selectedCitation.metadata?.bulletin || "").replace("_Ar", "_Fr").replace("_ar", "_Fr"),
              pages: data.page || "1"
            });
          }
        }
      }
    } catch (e) {
      console.error("Failed to fetch corresponding provision page:", e);
    } finally {
      setModalLang(targetLang);
      setLoadingModalPage(false);
    }
  };

  const isArabic = (text: string) => {
    if (!text) return false;
    return /[\u0600-\u06FF]/.test(text);
  };

  const toggleBrief = (id: string) => {
    setOpenBriefs((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const exportChat = () => {
    if (!activeSession) return;
    const chatTitle = activeSession.title;
    let mdContent = `# Chat Session: ${chatTitle}\n\n`;
    activeSession.messages.forEach((m) => {
      const role = m.sender === "user" ? "User" : "Assistant";
      mdContent += `### ${role}\n${m.text}\n\n`;
      if (m.agent1Brief) {
        mdContent += `**Agent 1 (Local DB Retrieval) Brief:**\n\`\`\`\n${m.agent1Brief}\n\`\`\`\n\n`;
      }
      if (m.agent2Brief) {
        mdContent += `**Agent 2 (Web Compliance) Brief:**\n\`\`\`\n${m.agent2Brief}\n\`\`\`\n\n`;
      }
    });

    const blob = new Blob([mdContent], { type: "text/markdown;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `${chatTitle.replace(/[^a-z0-9]/gi, "_").toLowerCase()}.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleSearch = async (searchQuery: string) => {
    if (!searchQuery.trim()) return;

    setQuery("");
    const userMsgId = Date.now().toString();
    let currentSessionId = activeSessionId;

    if (!currentSessionId) {
      currentSessionId = Date.now().toString();
      const newSession: ChatSession = {
        id: currentSessionId,
        title: searchQuery.length > 35 ? searchQuery.slice(0, 35) + "..." : searchQuery,
        messages: [{ id: userMsgId, sender: "user", text: searchQuery }],
        createdAt: Date.now()
      };
      setSessions(prev => [newSession, ...prev]);
      setActiveSessionId(currentSessionId);
    } else {
      setSessions(prev => prev.map(s => {
        if (s.id === currentSessionId) {
          return {
            ...s,
            messages: [...s.messages, { id: userMsgId, sender: "user", text: searchQuery }]
          };
        }
        return s;
      }));
    }

    setAgentState({
      status: "running",
      agent1: "running",
      agent2: "pending",
      agent3: "pending",
      currentMessage: "Agent 1 is querying the consolidated legal databases...",
    });
    setActiveAgent1Brief("");
    setActiveAgent2Brief("");

    try {
      const response = await fetch(`${getApiBase()}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: searchQuery }),
      });

      if (!response.body) {
        throw new Error("No response body available from server.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let tempAgent1Brief = "";
      let tempAgent2Brief = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const parsed = JSON.parse(line);
            if (parsed.status === "agent_1_start") {
              setAgentState((prev) => ({
                ...prev,
                agent1: "running",
                currentMessage: parsed.message,
              }));
            } else if (parsed.status === "agent_1_done") {
              tempAgent1Brief = parsed.data;
              setActiveAgent1Brief(parsed.data);
              setAgentState((prev) => ({
                ...prev,
                agent1: "done",
                agent2: "running",
                currentMessage:
                  "Agent 1 complete. Agent 2 is querying administrative web portals...",
              }));
            } else if (parsed.status === "agent_2_start") {
              setAgentState((prev) => ({
                ...prev,
                agent2: "running",
                currentMessage: parsed.message,
              }));
            } else if (parsed.status === "agent_2_done") {
              tempAgent2Brief = parsed.data;
              setActiveAgent2Brief(parsed.data);
              setAgentState((prev) => ({
                ...prev,
                agent2: "done",
                agent3: "running",
                currentMessage:
                  "Agent 2 complete. Agent 3 is synthesizing legal findings...",
              }));
            } else if (parsed.status === "agent_3_start") {
              setAgentState((prev) => ({
                ...prev,
                agent3: "running",
                currentMessage: parsed.message,
              }));
            } else if (parsed.status === "agent_3_done") {
              const assistantMsgId = Date.now().toString();
              setSessions(prev => prev.map(s => {
                if (s.id === currentSessionId) {
                  return {
                    ...s,
                    messages: [
                      ...s.messages,
                      {
                        id: assistantMsgId,
                        sender: "assistant",
                        text: parsed.data,
                        agent1Brief: tempAgent1Brief,
                        agent2Brief: tempAgent2Brief,
                        resources: parsed.resources,
                        citations: parsed.citations,
                      }
                    ]
                  };
                }
                return s;
              }));
              setAgentState({
                status: "done",
                agent1: "done",
                agent2: "done",
                agent3: "done",
                currentMessage: "Synthesis complete!",
              });
            } else if (parsed.status === "error") {
              throw new Error(parsed.message);
            }
          } catch (err) {
            console.error("Failed to parse stream line:", err);
          }
        }
      }
    } catch (error: unknown) {
      console.error(error);
      setAgentState((prev) => ({
        ...prev,
        status: "error",
        currentMessage: `Error: ${error instanceof Error ? error.message : "Something went wrong."}`,
      }));
    }
  };

  const renderInlineStyles = (text: string) => {
    const parts = text.split(/(\*\*.*?\*\*)/g);
    return parts.map((part, idx) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={idx} className="font-semibold text-slate-900 bg-slate-100 px-1.5 py-0.5 rounded text-xs md:text-sm">
            {part.slice(2, -2)}
          </strong>
        );
      }
      return part;
    });
  };

  const renderContent = (text: string) => {
    const lines = text.split("\n");
    const isAr = isArabic(text);
    return lines.map((line, i) => {
      if (line.startsWith("### "))
        return (
          <h3 
            key={i} 
            className={`text-sm font-bold text-slate-800 mt-5 mb-2 flex items-center gap-1.5 ${isAr ? "flex-row-reverse text-right font-medium font-sans" : ""}`}
            dir={isAr ? "rtl" : "ltr"}
          >
            <span className="w-1.5 h-1.5 bg-slate-600 rounded-full shrink-0" />
            {line.replace("### ", "")}
          </h3>
        );
      if (line.startsWith("## "))
        return (
          <h2
            key={i}
            className={`text-base font-extrabold text-slate-900 mt-6 mb-3 border-b border-slate-100 pb-1.5 tracking-tight flex items-center gap-2 ${isAr ? "flex-row-reverse text-right font-medium font-sans" : ""}`}
            dir={isAr ? "rtl" : "ltr"}
          >
            <span className="w-1 h-4 bg-gradient-to-b from-blue-500 to-indigo-600 rounded-full shrink-0" />
            {line.replace("## ", "")}
          </h2>
        );
      if (line.startsWith("# "))
        return (
          <h1
            key={i}
            className={`text-lg font-black text-slate-900 mt-7 mb-4 tracking-tight ${isAr ? "text-right font-bold font-sans" : ""}`}
            dir={isAr ? "rtl" : "ltr"}
          >
            {line.replace("# ", "")}
          </h1>
        );
      if (line.trim().startsWith("- ") || line.trim().startsWith("* ")) {
        const content = line.replace(/^[\s-*]+/, "");
        return (
          <ul 
            key={i} 
            className={`list-disc mb-1.5 text-slate-600 text-xs md:text-sm ${isAr ? "pr-5 pl-0 text-right font-sans" : "pl-5"}`}
            dir={isAr ? "rtl" : "ltr"}
          >
            <li className={`${isAr ? "pr-1" : "pl-1"} leading-relaxed`}>{renderInlineStyles(content)}</li>
          </ul>
        );
      }
      if (/^\d+\./.test(line.trim())) {
        const content = line.replace(/^\d+\.\s*/, "");
        return (
          <ol 
            key={i} 
            className={`list-decimal mb-1.5 text-slate-600 text-xs md:text-sm ${isAr ? "pr-5 pl-0 text-right font-sans" : "pl-5"}`}
            dir={isAr ? "rtl" : "ltr"}
          >
            <li className={`${isAr ? "pr-1" : "pl-1"} leading-relaxed`}>{renderInlineStyles(content)}</li>
          </ol>
        );
      }
      if (line.trim().startsWith(">")) {
        const content = line.replace(/^>\s*/, "");
        return (
          <blockquote
            key={i}
            className={`bg-slate-50 px-4 py-3 my-4 rounded text-slate-700 text-xs md:text-sm leading-relaxed font-mono ${
              isAr ? "border-r-3 border-l-0 text-right font-sans rounded-l-lg" : "border-l-3 border-r-0 rounded-r-lg"
            } border-slate-500`}
            dir={isAr ? "rtl" : "ltr"}
          >
            {renderInlineStyles(content)}
          </blockquote>
        );
      }
      if (!line.trim()) return <div key={i} className="h-3" />;
      return (
        <p 
          key={i} 
          className={`text-slate-600 mb-3 text-xs md:text-sm leading-relaxed ${isAr ? "text-right font-sans" : ""}`}
          dir={isAr ? "rtl" : "ltr"}
        >
          {renderInlineStyles(line)}
        </p>
      );
    });
  };

  // Rendering the dynamic interactive pipeline chart (Light Theme)
  const renderPipelineSVG = (state: AgentState) => {
    const isStep1Active = state.agent1 === "running";
    const isStep1Done = state.agent1 === "done";
    const isStep2Active = state.agent2 === "running";
    const isStep2Done = state.agent2 === "done";
    const isStep3Active = state.agent3 === "running";
    const isStep3Done = state.agent3 === "done";

    return (
      <div className="w-full py-4 px-6 bg-slate-50 rounded-2xl flex flex-col md:flex-row items-center justify-between gap-6 border border-slate-100 relative overflow-hidden">
        {/* Node 1: KB DB Agent */}
        <div className={`flex items-center gap-3 transition-all duration-300 ${isStep1Active ? "scale-105" : ""}`}>
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center border transition-all duration-300 ${
            isStep1Active 
              ? "border-blue-500 bg-blue-50 text-blue-600 shadow-sm animate-pulse"
              : isStep1Done 
              ? "border-slate-200 bg-slate-100 text-slate-700"
              : "border-slate-200 bg-white text-slate-400"
          }`}>
            <Terminal className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1">
              <span className="text-xs font-bold text-slate-800">Agent 1: Legal KB</span>
              {isStep1Active && <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping" />}
            </div>
            <p className="text-[10px] text-slate-500">Querying 147k+ articles</p>
          </div>
        </div>

        {/* Connector 1 */}
        <div className="hidden md:flex flex-1 items-center justify-center">
          <div className="h-0.5 w-full bg-slate-200 relative rounded-full overflow-hidden">
            {(isStep1Active || isStep1Done) && (
              <div className="absolute inset-0 bg-blue-500 h-full rounded-full transition-all duration-300" style={{ width: isStep1Done ? "100%" : "50%" }} />
            )}
          </div>
        </div>

        {/* Node 2: Web Compliance Agent */}
        <div className={`flex items-center gap-3 transition-all duration-300 ${isStep2Active ? "scale-105" : ""}`}>
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center border transition-all duration-300 ${
            isStep2Active 
              ? "border-blue-500 bg-blue-50 text-blue-600 shadow-sm animate-pulse"
              : isStep2Done 
              ? "border-slate-200 bg-slate-100 text-slate-700"
              : "border-slate-200 bg-white text-slate-400"
          }`}>
            <Globe className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1">
              <span className="text-xs font-bold text-slate-800">Agent 2: Web Lookup</span>
              {isStep2Active && <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping" />}
            </div>
            <p className="text-[10px] text-slate-500">Portals & circular circulars</p>
          </div>
        </div>

        {/* Connector 2 */}
        <div className="hidden md:flex flex-1 items-center justify-center">
          <div className="h-0.5 w-full bg-slate-200 relative rounded-full overflow-hidden">
            {(isStep2Active || isStep2Done) && (
              <div className="absolute inset-0 bg-blue-500 h-full rounded-full transition-all duration-300" style={{ width: isStep2Done ? "100%" : "50%" }} />
            )}
          </div>
        </div>

        {/* Node 3: Synthesis Advisor */}
        <div className={`flex items-center gap-3 transition-all duration-300 ${isStep3Active ? "scale-105" : ""}`}>
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center border transition-all duration-300 ${
            isStep3Active 
              ? "border-blue-500 bg-blue-50 text-blue-600 shadow-sm animate-pulse"
              : isStep3Done 
              ? "border-slate-200 bg-slate-100 text-slate-700"
              : "border-slate-200 bg-white text-slate-400"
          }`}>
            <BrainCircuit className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1">
              <span className="text-xs font-bold text-slate-800">Agent 3: Synthesis</span>
              {isStep3Active && <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping" />}
            </div>
            <p className="text-[10px] text-slate-500">Drafting legal synthesis</p>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-screen w-screen bg-white text-slate-900 font-sans overflow-hidden">
      
      {/* ─── Left Sidebar ─── */}
      <aside className="w-64 flex flex-col justify-between px-4 py-5 z-10 shrink-0 hidden lg:flex border-r border-slate-100 bg-[#f8fafc]">
        <div className="flex flex-col gap-6">
          
          {/* Profile / Model Selection Dropdown (Askk UI style) */}
          <div className="bg-white rounded-2xl border border-slate-200/80 p-3 flex items-center justify-between shadow-sm cursor-pointer hover:bg-slate-50/50 transition-colors">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-emerald-500 flex items-center justify-center text-white shadow-sm">
                <BrainCircuit className="w-4 h-4" />
              </div>
              <div className="text-left">
                <p className="font-extrabold text-xs text-slate-800">Morocco Law AI</p>
                <p className="text-[10px] text-slate-400">Consolidated RAG Console</p>
              </div>
            </div>
            <ChevronDown className="w-4 h-4 text-slate-400" />
          </div>

          {/* Search Box */}
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder="Search conversations..."
              value={sidebarSearchQuery}
              onChange={(e) => setSidebarSearchQuery(e.target.value)}
              className="bg-slate-200/50 border-transparent text-slate-700 placeholder:text-slate-400 text-xs pl-9 h-9 rounded-xl focus-visible:bg-white focus-visible:border-slate-200 focus-visible:ring-0"
            />
          </div>

          {/* Navigation Menu */}
          <nav className="flex flex-col gap-2">
            <button
              onClick={() => {
                setActiveSessionId(null);
                setAgentState({
                  status: "idle",
                  agent1: "pending",
                  agent2: "pending",
                  agent3: "pending",
                  currentMessage: "",
                });
                setActiveAgent1Brief("");
                setActiveAgent2Brief("");
                setViewMode("chat");
              }}
              className="flex items-center justify-center gap-2 w-full px-3.5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold shadow-sm transition-all cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              New Inquiry
            </button>
            <button
              onClick={() => setViewMode("chat")}
              className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all w-full cursor-pointer border ${
                viewMode === "chat"
                  ? "bg-white border-slate-200/80 text-slate-800 shadow-sm"
                  : "bg-transparent border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100"
              }`}
            >
              <MessageSquare className={`w-4 h-4 ${viewMode === "chat" ? "text-blue-500" : "text-slate-400"}`} />
              Agent Console
            </button>

            <button
              onClick={() => setViewMode("statistics")}
              className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all w-full cursor-pointer border ${
                viewMode === "statistics"
                  ? "bg-white border-slate-200/80 text-slate-800 shadow-sm"
                  : "bg-transparent border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100"
              }`}
            >
              <BarChart3 className={`w-4 h-4 ${viewMode === "statistics" ? "text-blue-500" : "text-slate-400"}`} />
              Database Analytics
            </button>
          </nav>

          {/* Saved Conversations Section */}
          {sessions.length > 0 && (
            <div className="flex flex-col gap-2 flex-1 min-h-0 mt-4 border-t border-slate-200/50 pt-4">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-1">
                Saved Conversations
              </span>
              <ScrollArea className="flex-1 pr-1">
                <div className="flex flex-col gap-1.5 pb-2">
                  {sessions
                    .filter((s) =>
                      s.title.toLowerCase().includes(sidebarSearchQuery.toLowerCase()) ||
                      s.messages.some((m) => m.text.toLowerCase().includes(sidebarSearchQuery.toLowerCase()))
                    )
                    .map((s) => {
                    const isActive = s.id === activeSessionId;
                    return (
                      <div
                        key={s.id}
                        onClick={() => {
                          setActiveSessionId(s.id);
                          setViewMode("chat");
                        }}
                        className={`group flex items-center justify-between px-3 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer border ${
                          isActive
                            ? "bg-white border-slate-200/80 text-slate-800 shadow-sm"
                            : "bg-transparent border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-100"
                        }`}
                      >
                        <div className="flex items-center gap-2.5 min-w-0 flex-1">
                          <MessageSquare className={`w-3.5 h-3.5 shrink-0 ${isActive ? "text-blue-500" : "text-slate-400"}`} />
                          <span className={`truncate pr-1 flex-1 ${isArabic(s.title) ? "text-right font-sans" : ""}`} dir={isArabic(s.title) ? "rtl" : "ltr"}>{s.title}</span>
                        </div>
                        <button
                          onClick={(e) => deleteSession(s.id, e)}
                          className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 p-0.5 rounded transition-opacity"
                          title="Delete conversation"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>
            </div>
          )}

        </div>

        {/* Database version indicator */}
        <div className="flex items-center gap-2 px-1 text-[10px] text-slate-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span>BO.2026.ONLINE · FTS5 Node</span>
        </div>
      </aside>

      {/* ─── Main Workspace ─── */}
      <main className="flex-1 flex flex-col bg-white overflow-hidden relative min-w-0">
        
        {/* Top Navbar */}
        <header className="h-14 border-b border-slate-200/70 bg-white/90 backdrop-blur-md sticky top-0 flex items-center justify-between px-6 z-20 shrink-0 shadow-xs">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center gap-2 bg-slate-100/80 px-3 py-1 rounded-full border border-slate-200/50">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-bold text-slate-700">
                {viewMode === "chat" ? "GPT-4o Multi-Agent" : "Database Analytics"}
              </span>
            </div>
            {viewMode === "statistics" && stats && (
              <span className="text-[10px] text-slate-500 font-medium font-mono bg-slate-50 px-2 py-0.5 rounded-md border border-slate-200/60">
                Analyzed {stats.total_provisions.toLocaleString()} articles
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {viewMode === "chat" ? (
              <>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={exportChat}
                  disabled={!activeSession}
                  className="text-xs text-slate-600 hover:text-slate-900 border-slate-200/80 hover:bg-slate-50 disabled:opacity-40 rounded-xl font-medium"
                >
                  Export Chat
                </Button>
                <Button size="sm" className="bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold px-4 shadow-xs">
                  Database Updates
                </Button>
              </>
            ) : (
              <Button size="sm" className="bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold px-4 shadow-xs" onClick={() => fetchStats()}>
                Refresh Stats
              </Button>
            )}
          </div>
        </header>

        {viewMode === "chat" ? (
          <>
            {/* Chat / Content workspace area */}
            <ScrollArea className="flex-1 min-h-0">
              <div className="space-y-8 max-w-4xl mx-auto px-6 py-6 md:px-8 md:py-8 pb-6">

                {/* Welcome / Hero Landing Workspace State */}
                {messages.length === 0 && agentState.status === "idle" && (
                  <div className="flex flex-col items-center justify-center text-center space-y-7 max-w-4xl mx-auto py-2 md:py-4">
                    
                    {/* Hero Badge & Headline */}
                    <div className="space-y-3 max-w-2xl mx-auto">
                      <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-100/90 border border-slate-200/80 text-slate-700 text-xs font-semibold shadow-xs">
                        <span className="w-2 h-2 rounded-full bg-blue-600 animate-pulse" />
                        <span>Moroccan Legal AI Suite</span>
                        <span className="text-slate-300">|</span>
                        <span className="text-blue-600 font-bold">Multi-Agent RAG</span>
                      </div>

                      <h1 className="text-3xl md:text-4xl font-black text-slate-900 tracking-tight leading-tight">
                        Consolidated Legal Intelligence & Jurisprudence Assistant
                      </h1>

                      <p className="text-slate-500 text-xs md:text-sm leading-relaxed max-w-xl mx-auto font-normal">
                        Autonomous multi-agent system synthesizing Moroccan official bulletins, codifications, and administrative portals with instant legal citations.
                      </p>

                      {/* System Architecture Quick Badges */}
                      <div className="pt-2 flex flex-wrap items-center justify-center gap-2 text-[11px] font-medium text-slate-600">
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-emerald-50 text-emerald-700 border border-emerald-200/60 rounded-lg font-bold">
                          ⚖️ 70,764 Provisions Indexed
                        </span>
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-blue-50 text-blue-700 border border-blue-200/60 rounded-lg font-bold">
                          📜 7,667 Bulletins Officiels (1999–2024)
                        </span>
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-purple-50 text-purple-700 border border-purple-200/60 rounded-lg font-bold">
                          ⚡ SQLite FTS5 Engine
                        </span>
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-50 text-amber-700 border border-amber-200/60 rounded-lg font-bold">
                          🤖 Multi-Agent Pipeline
                        </span>
                      </div>
                    </div>

                    {/* Section Header */}
                    <div className="w-full flex items-center gap-4 pt-2">
                      <div className="h-px bg-slate-200/70 flex-1" />
                      <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest px-2">
                        Explore Legal Domains & Codifications
                      </span>
                      <div className="h-px bg-slate-200/70 flex-1" />
                    </div>

                    {/* 8 Feature Cards spanning all major Moroccan law domains (Ultra-compact) */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-2.5 w-full">
                      {baseLaws.map((law, i) => {
                        const IconComp = law.icon;
                        return (
                          <Card
                            key={i}
                            className={`border-slate-200/70 hover:border-slate-300 hover:shadow-xs transition-all duration-200 cursor-pointer shadow-xs p-2.5 rounded-xl relative ${law.className}`}
                            onClick={() => setQuery(law.query)}
                          >
                            <div className="flex items-center gap-2.5">
                              <div className="w-7 h-7 rounded-lg bg-white flex items-center justify-center shadow-xs border border-slate-100 shrink-0">
                                <IconComp className={`w-3.5 h-3.5 ${law.textColor}`} />
                              </div>
                              <div className="min-w-0 flex-1 text-left">
                                <div className="flex items-center justify-between gap-1">
                                  <h3 className={`text-xs font-extrabold truncate ${law.textColor}`}>
                                    {law.name}
                                  </h3>
                                  <span className="text-[7.5px] font-bold text-slate-400 uppercase tracking-wider shrink-0">
                                    {law.tag}
                                  </span>
                                </div>
                                <p className="text-[9.5px] text-slate-500 truncate font-medium mt-0.5">
                                  {law.desc}
                                </p>
                              </div>
                            </div>
                          </Card>
                        );
                      })}
                    </div>

                    {/* Suggestion pills directly embedded in welcome flow */}
                    <div className="w-full space-y-2 pt-2">
                      <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-widest block">
                        Frequently Asked Legal Questions
                      </span>
                      <div className="flex flex-wrap gap-2 justify-center max-w-3xl mx-auto">
                        {suggestionChips.map((chip, idx) => (
                          <button
                            key={idx}
                            onClick={() => handleSearch(chip)}
                            className="bg-white border border-slate-200/80 hover:border-blue-300 text-slate-700 hover:bg-blue-50/40 hover:text-blue-700 text-[11px] font-semibold py-1.5 px-3.5 rounded-full cursor-pointer transition-all shadow-xs flex items-center gap-1.5"
                          >
                            <span>💬</span>
                            <span>{chip}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                  </div>
                )}

                {/* Chat Thread */}
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
                  >
                    {msg.sender === "user" ? (
                      <div 
                        className={`max-w-[70%] bg-slate-900 text-white rounded-2xl rounded-tr-sm px-5 py-2.5 text-xs md:text-sm leading-relaxed shadow-sm ${
                          isArabic(msg.text) ? "text-right font-sans" : ""
                        }`}
                        dir={isArabic(msg.text) ? "rtl" : "ltr"}
                      >
                        {msg.text}
                      </div>
                    ) : (
                      <div className="w-full flex items-start gap-4">
                        <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0 shadow-sm mt-1">
                          <Scale className="w-4 h-4" />
                        </div>
                        
                        <div className="flex-1 space-y-5">
                          {/* Accordions for briefs */}
                          {(msg.agent1Brief || msg.agent2Brief) && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-start">
                              {msg.agent1Brief && (
                                <div className="border border-slate-200/80 rounded-xl overflow-hidden bg-white shadow-sm">
                                  <button
                                    onClick={() => toggleBrief(`${msg.id}_1`)}
                                    className="w-full px-3.5 py-2 bg-slate-50 flex justify-between items-center text-[10px] font-bold text-slate-700 hover:bg-slate-100/60"
                                  >
                                    <span className="flex items-center gap-1.5">
                                      <Terminal className="w-3.5 h-3.5 text-blue-600" /> Agent 1: Local DB Retrieval
                                    </span>
                                    <span>{openBriefs[`${msg.id}_1`] ? "▲" : "▼"}</span>
                                  </button>
                                  {openBriefs[`${msg.id}_1`] && (
                                    <div className="max-h-96 overflow-y-auto border-t border-slate-100">
                                      <div className="p-3.5 text-[10px] text-slate-500 whitespace-pre-line leading-relaxed font-mono">
                                        {msg.agent1Brief}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}
                              {msg.agent2Brief && (
                                <div className="border border-slate-200/80 rounded-xl overflow-hidden bg-white shadow-sm">
                                  <button
                                    onClick={() => toggleBrief(`${msg.id}_2`)}
                                    className="w-full px-3.5 py-2 bg-slate-50 flex justify-between items-center text-[10px] font-bold text-slate-700 hover:bg-slate-100/60"
                                  >
                                    <span className="flex items-center gap-1.5">
                                      <Globe className="w-3.5 h-3.5 text-blue-600" /> Agent 2: Web Compliance
                                    </span>
                                    <span>{openBriefs[`${msg.id}_2`] ? "▲" : "▼"}</span>
                                  </button>
                                  {openBriefs[`${msg.id}_2`] && (
                                    <div className="max-h-96 overflow-y-auto border-t border-slate-100">
                                      <div className="p-3.5 text-[10px] text-slate-500 whitespace-pre-line leading-relaxed font-mono">
                                        {msg.agent2Brief}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Main answer text */}
                          <div className="bg-white rounded-2xl border border-slate-100 p-5 shadow-sm space-y-4">
                            {/* Beautiful Source Cards (Perplexity Style) */}
                            {msg.resources && msg.resources.length > 0 && (
                              <div className="space-y-2 border-b border-slate-100 pb-4">
                                <div className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase tracking-wider">
                                  <BookOpen className="w-3.5 h-3.5 text-blue-500" />
                                  <span>Sources & Official Resources</span>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
                                  {msg.resources.map((res, idx) => {
                                    const absoluteUrl = res.url && (res.url.startsWith("http://") || res.url.startsWith("https://"))
                                      ? res.url
                                      : `https://${res.url}`;
                                    let domain = "";
                                    try {
                                      domain = new URL(absoluteUrl).hostname.replace("www.", "");
                                    } catch (e) {
                                      domain = res.url;
                                    }
                                    const isArSnippet = isArabic(res.snippet || "") || isArabic(res.title || "");
                                    return (
                                      <a
                                        key={idx}
                                        href={absoluteUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex flex-col justify-between p-3 rounded-xl border border-slate-200/70 bg-slate-50/50 hover:bg-slate-100/60 hover:border-slate-300 transition-all duration-200 text-left group shadow-xs h-full min-h-[110px]"
                                      >
                                        <div className="space-y-1.5 w-full">
                                          <div className="flex items-center justify-between gap-1.5 mb-1">
                                            <span className="text-[10px] font-bold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded-md border border-blue-100 shrink-0">
                                              {idx + 1}
                                            </span>
                                            <span className="text-[9px] font-semibold text-slate-400 group-hover:text-slate-600 transition-colors truncate">
                                              {domain}
                                            </span>
                                          </div>
                                          <span className={`block text-xs font-extrabold text-slate-800 leading-snug truncate group-hover:text-blue-600 transition-colors ${isArSnippet ? "text-right font-sans" : ""}`} dir={isArSnippet ? "rtl" : "ltr"}>
                                            {res.title}
                                          </span>
                                          {res.snippet && (
                                            <p className={`text-[11px] text-slate-500 leading-relaxed line-clamp-3 mt-1 font-normal ${isArSnippet ? "text-right font-sans" : ""}`} dir={isArSnippet ? "rtl" : "ltr"}>
                                              {res.snippet}
                                            </p>
                                          )}
                                        </div>
                                      </a>
                                    );
                                  })}
                                </div>
                              </div>
                            )}
                            {/* Gazette Citations (Official Bulletins / SQLite records) */}
                            {msg.citations && msg.citations.length > 0 && (
                              <div className="space-y-2 border-b border-slate-100 pb-4">
                                <div className="flex items-center gap-1.5 text-xs font-bold text-slate-500 uppercase tracking-wider">
                                  <Layers className="w-3.5 h-3.5 text-emerald-500" />
                                  <span>Official Gazettes & Bulletins</span>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
                                  {msg.citations.map((cit, idx) => {
                                    const lang = cit.metadata?.language || "FR";
                                    const year = cit.metadata?.year || "Unknown";
                                    const bulletin = cit.metadata?.bulletin || "";
                                    const isArCit = isArabic(cit.content || "") || isArabic(cit.title || "") || isArabic(cit.provision_ref || "");
                                    return (
                                      <button
                                        key={idx}
                                        onClick={() => setSelectedCitation(cit)}
                                        className="flex flex-col justify-between p-3 rounded-xl border border-slate-200/70 bg-white hover:bg-emerald-50/40 hover:border-emerald-300 transition-all duration-200 text-left group shadow-xs cursor-pointer h-full min-h-[115px]"
                                      >
                                        <div className="space-y-1.5 w-full">
                                          <div className="flex items-center justify-between gap-1.5 mb-1 w-full">
                                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md border shrink-0 ${
                                              isArCit ? "bg-emerald-50 text-emerald-700 border-emerald-200/60" : "bg-blue-50 text-blue-700 border-blue-200/60"
                                            }`}>
                                              {cit.provision_ref}
                                            </span>
                                            <span className="text-[9px] font-semibold text-slate-400 group-hover:text-slate-600 transition-colors truncate">
                                              {year} · {bulletin.replace("BO_", "").replace("_Fr", "").replace("_Ar", "")}
                                            </span>
                                          </div>
                                          <span className={`block text-xs font-extrabold text-slate-800 leading-snug truncate group-hover:text-emerald-600 transition-colors ${isArCit ? "text-right font-sans" : ""}`} dir={isArCit ? "rtl" : "ltr"}>
                                            {cit.title || cit.document_id}
                                          </span>
                                          {cit.content && (
                                            <p className={`text-[11px] text-slate-500 leading-relaxed line-clamp-3 mt-1 font-normal ${isArCit ? "text-right font-sans" : ""}`} dir={isArCit ? "rtl" : "ltr"}>
                                              {cit.content}
                                            </p>
                                          )}
                                        </div>
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>
                            )}

                            <div className="prose prose-slate max-w-none text-slate-700">
                              {renderContent(msg.text)}
                            </div>
                            
                            {/* Reference / Action Bar */}
                            <div className="flex items-center justify-between border-t border-slate-100 pt-3 text-[11px] text-slate-400">
                              <span>Jurisprudence Synthesizer Node active</span>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => copyToClipboard(msg.text, msg.id)}
                                className="h-7 text-xs text-slate-400 hover:text-slate-700 flex items-center gap-1.5 px-2 hover:bg-slate-100"
                              >
                                {copiedId === msg.id ? (
                                  <>
                                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                                    Copied
                                  </>
                                ) : (
                                  <>
                                    <Copy className="w-3.5 h-3.5" />
                                    Copy Advice
                                  </>
                                )}
                              </Button>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}

                {/* Streaming Node visualizer */}
                {agentState.status === "running" && (
                  <div className="flex flex-col gap-4">
                    {renderPipelineSVG(agentState)}

                    {/* Log drawer */}
                    <div className="bg-slate-50/50 rounded-2xl p-4 border border-slate-100 shadow-sm">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                          <Cpu className="w-3.5 h-3.5 text-blue-500 animate-spin" />
                          Pipeline Monitor
                        </span>
                        <Badge className="bg-blue-100/55 text-blue-700 border-none text-[9px] px-2 py-0.5">
                          Processing
                        </Badge>
                      </div>
                      <p className="text-[11px] text-slate-600 font-mono italic pl-2.5 border-l-2 border-blue-500 py-0.5">
                        {agentState.currentMessage}
                      </p>
                    </div>

                    {/* Floating briefs */}
                    {(activeAgent1Brief || activeAgent2Brief) && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 items-start">
                        {activeAgent1Brief && (
                          <div className="border border-slate-200/80 rounded-xl overflow-hidden bg-white shadow-sm">
                            <button
                              onClick={() => toggleBrief("active_1")}
                              className="w-full px-3 py-2 bg-slate-50 flex justify-between items-center text-[9px] font-bold text-slate-600"
                            >
                              <span>🔍 Agent 1 Brief Available</span>
                              <span>{openBriefs["active_1"] ? "▲" : "▼"}</span>
                            </button>
                            {openBriefs["active_1"] && (
                              <div className="max-h-80 overflow-y-auto border-t border-slate-100">
                                <div className="p-3 text-[9px] text-slate-500 whitespace-pre-line leading-relaxed font-mono">
                                  {activeAgent1Brief}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                        {activeAgent2Brief && (
                          <div className="border border-slate-200/80 rounded-xl overflow-hidden bg-white shadow-sm">
                            <button
                              onClick={() => toggleBrief("active_2")}
                              className="w-full px-3 py-2 bg-slate-50 flex justify-between items-center text-[9px] font-bold text-slate-600"
                            >
                              <span>🌐 Agent 2 Brief Available</span>
                              <span>{openBriefs["active_2"] ? "▲" : "▼"}</span>
                            </button>
                            {openBriefs["active_2"] && (
                              <div className="max-h-80 overflow-y-auto border-t border-slate-100">
                                <div className="p-3 text-[9px] text-slate-500 whitespace-pre-line leading-relaxed font-mono">
                                  {activeAgent2Brief}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* Error Message */}
                {agentState.status === "error" && (
                  <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl p-4 flex items-start gap-3 max-w-2xl">
                    <HelpCircle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" />
                    <div className="space-y-0.5">
                      <p className="text-xs font-bold">Inquiry Interrupted</p>
                      <p className="text-[11px] font-mono leading-relaxed">{agentState.currentMessage}</p>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>
            </ScrollArea>

            {/* ─── Bottom Floating Console Dock (Askk UI inspired input console) ─── */}
            <footer className="p-6 bg-white border-t border-slate-100 shrink-0">
              <div className="max-w-3xl mx-auto">
                
                {/* Rounded Input dock */}
                <div className="askk-input-dock rounded-2xl p-2.5 flex flex-col gap-2">
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      handleSearch(query);
                    }}
                    className="flex items-center gap-2"
                  >
                    <Input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="Ask me anything..."
                      disabled={agentState.status === "running"}
                      className="flex-1 bg-transparent border-transparent text-slate-800 placeholder:text-slate-400 text-xs md:text-sm h-10 px-2 focus-visible:ring-0 focus-visible:border-transparent"
                    />
                    <Button
                      type="submit"
                      disabled={agentState.status === "running" || !query.trim()}
                      className="bg-slate-900 hover:bg-slate-800 text-white rounded-xl w-10 h-10 p-0 flex items-center justify-center shrink-0 disabled:opacity-30 cursor-pointer shadow-sm"
                    >
                      {agentState.status === "running" ? (
                        <span className="w-3.5 h-3.5 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                      ) : (
                        <ArrowUp className="w-4 h-4 text-white" />
                      )}
                    </Button>
                  </form>

                  {/* Input console footer pills */}
                  <div className="flex items-center justify-between border-t border-slate-100 pt-2 px-1 text-[10px] text-slate-400">
                    <div className="flex items-center gap-2">
                      <button className="flex items-center gap-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200/80 px-2.5 py-1 rounded-lg font-bold text-slate-600 transition-colors">
                        <Sparkles className="w-3 h-3 text-blue-500" />
                        Active Pipeline
                      </button>
                      <button className="flex items-center gap-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200/80 px-2.5 py-1 rounded-lg font-bold text-slate-600 transition-colors">
                        <Paperclip className="w-3 h-3" />
                        FTS5 Search
                      </button>
                    </div>
                    <span className="text-[9px] text-slate-400 font-medium">Verify legal findings in BO circulars</span>
                  </div>
                </div>

              </div>
            </footer>
          </>
        ) : (
                          /* Database Analytics View */
                          <ScrollArea className="flex-1 min-h-0 bg-slate-50/50">

            {loadingStats ? (
              <div className="flex-1 flex items-center justify-center min-h-[500px]">
                <div className="flex flex-col items-center gap-2">
                  <span className="w-8 h-8 border-3 border-slate-200 border-t-slate-900 rounded-full animate-spin" />
                  <span className="text-xs font-bold text-slate-400">Loading database analytics...</span>
                </div>
              </div>
            ) : !stats ? (
              <div className="flex-1 flex items-center justify-center min-h-[500px]">
                <div className="text-center p-8 space-y-2">
                  <BarChart3 className="w-8 h-8 text-slate-300 mx-auto" />
                  <p className="text-slate-400 text-xs font-medium">Failed to load statistics.</p>
                </div>
              </div>
            ) : (
              <div className="p-8 max-w-5xl mx-auto space-y-8 pb-12">
                <div className="space-y-1">
                  <h1 className="text-2xl font-black text-slate-800 tracking-tight">Database Analytics</h1>
                  <p className="text-slate-400 text-xs md:text-sm font-medium">
                    Aggregated statistical insights compiled from active codifications, bulletins, and amendments.
                  </p>
                </div>

                {/* Metrics Grid */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  {/* Metric 1 */}
                  <Card className="border-slate-100 shadow-sm bg-white overflow-hidden relative">
                    <CardContent className="p-5 flex items-center justify-between">
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total Documents</span>
                        <p className="text-2xl font-black text-slate-800">{stats.total_documents.toLocaleString()}</p>
                      </div>
                      <div className="w-10 h-10 rounded-xl bg-blue-50 border border-blue-100/50 flex items-center justify-center text-blue-600">
                        <Layers className="w-5 h-5" />
                      </div>
                    </CardContent>
                  </Card>

                  {/* Metric 2 */}
                  <Card className="border-slate-100 shadow-sm bg-white overflow-hidden relative">
                    <CardContent className="p-5 flex items-center justify-between">
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total Provisions</span>
                        <p className="text-2xl font-black text-slate-800">{stats.total_provisions.toLocaleString()}</p>
                      </div>
                      <div className="w-10 h-10 rounded-xl bg-emerald-50 border border-emerald-100/50 flex items-center justify-center text-emerald-600">
                        <Scale className="w-5 h-5" />
                      </div>
                    </CardContent>
                  </Card>

                  {/* Metric 3 */}
                  <Card className="border-slate-100 shadow-sm bg-white overflow-hidden relative">
                    <CardContent className="p-5 flex items-center justify-between">
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Avg provisions / doc</span>
                        <p className="text-2xl font-black text-slate-800">
                          {(stats.total_provisions / stats.total_documents).toFixed(1)}
                        </p>
                      </div>
                      <div className="w-10 h-10 rounded-xl bg-purple-50 border border-purple-100/50 flex items-center justify-center text-purple-600">
                        <BookOpen className="w-5 h-5" />
                      </div>
                    </CardContent>
                  </Card>

                  {/* Metric 4 */}
                  <Card className="border-slate-100 shadow-sm bg-white overflow-hidden relative">
                    <CardContent className="p-5 flex items-center justify-between">
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Unique Bulletins</span>
                        <p className="text-2xl font-black text-slate-800">538</p>
                      </div>
                      <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-100/50 flex items-center justify-center text-amber-600">
                        <Database className="w-5 h-5" />
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Years Timeline Chart */}
                <Card className="border-slate-100 bg-white shadow-sm">
                  <CardContent className="p-6 space-y-6">
                    <div className="flex items-center justify-between border-b border-slate-50 pb-4">
                      <h3 className="text-sm font-bold text-slate-800">Historical Distribution (Timeline 2000 - 2026)</h3>
                      <span className="text-[10px] font-bold text-slate-400">Total provisions mapped by bulletin year</span>
                    </div>

                    {(() => {
                      const yearStats = stats.years_distribution.filter((y: any) => y.year !== "Unknown" && y.year !== "0");
                      const maxCount = Math.max(...yearStats.map((y: any) => y.count), 1);
                      return (
                        <div className="h-48 flex items-end justify-between gap-1.5 pt-6 relative border-b border-slate-100 px-2">
                          {yearStats.map((item: any, idx: number) => {
                            const heightPct = (item.count / maxCount) * 100;
                            return (
                              <div key={idx} className="flex-1 flex flex-col items-center group relative h-full justify-end">
                                {/* Tooltip */}
                                <div className="absolute bottom-full mb-1 opacity-0 group-hover:opacity-100 transition-opacity bg-slate-900 text-white text-[9px] font-bold py-1 px-2 rounded pointer-events-none shadow-sm z-20 whitespace-nowrap">
                                  {item.year}: {item.count.toLocaleString()} articles
                                </div>
                                {/* Visual Bar */}
                                <div
                                  style={{ height: `${heightPct}%` }}
                                  className="w-full bg-gradient-to-t from-blue-500/80 to-blue-400 rounded-t-sm hover:from-blue-600 hover:to-blue-500 transition-all duration-300"
                                />
                                {/* Label */}
                                <span className="text-[9px] font-bold text-slate-400 mt-2 truncate w-full text-center hidden md:inline">
                                  {item.year.slice(-2)}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      );
                    })()}
                  </CardContent>
                </Card>

                {/* Bottom Row */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Language Card */}
                  <Card className="border-slate-100 bg-white shadow-sm">
                    <CardContent className="p-6 space-y-6">
                      <div className="flex items-center justify-between border-b border-slate-50 pb-4">
                        <h3 className="text-sm font-bold text-slate-800">Language Coverage</h3>
                        <span className="text-[10px] font-bold text-slate-400">Metadata language tags</span>
                      </div>
                      
                      <div className="space-y-4">
                        {Object.entries(stats.language_distribution).map(([lang, count]: any) => {
                          const pct = ((count / stats.total_provisions) * 100).toFixed(1);
                          return (
                            <div key={lang} className="space-y-1.5">
                              <div className="flex justify-between text-xs font-bold text-slate-700">
                                <span>{lang === "FR" ? "French (FR)" : lang === "AR" ? "Arabic (AR)" : lang}</span>
                                <span>{count.toLocaleString()} articles ({pct}%)</span>
                              </div>
                              <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                                <div
                                  style={{ width: `${pct}%` }}
                                  className={`h-full rounded-full ${lang === "FR" ? "bg-blue-500" : lang === "AR" ? "bg-emerald-500" : "bg-slate-400"}`}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </CardContent>
                  </Card>

                  {/* Largest Codes Card */}
                  <Card className="border-slate-100 bg-white shadow-sm">
                    <CardContent className="p-6 space-y-4">
                      <div className="flex items-center justify-between border-b border-slate-50 pb-2">
                        <h3 className="text-sm font-bold text-slate-800">Largest Codes & Statutes</h3>
                        <span className="text-[10px] font-bold text-slate-400">Top 5 by provision count</span>
                      </div>

                      <div className="space-y-3.5">
                        {stats.top_documents.map((doc: any, idx: number) => (
                          <div key={idx} className="flex items-center justify-between border-b border-slate-100/50 pb-2 last:border-0 last:pb-0">
                            <div className="space-y-0.5 pr-4">
                              <p className="text-xs font-extrabold text-slate-800 line-clamp-1">{doc.title}</p>
                              <p className="text-[9px] font-mono text-slate-400">{doc.id}</p>
                            </div>
                            <span className="text-xs font-black text-blue-600 bg-blue-50 border border-blue-100/50 px-2 py-0.5 rounded shrink-0">
                              {doc.provision_count} articles
                            </span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </div>

              </div>
            )}
          </ScrollArea>
        )}
      </main>
      {/* ─── PDF Viewer Modal (Overlay Dialog) ─── */}
      {selectedCitation && (() => {
        const lang = modalMetadata?.language || selectedCitation.metadata?.language || "FR";
        const year = modalMetadata?.year || selectedCitation.metadata?.year || "Unknown";
        let bulletin = modalMetadata?.bulletin || selectedCitation.metadata?.bulletin || "";
        
        const pagesRaw = modalMetadata?.pages || selectedCitation.metadata?.pages || "1";
        const firstPageMatch = pagesRaw.toString().match(/\d+/);
        const pageNum = firstPageMatch ? firstPageMatch[0] : "1";
        
        const activeLang = modalLang || lang;
        const activePage = modalPageNum || pageNum;
        const activeContent = modalContent || selectedCitation.content;
        const activeDocId = modalDocId || selectedCitation.document_id;
        const activeProvisionRef = modalProvisionRef || selectedCitation.provision_ref;
        
        let activeBulletin = bulletin;
        if (activeLang === "AR") {
          activeBulletin = bulletin.replace("_Fr", "_Ar").replace("_fr", "_Ar");
        } else {
          activeBulletin = bulletin.replace("_Ar", "_Fr").replace("_ar", "_Fr");
        }
        
        const pdfUrl = activeDocId === "ma-adala-family-118"
          ? `http://localhost:8000/api/pdf-view?lang=ar&year=special&bulletin=moudawana`
          : `http://localhost:8000/api/pdf-view?lang=${activeLang.toLowerCase()}&year=${year}&bulletin=${activeBulletin}#page=${activePage}`;
        
        return (
          <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl w-full max-w-5xl h-[85vh] flex flex-col shadow-2xl border border-slate-100 overflow-hidden">
              
              {/* Modal Header */}
              <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-extrabold text-blue-600 bg-blue-50 px-2 py-0.5 rounded border border-blue-100">
                      {activeProvisionRef}
                    </span>
                    <span className="text-xs font-bold text-slate-400">
                      BO Gazette Record ({activeLang})
                    </span>
                  </div>
                  <h3 className="text-sm font-extrabold text-slate-800 line-clamp-1">
                    {activeDocId === "ma-adala-real-estate-128" ? "ظهير متعلق بالتحفيظ العقاري" : (selectedCitation.title || activeDocId)}
                  </h3>
                </div>
                <button
                  onClick={() => setSelectedCitation(null)}
                  className="w-8 h-8 rounded-full bg-slate-200/50 hover:bg-slate-200 flex items-center justify-center text-slate-500 hover:text-slate-700 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              
              {/* Modal Split View */}
              <div className="flex-1 flex min-h-0 divide-x divide-slate-100">
                {/* Left side: Clean text description */}
                <div className="w-1/2 p-6 overflow-y-auto space-y-4 bg-slate-50/30">
                  <div className="space-y-1">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                      Clean Text Preview
                    </span>
                    <h4 className="text-xs font-bold text-slate-700">{activeProvisionRef} Content</h4>
                  </div>
                  {activeContent?.startsWith("[SCAN_ONLY]") ? (
                    <div className="bg-amber-50 border border-amber-200/60 rounded-xl p-4 shadow-sm space-y-2">
                      <div className="flex items-center gap-2 text-amber-700">
                        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span className="text-xs font-bold">النص العربي غير مُفهرَس بعد</span>
                      </div>
                      <p className="text-xs text-amber-600 leading-relaxed font-medium" dir="rtl">
                        النص الكامل لهذه المادة متاح في الطبعة الرسمية العربية للجريدة الرسمية. استخدم عارض PDF على اليمين للاطلاع على النص الأصلي.
                      </p>
                      <p className="text-[10px] text-amber-500 font-medium">
                        Arabic text not yet extracted — the official Arabic scan is available in the PDF viewer on the right.
                      </p>
                    </div>
                  ) : (
                    <p
                      className={`text-xs text-slate-600 leading-relaxed whitespace-pre-wrap bg-white border border-slate-200/60 rounded-xl p-4 shadow-sm font-medium ${
                        isArabic(activeContent) ? "text-right font-sans" : ""
                      }`}
                      dir={isArabic(activeContent) ? "rtl" : "ltr"}
                    >
                      {activeContent}
                    </p>
                  )}
                  
                  {/* Metadata tags */}
                  <div className="bg-white border border-slate-200/60 rounded-xl p-4 shadow-sm space-y-2">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">
                      Metadata Attributes
                    </span>
                    <div className="grid grid-cols-2 gap-2 text-[10px] font-bold text-slate-500">
                      <div className="bg-slate-50 p-2 rounded col-span-2">Document ID: <span className="text-slate-800 font-mono text-[9px] block mt-0.5">{activeDocId}</span></div>
                      <div className="bg-slate-50 p-2 rounded">Year: <span className="text-slate-800">{year}</span></div>
                      <div className="bg-slate-50 p-2 rounded">Bulletin: <span className="text-slate-800">{activeBulletin.replace("BO_", "")}</span></div>
                      <div className="bg-slate-50 p-2 rounded">Language: <span className="text-slate-800">{activeLang}</span></div>
                      <div className="bg-slate-50 p-2 rounded">Page target: <span className="text-slate-800">Page {activePage}</span></div>
                    </div>
                  </div>
                </div>
                
                {/* Right side: Interactive PDF iframe or Online Lookup Panel */}
                <div className="w-1/2 h-full bg-slate-50 flex flex-col relative p-6 pt-14">
                  {(activeDocId.startsWith("BO_") || (bulletin && /^\d/.test(bulletin)) || activeDocId === "ma-adala-real-estate-128") && (
                    <div className="absolute top-3 right-6 z-20 flex items-center gap-2 bg-white/80 backdrop-blur-xs p-1 rounded-xl border border-slate-200/80 shadow-xs">
                      <button
                        onClick={() => toggleModalLanguage("FR")}
                        className={`px-3 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer ${
                          activeLang === "FR"
                            ? "bg-slate-900 text-white shadow-sm"
                            : "bg-transparent text-slate-500 hover:text-slate-800"
                        }`}
                      >
                        Français
                      </button>
                      <button
                        onClick={() => toggleModalLanguage("AR")}
                        className={`px-3 py-1 rounded-lg text-[10px] font-bold transition-all cursor-pointer ${
                          activeLang === "AR"
                            ? "bg-slate-900 text-white shadow-sm"
                            : "bg-transparent text-slate-500 hover:text-slate-800"
                        }`}
                      >
                        العربية
                      </button>
                    </div>
                  )}
                  {activeDocId === "ma-adala-family-118" || (year !== "Unknown" && bulletin !== "") ? (
                    <div className="w-full h-full relative flex-1">
                      {loadingModalPage && (
                        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-slate-400 bg-white/70 z-30 rounded-xl">
                          <span className="w-6 h-6 border-2 border-slate-300 border-t-slate-500 rounded-full animate-spin" />
                          <span className="text-[10px] font-medium">Syncing page translation...</span>
                        </div>
                      )}
                      <iframe 
                        key={pdfUrl}
                        src={pdfUrl} 
                        className="w-full h-full border-0 z-10 bg-white rounded-xl border border-slate-200/60 shadow-sm"
                        title="Moroccan Official Bulletin PDF Viewer"
                      />
                    </div>
                  ) : (
                    <div className="max-w-md w-full text-center space-y-5 bg-white border border-slate-200/60 rounded-2xl p-6 shadow-sm">
                      <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center mx-auto text-blue-500">
                        <Search className="w-5 h-5" />
                      </div>
                      <div className="space-y-1">
                        <h4 className="text-sm font-extrabold text-slate-800">Recherche & Consultation en Ligne</h4>
                        <p className="text-[11px] text-slate-500 leading-relaxed font-medium">
                          Ce document provient de notre base de données consolidée. Aucun scan PDF local n'est disponible. Vous pouvez effectuer une recherche en ligne à l'aide des références ci-dessous.
                        </p>
                      </div>
                      
                      {/* Recommended Search Query */}
                      <div className="bg-slate-50 border border-slate-100 rounded-xl p-3 text-left space-y-1 relative group">
                        <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">Requête de recherche</span>
                        <div className="text-xs font-semibold text-slate-700 font-mono break-all pr-8">
                          {selectedCitation.title || activeDocId}
                        </div>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(selectedCitation.title || activeDocId);
                            setCopiedId("citation-query");
                            setTimeout(() => setCopiedId(null), 2000);
                          }}
                          className="absolute right-2.5 bottom-2.5 w-6 h-6 rounded-md bg-white border border-slate-200 flex items-center justify-center text-slate-500 hover:text-slate-700 shadow-2xs hover:border-slate-300 transition-all cursor-pointer"
                          title="Copier la requête"
                        >
                          {copiedId === "citation-query" ? (
                            <Check className="w-3.5 h-3.5 text-emerald-500" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>

                      {/* Useful Official Links */}
                      <div className="space-y-2 text-left">
                        <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider block">Portails officiels recommandés</span>
                        <div className="grid grid-cols-1 gap-2">
                          <a
                            href="https://www.sgg.gov.ma/BulletinOfficiel.aspx"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-between p-2.5 rounded-xl border border-slate-200/60 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-300 transition-colors text-xs font-bold text-slate-700 group"
                          >
                            <span className="truncate group-hover:text-blue-600 transition-colors">SGG - Bulletins Officiels</span>
                            <span className="text-[10px] text-slate-400 group-hover:text-slate-600 font-medium">sgg.gov.ma →</span>
                          </a>
                          <a
                            href="https://www.sgg.gov.ma/Legislation.aspx"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-between p-2.5 rounded-xl border border-slate-200/60 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-300 transition-colors text-xs font-bold text-slate-700 group"
                          >
                            <span className="truncate group-hover:text-blue-600 transition-colors">SGG - Législation consolidée</span>
                            <span className="text-[10px] text-slate-400 group-hover:text-slate-600 font-medium">sgg.gov.ma →</span>
                          </a>
                          <a
                            href="https://www.justice.gov.ma"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-between p-2.5 rounded-xl border border-slate-200/60 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-300 transition-colors text-xs font-bold text-slate-700 group"
                          >
                            <span className="truncate group-hover:text-blue-600 transition-colors">Portail Adala (Ministère de la Justice)</span>
                            <span className="text-[10px] text-slate-400 group-hover:text-slate-600 font-medium">justice.gov.ma →</span>
                          </a>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
              
            </div>
          </div>
        );
      })()}
    </div>
  );
}
