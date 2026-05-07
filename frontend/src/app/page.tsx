"use client";

import React, { useState, useRef, useEffect } from "react";
import { User, Bot } from "lucide-react";
import { ClaudeChatInput } from "@/components/ClaudeChatInput";

/* --- ICONS --- */
const Icons = {
    Logo: (props: React.SVGProps<SVGSVGElement>) => (
        <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" {...props}>
            <ellipse cx="100" cy="100" rx="90" ry="22" fill="#D46B4F" transform="rotate(0 100 100)" />
            <ellipse cx="100" cy="100" rx="90" ry="22" fill="#D46B4F" transform="rotate(45 100 100)" />
            <ellipse cx="100" cy="100" rx="90" ry="22" fill="#D46B4F" transform="rotate(90 100 100)" />
            <ellipse cx="100" cy="100" rx="90" ry="22" fill="#D46B4F" transform="rotate(135 100 100)" />
        </svg>
    ),
};

interface Message { id: string; role: "user" | "bot"; content: string; telemetry?: any; }

/* --- MAIN PAGE --- */
export default function ChatPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [webUserId] = useState(() => "web_" + Math.random().toString(36).substring(7));
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => { 
        scrollRef.current?.scrollIntoView({ behavior: "smooth" }); 
    }, [messages]);

    const handleSendMessage = async (data: any) => {
        const { message, model, isThinkingEnabled } = data;
        
        if (!message.trim() || isLoading) return;

        // Add user message
        const userMsgId = Date.now().toString();
        setMessages(p => [...p, { id: userMsgId, role: "user", content: message }]);
        setIsLoading(true);

        try {
            // BACKEND URL
            const BACKEND_URL = "https://msajce-lorin-ai.vercel.app/api/chat";
            
            const res = await fetch(BACKEND_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    message, 
                    model: model || "lorin-pro", 
                    thinking: isThinkingEnabled,
                    user_id: webUserId
                }),
            });
            
            if (!res.ok) throw new Error("Backend error");
            
            const responseData = await res.json();
            setMessages(p => [...p, { 
                id: (Date.now() + 1).toString(), 
                role: "bot", 
                content: responseData.response || "I encountered an error. Please try again.",
                telemetry: responseData.telemetry
            }]);
        } catch (e) { 
            setMessages(p => [...p, { 
                id: (Date.now() + 2).toString(), 
                role: "bot", 
                content: "Connection Error: Please ensure your Bot is awake at msajce-lorin-ai.vercel.app" 
            }]);
        } finally { 
            setIsLoading(false); 
        }
    };

    return (
        <div className="flex flex-col h-screen bg-white dark:bg-[#212121] transition-colors duration-500">
            {/* Header */}
            <header className="h-14 flex items-center justify-between px-6 border-b border-zinc-200 dark:border-white/5 bg-white/80 dark:bg-[#212121]/50 backdrop-blur-md sticky top-0 z-50">
                <div className="flex items-center gap-2 font-bold text-lg tracking-tight text-zinc-900 dark:text-white">
                    <Icons.Logo className="w-6 h-6" />
                    LORIN <span className="bg-[#D46B4F]/10 text-[#D46B4F] text-[10px] px-1.5 py-0.5 rounded-full font-bold">PRO</span>
                </div>
                <div className="flex items-center gap-4">
                    <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Institutional Intelligence</span>
                </div>
            </header>

            {/* Chat Area */}
            <main className="flex-1 overflow-y-auto no-scrollbar py-8">
                {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center px-4 animate-in fade-in slide-in-from-bottom-4 duration-1000">
                        <div className="p-4 bg-zinc-50 dark:bg-zinc-800/50 rounded-full mb-8">
                            <Icons.Logo className="w-16 h-16 animate-pulse" />
                        </div>
                        <h1 className="text-4xl font-bold mb-4 text-zinc-900 dark:text-white tracking-tight">How can I assist you today?</h1>
                        <p className="text-zinc-500 dark:text-zinc-400 mb-12 max-w-md">Lorin is your AI-powered companion for college information, admissions, and departmental queries.</p>
                        
                        <div className="grid grid-cols-2 gap-3 w-full max-w-xl">
                            {[
                                { q: "Bus Routes", desc: "View transportation details" },
                                { q: "Faculties", desc: "Browse staff directory" },
                                { q: "Admissions", desc: "Enquiry about courses" },
                                { q: "Library", desc: "Check book availability" }
                            ].map(item => (
                                <button 
                                    key={item.q} 
                                    onClick={() => handleSendMessage({ message: item.q })} 
                                    className="p-5 rounded-2xl border border-zinc-200 dark:border-zinc-800 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/80 transition-all group hover:border-[#D46B4F]/50"
                                >
                                    <div className="font-semibold text-zinc-900 dark:text-white mb-1 group-hover:text-[#D46B4F] transition-colors">{item.q}</div>
                                    <div className="text-xs text-zinc-500 dark:text-zinc-400">{item.desc}</div>
                                </button>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div className="max-w-3xl mx-auto px-4 space-y-10">
                        {messages.map(m => (
                            <div key={m.id} className={`flex gap-6 group animate-in fade-in duration-500 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                                <div className={`w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 shadow-sm ${m.role === "user" ? "bg-zinc-800 dark:bg-zinc-700" : "bg-[#D46B4F] shadow-[#D46B4F]/20 shadow-lg"}`}>
                                    {m.role === "user" ? <User size={20} className="text-white" /> : <Bot size={20} className="text-white" />}
                                </div>
                                <div className={`flex-1 space-y-2 ${m.role === "user" ? "text-right" : ""}`}>
                                    <div className="text-[10px] font-bold uppercase text-zinc-400 dark:text-zinc-500 tracking-[0.2em]">
                                        {m.role === "user" ? "Academic Inquiry" : "Lorin System"}
                                    </div>
                                    <div className={`
                                        inline-block max-w-full text-[15px] leading-relaxed whitespace-pre-wrap antialiased
                                        ${m.role === "user" 
                                            ? "bg-zinc-100 dark:bg-zinc-800/80 p-4 rounded-3xl text-zinc-800 dark:text-zinc-200" 
                                            : "text-zinc-800 dark:text-zinc-100 font-medium"
                                        }
                                    `}>
                                        {m.content}
                                    </div>
                                    {m.role === "bot" && m.telemetry && (
                                        <div className="flex flex-wrap gap-2 pt-2 animate-in fade-in slide-in-from-top-1 duration-700">
                                            <div className="px-2 py-0.5 rounded-full bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-700/50 text-[9px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-tighter">
                                                Query: {m.telemetry.tokens?.input || 0} t
                                            </div>
                                            <div className="px-2 py-0.5 rounded-full bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-700/50 text-[9px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-tighter">
                                                Reply: {m.telemetry.tokens?.output || 0} t
                                            </div>
                                            <div className="px-2 py-0.5 rounded-full bg-[#D46B4F]/5 border border-[#D46B4F]/10 text-[9px] font-bold text-[#D46B4F]/70 uppercase tracking-tighter">
                                                Total: {m.telemetry.tokens?.total || 0} tokens
                                            </div>
                                            <div className="px-2 py-0.5 rounded-full bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-100 dark:border-zinc-700/50 text-[9px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-tighter">
                                                Latency: {m.telemetry.latency_ms}ms
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                        
                        {isLoading && (
                            <div className="flex gap-6 animate-pulse">
                                <div className="w-10 h-10 bg-[#D46B4F]/50 rounded-2xl flex items-center justify-center">
                                    <Bot size={20} className="text-white" />
                                </div>
                                <div className="flex gap-2 items-center">
                                    <div className="w-1.5 h-1.5 bg-[#D46B4F] rounded-full animate-bounce" />
                                    <div className="w-1.5 h-1.5 bg-[#D46B4F] rounded-full animate-bounce [animation-delay:0.2s]" />
                                    <div className="w-1.5 h-1.5 bg-[#D46B4F] rounded-full animate-bounce [animation-delay:0.4s]" />
                                </div>
                            </div>
                        )}
                        <div ref={scrollRef} className="h-40" />
                    </div>
                )}
            </main>

            {/* Input Bar */}
            <div className="pb-8 bg-gradient-to-t from-white dark:from-[#212121] via-white/90 dark:via-[#212121]/90 to-transparent pt-10 sticky bottom-0 z-50">
                <div className="max-w-3xl mx-auto px-4">
                    <ClaudeChatInput onSendMessage={handleSendMessage} />
                </div>
            </div>
        </div>
    );
}

