"use client";

import { useState, useEffect, useRef } from "react";
import { 
  Plus, 
  MessageSquare, 
  User, 
  Bot, 
  Settings, 
  ExternalLink,
  ChevronDown,
  PanelLeftClose,
  PanelLeftOpen
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { ClaudeChatInput, AttachedFile } from "../components/ClaudeChatInput";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type Message = {
  id: string;
  role: "user" | "bot";
  content: string;
  files?: AttachedFile[];
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (data: { message: string, files: AttachedFile[] }) => {
    const { message, files } = data;
    if (!message.trim() && files.length === 0) return;

    const userMsg: Message = { 
      id: Date.now().toString(), 
      role: "user", 
      content: message,
      files: files
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      // PRO TIP: Replace with your actual Bot URL for production
      const BACKEND_URL = "/api/chat";
      
      const response = await fetch(BACKEND_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          message: message,
          has_files: files.length > 0 
        }),
      });

      const result = await response.json();
      const botMsg: Message = { 
        id: (Date.now() + 1).toString(), 
        role: "bot", 
        content: result.response || "I encountered an error. Please try again." 
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
            className="bg-[#171717] flex flex-col h-full overflow-hidden shrink-0 border-r border-white/5"
          >
            <div className="p-3 flex flex-col h-full">
              <button 
                onClick={() => setMessages([])}
                className="flex items-center justify-between w-full p-3 rounded-xl hover:bg-[#2f2f2f] transition-colors group mb-6"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-white flex items-center justify-center text-black">
                    <Plus size={18} strokeWidth={2.5} />
                  </div>
                  <span className="text-sm font-semibold text-white">New Chat</span>
                </div>
                <MessageSquare size={16} className="text-zinc-500 group-hover:text-zinc-300" />
              </button>

              <div className="flex-1 overflow-y-auto space-y-1">
                <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest px-3 mb-3">Recent Discussions</p>
                <div className="sidebar-item">
                  <MessageSquare size={16} />
                  <span className="truncate">Campus Bus Schedule</span>
                </div>
                <div className="sidebar-item">
                  <MessageSquare size={16} />
                  <span className="truncate">CSE Placement Stats</span>
                </div>
              </div>

              <div className="mt-auto pt-4 space-y-1 border-t border-white/5">
                <div className="sidebar-item">
                  <Settings size={16} />
                  <span>Settings</span>
                </div>
                <div className="sidebar-item">
                  <ExternalLink size={16} />
                  <span>MSAJCE Website</span>
                </div>
              </div>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* MAIN CONTENT */}
      <main className="flex-1 flex flex-col relative h-full bg-white dark:bg-[#212121]">
        {/* Toggle Sidebar Button */}
        <button 
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          className="absolute top-4 left-4 z-50 p-2 text-zinc-400 hover:text-zinc-800 dark:hover:text-white transition-colors"
        >
          {isSidebarOpen ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
        </button>

        {/* Header */}
        <header className="h-14 flex items-center justify-center border-b border-zinc-100 dark:border-white/5 bg-white/80 dark:bg-background/50 backdrop-blur-md z-40">
          <div className="flex items-center gap-2 cursor-pointer hover:bg-zinc-100 dark:hover:bg-zinc-800 px-3 py-1.5 rounded-xl transition-colors">
            <span className="font-bold text-lg tracking-tight">LORIN</span>
            <span className="bg-accent/10 text-accent text-[10px] px-1.5 py-0.5 rounded-full font-bold">PRO</span>
            <ChevronDown size={14} className="text-zinc-400" />
          </div>
        </header>

        {/* Chat Feed */}
        <div className="flex-1 overflow-y-auto no-scrollbar">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center px-4 max-w-2xl mx-auto text-center">
              <div className="w-16 h-16 rounded-2xl border border-zinc-100 dark:border-zinc-800 flex items-center justify-center mb-8 shadow-sm">
                 <Bot size={32} className="text-accent" />
              </div>
              <h1 className="text-3xl font-bold mb-4 tracking-tight">I'm LORIN. How can I help you?</h1>
              <p className="text-zinc-500 dark:text-zinc-400 text-sm mb-12">Ask about college admissions, bus routes, or department details.</p>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 w-full">
                {[
                  "Where is the bus for Route 47?",
                  "Show me the CSE faculty list",
                  "What are the admission requirements?",
                  "Contact info for the Principal"
                ].map((q, i) => (
                  <button 
                    key={i} 
                    onClick={() => handleSend({ message: q, files: [] })}
                    className="p-4 rounded-2xl border border-zinc-100 dark:border-zinc-800 text-left text-sm hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-all hover:border-accent/30 text-zinc-600 dark:text-zinc-300 group"
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
                    msg.role === "user" ? "bg-zinc-700" : "bg-accent shadow-lg shadow-accent/20"
                  )}>
                    {msg.role === "user" ? <User size={18} /> : <Bot size={18} />}
                  </div>
                  <div className="message-content">
                    <p className="font-bold text-[11px] mb-2 uppercase tracking-widest text-zinc-400">
                      {msg.role === "user" ? "Principal / Faculty" : "LORIN Intelligence"}
                    </p>
                    <div className="whitespace-pre-wrap text-zinc-800 dark:text-zinc-200">
                      {msg.content}
                    </div>
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="message-row">
                  <div className="avatar bg-accent">
                    <Bot size={18} />
                  </div>
                  <div className="message-content">
                    <div className="flex gap-1.5 items-center h-8">
                      <div className="w-2 h-2 bg-accent/40 rounded-full animate-bounce [animation-delay:-0.3s]" />
                      <div className="w-2 h-2 bg-accent/40 rounded-full animate-bounce [animation-delay:-0.15s]" />
                      <div className="w-2 h-2 bg-accent/40 rounded-full animate-bounce" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={scrollRef} className="h-32" />
            </div>
          )}
        </div>

        {/* Premium Input Component */}
        <div className="pb-8 bg-gradient-to-t from-white dark:from-[#212121] via-white dark:via-[#212121] to-transparent">
          <ClaudeChatInput 
            onSendMessage={handleSend} 
            isLoading={isLoading} 
          />
        </div>
      </main>
    </div>
  );
}
