"use client";

import { useState, useEffect, useRef } from "react";
import { 
  Send, 
  Plus, 
  MessageSquare, 
  User, 
  Bot, 
  Settings, 
  LogOut,
  ExternalLink,
  ChevronDown,
  Sparkles,
  Search,
  PanelLeftClose,
  PanelLeftOpen
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type Message = {
  id: string;
  role: "user" | "bot";
  content: string;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (query?: string) => {
    const text = query || input;
    if (!text.trim() || isLoading) return;

    const userMsg: Message = { id: Date.now().toString(), role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      // PRO TIP: Replace with your actual Bot URL for production
      const BACKEND_URL = "/api/chat";
      
      const response = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });

      const data = await response.json();
      const botMsg: Message = { 
        id: (Date.now() + 1).toString(), 
        role: "bot", 
        content: data.response || "I encountered an error. Please check your connection." 
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (error) {
      console.error("Chat Error:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      {/* SIDEBAR */}
      <AnimatePresence mode="wait">
        {isSidebarOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 260, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            className="bg-[#171717] flex flex-col h-full overflow-hidden shrink-0"
          >
            <div className="p-3 flex flex-col h-full">
              {/* New Chat Button */}
              <button 
                onClick={() => setMessages([])}
                className="flex items-center justify-between w-full p-3 rounded-lg hover:bg-[#2f2f2f] transition-colors group mb-4"
              >
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-full bg-white flex items-center justify-center text-black">
                    <Plus size={16} strokeWidth={3} />
                  </div>
                  <span className="text-sm font-medium text-white">New Chat</span>
                </div>
                <MessageSquare size={16} className="text-zinc-500 group-hover:text-zinc-300" />
              </button>

              {/* History Placeholder */}
              <div className="flex-1 overflow-y-auto space-y-1">
                <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest px-3 mb-2">History</p>
                <div className="sidebar-item group">
                  <MessageSquare size={16} />
                  <span className="truncate">MSAJCE Transport Query</span>
                </div>
                <div className="sidebar-item group">
                  <MessageSquare size={16} />
                  <span className="truncate">Admission 2024 Help</span>
                </div>
              </div>

              {/* Footer Links */}
              <div className="mt-auto pt-4 space-y-1 border-t border-white/5">
                <div className="sidebar-item">
                  <Settings size={16} />
                  <span>Settings</span>
                </div>
                <div className="sidebar-item">
                  <ExternalLink size={16} />
                  <span>College Website</span>
                </div>
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* MAIN CONTENT */}
      <main className="flex-1 flex flex-col relative h-full">
        {/* Toggle Sidebar Button */}
        <button 
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          className="absolute top-4 left-4 z-50 p-2 text-zinc-500 hover:text-zinc-800 dark:hover:text-white transition-colors"
        >
          {isSidebarOpen ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
        </button>

        {/* Model Picker (Header) */}
        <header className="h-14 flex items-center justify-center border-b border-white/5 bg-background/50 backdrop-blur-md z-40">
          <div className="flex items-center gap-1 cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-800 px-3 py-1.5 rounded-lg transition-colors">
            <span className="font-bold text-lg">LORIN</span>
            <span className="text-zinc-500 text-lg">2.0</span>
            <ChevronDown size={16} className="text-zinc-500 mt-1" />
          </div>
        </header>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center px-4">
              <div className="w-12 h-12 rounded-full border border-zinc-200 dark:border-zinc-700 flex items-center justify-center mb-6">
                 <Bot size={28} className="text-zinc-400" />
              </div>
              <h1 className="text-2xl font-semibold mb-8 text-center tracking-tight">How can I assist you today?</h1>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-2xl">
                {[
                  "What are the college bus routes?",
                  "Tell me about MSAJCE departments",
                  "How to apply for admission?",
                  "Scholarship details for students"
                ].map((q, i) => (
                  <button 
                    key={i} 
                    onClick={() => handleSend(q)}
                    className="p-4 rounded-xl border border-zinc-200 dark:border-zinc-700 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors text-zinc-600 dark:text-zinc-300"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="chat-container">
              {messages.map((msg) => (
                <div key={msg.id} className="message-row group">
                  <div className={cn(
                    "avatar",
                    msg.role === "user" ? "bg-zinc-600" : "bg-[#10a37f]"
                  )}>
                    {msg.role === "user" ? <User size={16} /> : <Bot size={16} />}
                  </div>
                  <div className="message-content">
                    <p className="font-bold text-[13px] mb-1 uppercase tracking-tight text-zinc-500">
                      {msg.role === "user" ? "You" : "LORIN AI"}
                    </p>
                    <div className="whitespace-pre-wrap">
                      {msg.content}
                    </div>
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="message-row">
                  <div className="avatar bg-[#10a37f]">
                    <Bot size={16} />
                  </div>
                  <div className="message-content">
                    <div className="flex gap-1 items-center h-6">
                      <div className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
                      <div className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
                      <div className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={scrollRef} className="h-20" />
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="input-container">
          <div className="input-box">
            <textarea
              rows={1}
              placeholder="Message LORIN..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              className="flex-1 bg-transparent border-none focus:ring-0 p-3 text-[15px] resize-none max-h-40 outline-none"
            />
            <button
              onClick={() => handleSend()}
              disabled={!input.trim() || isLoading}
              className="p-1.5 rounded-lg bg-zinc-100 dark:bg-white text-zinc-400 dark:text-black hover:bg-zinc-200 dark:hover:bg-zinc-100 transition-colors disabled:opacity-30 mb-1"
            >
              <Send size={18} />
            </button>
          </div>
          <p className="text-[11px] text-center mt-3 text-zinc-400 font-medium">
            LORIN can make mistakes. Check important info about MSAJCE.
          </p>
        </div>
      </main>
    </div>
  );
}
