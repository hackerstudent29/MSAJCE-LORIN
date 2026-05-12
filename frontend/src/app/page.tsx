"use client";

import React, { useState, useRef, useEffect } from "react";
import { User, Bot, ArrowDown } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ClaudeChatInput } from "@/components/ClaudeChatInput";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ToolGroup, type NestedTool } from "@/components/ToolGroup";

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

interface Message { id: string; role: "user" | "bot"; content: string; telemetry?: any; tools?: NestedTool[]; isThinking?: boolean; autoDetectedTopic?: string; }

/* --- COMPONENTS --- */

const TypewriterText = ({ text, onComplete, skipReveal }: { text: string; onComplete?: () => void; skipReveal?: boolean }) => {
    const [visibleChars, setVisibleChars] = useState(skipReveal ? text.length : 0);

    useEffect(() => {
        if (skipReveal) return;
        
        const interval = setInterval(() => {
            setVisibleChars((prev) => {
                if (prev >= text.length) {
                    clearInterval(interval);
                    onComplete?.();
                    return prev;
                }
                return prev + 5;
            });
        }, 20);
        return () => clearInterval(interval);
    }, [text, onComplete, skipReveal]);

    const displayedText = text.slice(0, visibleChars);
    
    // Auto-link phone numbers (e.g., +91 1234567890 or 044-12345678)
    const linkedText = displayedText.replace(
        /(\+?\d{1,4}[\s-]?\d{10}|\d{2,4}-\d{6,8})/g, 
        (match) => `[${match}](tel:${match.replace(/[\s-]/g, '')})`
    );

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="prose dark:prose-invert max-w-none prose-p:leading-relaxed prose-p:my-2 prose-a:text-[#D46B4F] prose-a:no-underline hover:prose-a:underline"
        >
            <ReactMarkdown 
                remarkPlugins={[remarkGfm]}
                components={{
                    a: ({ node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                }}
            >
                {linkedText}
            </ReactMarkdown>
        </motion.div>
    );
};

/* --- MAIN PAGE --- */
export default function ChatPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isDeepSearchEnabled, setIsDeepSearchEnabled] = useState(false);
    const [revealedId, setRevealedId] = useState<string | null>(null);
    const [webUserId, setWebUserId] = useState<string>("");
    const [showScrollButton, setShowScrollButton] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);
    const mainRef = useRef<HTMLDivElement>(null);

    // Institutional Memory: Load on mount
    useEffect(() => {
        const CHAT_VERSION = "2.5.1"; // Bump this to force-clear all user chat histories

        let id = localStorage.getItem("lorin_user_id");
        if (!id) {
            id = "web_" + Math.random().toString(36).substring(2, 11);
            localStorage.setItem("lorin_user_id", id);
        }
        setWebUserId(id);

        // Force-clear old chat history if version mismatch
        const storedVersion = localStorage.getItem("lorin_chat_version");
        if (storedVersion !== CHAT_VERSION) {
            localStorage.removeItem("lorin_chat_history");
            localStorage.setItem("lorin_chat_version", CHAT_VERSION);
        }

        const saved = localStorage.getItem("lorin_chat_history");
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                if (parsed.length > 0) {
                    setMessages(parsed);
                    setRevealedId(parsed[parsed.length - 1].id);
                }
            } catch (e) { console.error("Failed to load history", e); }
        }

        // DEEP SYNC: Fetch from Supabase as fallback/integrity check
        const syncHistory = async () => {
            try {
                const res = await fetch(`https://msajce-lorin-ai.vercel.app/api/history?user_id=${id}`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.history && data.history.length > 0) {
                        setMessages(data.history);
                        setRevealedId(data.history[data.history.length - 1].id);
                    }
                }
            } catch (e) { console.error("Vault sync failed", e); }
        };
        syncHistory();
    }, []);

    // Institutional Memory: Save on change
    useEffect(() => {
        if (messages.length > 0) {
            localStorage.setItem("lorin_chat_history", JSON.stringify(messages));
        }
        scrollToBottom();
    }, [messages]);

    const scrollToBottom = () => {
        scrollRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
        const target = e.currentTarget;
        const isScrolledUp = target.scrollHeight - target.scrollTop > target.clientHeight + 200;
        setShowScrollButton(isScrolledUp);
    };

    const handleSendMessage = async (data: any) => {
        const { message, model, isThinkingEnabled, user_level } = data;
        
        // GIBBERISH/EMPTY FILTER (Telegram Logic)
        if (!message.trim() || message.length < 2) return;
        if (isLoading) return;

        // Add user message
        const userMsgId = Date.now().toString();
        setMessages(p => [...p, { id: userMsgId, role: "user", content: message }]);
        setRevealedId(null);
        const startTime = performance.now();
        setIsLoading(true);

        const botMsgId = (Date.now() + 1).toString();
        setMessages(p => [...p, { 
            id: botMsgId, 
            role: "bot", 
            content: "", 
            isThinking: isThinkingEnabled,
            autoDetectedTopic: data.autoDetectedTopic
        }]);

        try {
            const BACKEND_URL = "https://msajce-lorin-ai.vercel.app/api/chat";
            const res = await fetch(BACKEND_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    message, 
                    model: model || "lorin-pro", 
                    thinking: isThinkingEnabled,
                    deep_search: isDeepSearchEnabled,
                    user_id: webUserId,
                    user_level: user_level || "student",
                    topic: data.topic
                }),
            });
            
            const endTime = performance.now();
            const perceivedLatencyMs = endTime - startTime;

            if (res.status === 403) {
                const securityData = await res.json();
                setMessages(p => p.map(m => m.id === botMsgId ? { 
                    ...m, 
                    content: securityData.response || "Institutional Security Alert.",
                    telemetry: { latency_ms: perceivedLatencyMs } 
                } : m));
                setIsLoading(false);
                return;
            }
            
            if (!res.ok) throw new Error("Backend error");
            const responseData = await res.json();
            const responseContent = responseData.response || "Institutional intelligence is currently analyzing your request. Please try again.";
            
            // Map real institutional sources to the ToolGroup, filtering out "Unknown"
            const realTools: NestedTool[] = (responseData.telemetry?.sources || [])
                .filter((s: string) => s && s.toLowerCase() !== "unknown" && s !== "None")
                .map((s: string) => ({
                    category: "file",
                    title: s,
                    subtitle: "Verified Institutional Source"
                }));

            setMessages(p => p.map(m => m.id === botMsgId ? { 
                ...m, 
                content: responseContent,
                tools: realTools.length > 0 ? realTools : [
                    { category: "file", title: "Institutional Intelligence Archive", subtitle: "Ground Truth Vault" }
                ],
                telemetry: { ...responseData.telemetry, latency_ms: perceivedLatencyMs }
            } : m));
        } catch (e) { 
            console.error("Chat error:", e);
            setMessages(p => p.map(m => m.id === botMsgId ? { 
                ...m, 
                content: "I'm currently experiencing institutional sync issues. Please try again in a moment." 
            } : m));
        } finally { 
            setIsLoading(false); 
        }
    };

    return (
        <div className="flex flex-col h-dvh bg-[#FDFDFD] dark:bg-[#1A1A1A] transition-colors duration-500 font-sans antialiased overflow-hidden">
            {/* Header */}
            <header className="h-12 flex items-center justify-between px-4 sm:px-6 bg-transparent sticky top-0 z-50 transition-all">
                <div className="flex items-center gap-2">
                    <Icons.Logo className="w-8 h-8 text-[#D46B4F]" />
                    <span className="text-[18px] tracking-tight text-zinc-900 dark:text-white">Lorin</span>
                    <div className="px-1.5 py-[1px] bg-[#D46B4F]/10 border border-[#D46B4F]/20 rounded text-[10px] text-[#D46B4F]">v2.5</div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                        <span className="text-[10px] text-zinc-500 dark:text-zinc-400 tracking-widest">Ground truth active</span>
                    </div>
                </div>
            </header>

            {/* Chat Area */}
            <main 
                ref={mainRef}
                onScroll={handleScroll}
                className="flex-1 overflow-y-auto no-scrollbar py-12 scroll-smooth"
            >
                {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center px-4 animate-in fade-in slide-in-from-bottom-4 duration-1000">
                        <div className="p-5 bg-zinc-50 dark:bg-zinc-800/50 rounded-3xl mb-10 shadow-sm">
                            <Icons.Logo className="w-16 h-16 animate-pulse" />
                        </div>
                        <h1 className="text-4xl mb-4 text-zinc-900 dark:text-white tracking-tighter">Institutional intelligence.</h1>
                        <p className="text-zinc-500 dark:text-zinc-400 mb-12 max-w-md">How can Lorin assist you today with MSAJCE data?</p>
                        
                        <div className="grid grid-cols-2 gap-3 w-full max-w-xl">
                            {[
                                { q: "Bus Routes", desc: "Fleet & routes" },
                                { q: "Faculties", desc: "Staff directory" },
                                { q: "Admissions", desc: "Admission code 1301" },
                                { q: "Scholarships", desc: "Female & merit waivers" }
                            ].map(item => (
                                <button 
                                    key={item.q} 
                                    onClick={() => handleSendMessage({ message: item.q })} 
                                    className="p-6 rounded-3xl border border-zinc-200 dark:border-zinc-800 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/80 transition-all group hover:border-[#D46B4F]/50 shadow-sm hover:shadow-md"
                                >
                                    <div className="text-zinc-900 dark:text-white mb-1 group-hover:text-[#D46B4F] transition-colors">{item.q}</div>
                                    <span className="text-[11px] text-zinc-400 dark:text-zinc-500 tracking-wide">Lorin system</span>
                                    <div className="text-[11px] text-zinc-400 dark:text-zinc-500 uppercase tracking-wider">{item.desc}</div>
                                </button>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div className="max-w-3xl mx-auto px-4 space-y-8">
                        {messages.map((m, idx) => (
                            <div key={m.id} className={`flex w-full gap-4 items-start ${m.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                                {/* Icon */}
                                <div className={`w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 shadow-sm ${m.role === "user" ? "bg-zinc-800 dark:bg-zinc-700" : "bg-[#D46B4F] shadow-lg shadow-[#D46B4F]/20"}`}>
                                    {m.role === "user" ? <User size={20} className="text-white" /> : <Bot size={20} className="text-white" />}
                                </div>

                                {/* Message Content Container */}
                                <div className={`flex flex-col max-w-[90%] sm:max-w-[85%] ${m.role === "user" ? "items-end" : "items-start"} overflow-hidden`}>
                                    {/* Meta Header */}
                                    <div className="flex items-center gap-2 mb-1.5 px-1">
                                        <span className="text-[10px] text-zinc-400 dark:text-zinc-500 tracking-widest">
                                            {m.role === "user" ? "Academic inquiry" : "Lorin system"}
                                        </span>
                                    </div>

                                    {/* Bot Logic: Unified Container to prevent double icons */}
                                    {m.role === "bot" && (
                                        <div className="flex flex-col gap-2 w-full">
                                            {/* Thinking / Reasoning Trail: Technical System Logs */}
                                            {(m.tools || (idx === messages.length - 1 && isLoading)) && (
                                                    <div className="w-full mb-1">
                                                        <ToolGroup
                                                            state={idx === messages.length - 1 && isLoading ? "pending" : "completed"}
                                                            chunkCount={m.telemetry?.num_chunks}
                                                            nestedTools={m.tools}
                                                            completeLabel={(isDeepSearchEnabled || m.isThinking) ? "Deep institutional analysis" : "Lorin reasoning"}
                                                            shimmerLabel={(isDeepSearchEnabled || m.isThinking) ? "Deep searching archives..." : "Lorin is thinking"}
                                                            interruptedLabel="Reasoning interrupted"
                                                            elapsedTime={m.telemetry?.latency_ms ? `${(m.telemetry.latency_ms / 1000).toFixed(1)}s` : undefined}
                                                            showElapsed={true}
                                                            defaultOpen={idx === messages.length - 1 && !isLoading}
                                                        />
                                                    </div>
                                                )}

                                                {/* Intent Notice */}
                                                {m.autoDetectedTopic && (
                                                    <div className="px-1 mb-1 animate-in fade-in slide-in-from-bottom-1">
                                                        <p className="text-[11px] text-zinc-400 dark:text-zinc-500 italic">
                                                            Searched under {m.autoDetectedTopic} — your question seemed to be about {m.autoDetectedTopic}.
                                                        </p>
                                                    </div>
                                                )}

                                            {/* Bubble */}
                                            <div className={`
                                                block w-full p-4 rounded-2xl text-[15px] sm:text-[16px] leading-relaxed whitespace-pre-wrap antialiased break-words
                                                ${m.content.includes("Security Alert")
                                                    ? "border-l-2 border-orange-400/50 pl-4 py-2 text-zinc-600 dark:text-zinc-400 font-sans"
                                                    : "text-zinc-800 dark:text-zinc-100"
                                                }
                                            `}>
                                                {m.content === "" && idx === messages.length - 1 && isLoading ? (
                                                    null // ToolGroup handles the visual wait
                                                ) : (
                                                    <TypewriterText 
                                                        text={m.content} 
                                                        skipReveal={idx < messages.length - 1 || revealedId === m.id}
                                                        onComplete={() => {
                                                            if (idx === messages.length - 1) setRevealedId(m.id);
                                                        }} 
                                                    />
                                                )}
                                            </div>

                                            {/* Telemetry Badge (BACK AT BOTTOM) */}
                                            {m.telemetry && (revealedId === m.id || idx < messages.length - 1) && (
                                                <motion.div 
                                                    initial={revealedId === m.id ? { opacity: 0, y: -5 } : { opacity: 1, y: 0 }}
                                                    animate={{ opacity: 1, y: 0 }}
                                                    className="flex flex-wrap gap-2 pt-3"
                                                >
                                                    <div className="px-3 py-1 rounded-full bg-[#D46B4F]/10 border border-[#D46B4F]/20 text-[10px] text-[#D46B4F] font-mono font-bold tracking-tight">
                                                        {typeof m.telemetry.tokens === 'number' ? m.telemetry.tokens : (m.telemetry.tokens?.total || 0)} Tokens
                                                    </div>
                                                    <div className="px-3 py-1 rounded-full bg-[#D46B4F]/10 border border-[#D46B4F]/20 text-[10px] text-[#D46B4F] font-mono font-bold tracking-tight">
                                                        {(m.telemetry.latency_ms / 1000).toFixed(1)}s Lat
                                                    </div>
                                                </motion.div>
                                            )}
                                        </div>
                                    )}

                                    {/* User Message Rendering */}
                                    {m.role === "user" && (
                                        <div className="inline-block p-4 rounded-2xl text-[16px] leading-relaxed whitespace-pre-wrap antialiased bg-zinc-100 dark:bg-zinc-800/80 text-zinc-800 dark:text-zinc-200 shadow-sm">
                                            {m.content}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                        
                        <div ref={scrollRef} className="h-20" />
                    </div>
                )}
            </main>

            {/* Input Bar */}
            <div className="pb-10 bg-gradient-to-t from-[#FDFDFD] dark:from-[#1A1A1A] via-[#FDFDFD]/90 dark:via-[#1A1A1A]/90 to-transparent pt-12 sticky bottom-0 z-50">
                <div className="max-w-3xl mx-auto px-4 relative">
                    <AnimatePresence>
                        {showScrollButton && (
                            <button
                                onClick={scrollToBottom}
                                className="fixed bottom-24 sm:bottom-28 left-1/2 -translate-x-1/2 p-2 bg-white dark:bg-[#30302E] border border-zinc-200 dark:border-white/10 rounded-full shadow-lg hover:bg-zinc-50 dark:hover:bg-[#40403E] transition-all animate-in fade-in slide-in-from-bottom-2 z-40"
                            >
                                <ArrowDown size={18} />
                            </button>
                        )}
                    </AnimatePresence>
                    
                    <ClaudeChatInput 
                        onSendMessage={handleSendMessage} 
                        isDeepSearchEnabled={isDeepSearchEnabled}
                        setIsDeepSearchEnabled={setIsDeepSearchEnabled}
                    />
                </div>
            </div>
        </div>
    );
}
