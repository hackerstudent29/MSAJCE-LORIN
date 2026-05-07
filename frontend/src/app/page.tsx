"use client";

import { useState, useEffect, useRef } from "react";
import { 
  Send, 
  Bot, 
  User, 
  Sparkles, 
  MessageSquare, 
  Clock, 
  ChevronRight,
  Bus,
  School,
  BookOpen,
  HelpCircle,
  Menu,
  X
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// Utility for tailwind classes
function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type Message = {
  id: string;
  role: "user" | "bot";
  content: string;
  timestamp: Date;
};

const QUICK_ACTIONS = [
  { icon: Bus, label: "Transport Routes", query: "What are the bus routes for Tambaram?" },
  { icon: School, label: "Departments", query: "List all 12 departments in MSAJCE" },
  { icon: Sparkles, label: "Admission 2024", query: "Tell me about admission details for 2024 batch" },
  { icon: BookOpen, label: "Scholarships", query: "What scholarships are available for students?" },
];

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async (query?: string) => {
    const text = query || input;
    if (!text.trim() || isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });

      const data = await response.json();
      
      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "bot",
        content: data.response || "I'm sorry, I encountered an error. Please try again.",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, botMsg]);
    } catch (error) {
      console.error("Chat Error:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-background overflow-hidden font-sans">
      {/* Mobile Menu Toggle */}
      <button 
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className="fixed top-4 left-4 z-50 p-2 rounded-lg bg-muted md:hidden"
      >
        {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Sidebar */}
      <AnimatePresence mode="wait">
        {isSidebarOpen && (
          <motion.aside
            initial={{ x: -300, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -300, opacity: 0 }}
            className="w-72 border-r border-border bg-card/50 backdrop-blur-xl flex flex-col z-40 fixed inset-y-0 left-0 md:relative"
          >
            <div className="p-6">
              <div className="flex items-center gap-3 mb-8">
                <div className="w-10 h-10 rounded-xl bg-accent flex items-center justify-center text-white shadow-lg">
                  <Bot size={24} />
                </div>
                <div>
                  <h1 className="font-bold text-lg tracking-tight">LORIN AI</h1>
                  <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-medium">Institutional Assistant</p>
                </div>
              </div>

              <button 
                onClick={() => setMessages([])}
                className="w-full py-3 px-4 rounded-xl border border-dashed border-muted-foreground/30 hover:border-accent hover:bg-accent/5 transition-all flex items-center gap-3 text-sm font-medium mb-6"
              >
                <Sparkles size={16} className="text-accent" />
                New Conversation
              </button>

              <div className="space-y-1">
                <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-widest mb-3 px-2">Quick Access</p>
                {QUICK_ACTIONS.map((action, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(action.query)}
                    className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-muted/50 transition-colors text-sm group"
                  >
                    <action.icon size={18} className="text-muted-foreground group-hover:text-accent transition-colors" />
                    <span className="truncate">{action.label}</span>
                    <ChevronRight size={14} className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-auto p-6 border-t border-border">
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                System Operational
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Main Chat Area */}
      <main className="flex-1 flex flex-col relative bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-900 via-background to-background">
        {/* Header */}
        <header className="h-16 flex items-center px-8 border-b border-white/5 backdrop-blur-md z-30">
          <div className="flex items-center gap-3">
             <div className="text-xs font-semibold px-2 py-1 rounded bg-accent/10 text-accent border border-accent/20">
              BETA v2.0
            </div>
          </div>
        </header>

        {/* Messages */}
        <div 
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-4 md:p-8 space-y-8 scroll-smooth"
        >
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center space-y-6 max-w-2xl mx-auto">
              <div className="w-20 h-20 rounded-3xl bg-accent/10 flex items-center justify-center text-accent mb-4 animate-bounce">
                <Sparkles size={40} />
              </div>
              <h2 className="text-4xl font-bold tracking-tight">How can I assist you today?</h2>
              <p className="text-muted-foreground text-lg">
                I am LORIN, your official MSAJCE assistant. Ask me about departments, transport, admissions, or campus rules.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full mt-8">
                {QUICK_ACTIONS.slice(0, 2).map((a, i) => (
                  <button 
                    key={i}
                    onClick={() => handleSend(a.query)}
                    className="p-4 rounded-2xl glass-card text-left hover:border-accent/50 transition-all group"
                  >
                    <p className="font-bold text-sm mb-1 group-hover:text-accent">{a.label}</p>
                    <p className="text-xs text-muted-foreground line-clamp-1">{a.query}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <motion.div
                initial={{ y: 20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                key={msg.id}
                className={cn(
                  "flex gap-4 max-w-4xl mx-auto w-full",
                  msg.role === "user" ? "flex-row-reverse" : "flex-row"
                )}
              >
                <div className={cn(
                  "w-10 h-10 rounded-xl flex items-center justify-center shrink-0 shadow-lg",
                  msg.role === "user" ? "bg-slate-700 text-white" : "bg-accent text-white"
                )}>
                  {msg.role === "user" ? <User size={20} /> : <Bot size={20} />}
                </div>
                <div className={cn(
                  "relative group",
                  msg.role === "user" ? "chat-bubble-user" : "chat-bubble-bot"
                )}>
                  <div className="prose prose-invert max-w-none whitespace-pre-wrap">
                    {msg.content}
                  </div>
                  <div className={cn(
                    "absolute -bottom-6 text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity",
                    msg.role === "user" ? "right-0" : "left-0"
                  )}>
                    {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              </motion.div>
            ))
          )}
          {isLoading && (
            <div className="flex gap-4 max-w-4xl mx-auto w-full">
              <div className="w-10 h-10 rounded-xl bg-accent flex items-center justify-center text-white shrink-0">
                <Bot size={20} />
              </div>
              <div className="chat-bubble-bot flex items-center gap-2">
                <div className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:-0.3s]" />
                <div className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce [animation-delay:-0.15s]" />
                <div className="w-1.5 h-1.5 bg-accent rounded-full animate-bounce" />
              </div>
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="p-6 md:p-10 border-t border-white/5 bg-background/80 backdrop-blur-md">
          <div className="max-w-4xl mx-auto relative group">
            <div className="absolute -inset-1 bg-gradient-to-r from-accent to-blue-600 rounded-[22px] blur opacity-20 group-focus-within:opacity-40 transition-opacity" />
            <div className="relative flex items-center bg-card border border-border rounded-[20px] p-2 pr-4 shadow-2xl">
              <input
                type="text"
                placeholder="Message LORIN..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                className="flex-1 bg-transparent border-none focus:ring-0 px-4 py-3 text-sm"
              />
              <button 
                onClick={() => handleSend()}
                disabled={!input.trim() || isLoading}
                className="w-10 h-10 rounded-xl bg-accent text-white flex items-center justify-center hover:scale-105 active:scale-95 disabled:opacity-50 disabled:hover:scale-100 transition-all shadow-lg shadow-accent/20"
              >
                <Send size={18} />
              </button>
            </div>
            <p className="text-[10px] text-center mt-3 text-muted-foreground font-medium">
              LORIN can make mistakes. Check important info about departments and routes.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
