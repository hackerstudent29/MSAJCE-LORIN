"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { Plus, ChevronDown, ArrowUp, X, FileText, Loader2, Check, Archive, User, Bot } from "lucide-react";

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
    Plus, ChevronDown, ArrowUp, X, FileText, Loader2, Check, Archive,
    Thinking: (props: any) => <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" {...props}><path d="M10.3857 2.50977C14.3486 2.71054 17.5 5.98724 17.5 10C17.5 14.1421 14.1421 17.5 10 17.5C5.85786 17.5 2.5 14.1421 2.5 10C2.5 9.72386 2.72386 9.5 3 9.5C3.27614 9.5 3.5 9.72386 3.5 10C3.5 13.5899 6.41015 16.5 10 16.5C13.5899 16.5 16.5 13.5899 16.5 10C16.5 6.5225 13.7691 3.68312 10.335 3.50879L10 3.5L9.89941 3.49023C9.67145 3.44371 9.5 3.24171 9.5 3C9.5 2.72386 9.72386 2.5 10 2.5L10.3857 2.50977ZM10 5.5C10.2761 5.5 10.5 5.72386 10.5 6V9.69043L13.2236 11.0527C13.4706 11.1762 13.5708 11.4766 13.4473 11.7236C13.3392 11.9397 13.0957 12.0435 12.8711 11.9834L12.7764 11.9473L9.77637 10.4473C9.60698 10.3626 9.5 10.1894 9.5 10V6C9.5 5.72386 9.72386 5.5 10 5.5Z" /></svg>,
};

/* --- UTILS --- */
const formatFileSize = (b: number) => {
    if (b === 0) return "0 Bytes";
    const k = 1024;
    const s = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(b) / Math.log(k));
    return parseFloat((b / Math.pow(k, i)).toFixed(2)) + " " + s[i];
};

interface AttachedFile { id: string; file: File; type: string; preview: string | null; uploadStatus: string; }
interface Message { id: string; role: "user" | "bot"; content: string; }

/* --- SUB-COMPONENTS --- */
const FileCard = ({ file, onRemove }: any) => (
    <div className="relative group w-24 h-24 rounded-xl border border-bg-300 bg-bg-200 overflow-hidden animate-fade-in shrink-0">
        {file.preview ? <img src={file.preview} className="w-full h-full object-cover" /> : <div className="p-3"><Icons.FileText className="w-5 h-5 text-text-300" /></div>}
        <button onClick={() => onRemove(file.id)} className="absolute top-1 right-1 p-1 bg-black/50 rounded-full text-white opacity-0 group-hover:opacity-100 transition-opacity"><Icons.X className="w-3 h-3" /></button>
    </div>
);

const PastedCard = ({ content, onRemove }: any) => (
    <div className="relative group w-28 h-28 rounded-2xl border border-bg-300 bg-white dark:bg-bg-200 p-3 flex flex-col justify-between shrink-0 animate-fade-in shadow-sm">
        <p className="text-[10px] text-text-400 font-mono line-clamp-4">{content.content}</p>
        <span className="text-[9px] font-bold text-text-500 uppercase tracking-widest">PASTED</span>
        <button onClick={() => onRemove(content.id)} className="absolute top-2 right-2 p-1 bg-bg-200 border border-bg-300 rounded-full text-text-400 opacity-0 group-hover:opacity-100"><Icons.X className="w-2 h-2" /></button>
    </div>
);

const ModelSelector = ({ selected, onSelect }: any) => {
    const [open, setOpen] = useState(false);
    const models = [{ id: "lorin-pro", name: "LORIN Pro" }, { id: "lorin-std", name: "LORIN Standard" }];
    return (
        <div className="relative">
            <button onClick={() => setOpen(!open)} className="h-8 px-3 rounded-xl text-xs font-medium text-text-400 hover:bg-bg-200 flex items-center gap-1">
                {models.find(m => m.id === selected)?.name} <Icons.ChevronDown className="w-3 h-3" />
            </button>
            {open && (
                <div className="absolute bottom-full right-0 mb-2 w-48 bg-white dark:bg-bg-100 border border-bg-300 rounded-2xl shadow-xl p-1.5 z-50">
                    {models.map(m => (
                        <button key={m.id} onClick={() => { onSelect(m.id); setOpen(false); }} className="w-full text-left px-3 py-2 rounded-xl text-sm hover:bg-bg-200 flex items-center justify-between">
                            {m.name} {selected === m.id && <Icons.Check className="w-3 h-3 text-accent" />}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};

/* --- MAIN PAGE --- */
export default function ChatPage() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState("");
    const [files, setFiles] = useState<AttachedFile[]>([]);
    const [pastes, setPastes] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [thinking, setThinking] = useState(false);
    const [model, setModel] = useState("lorin-pro");
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => { scrollRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

    const handleSend = async (manualText?: string) => {
        const text = manualText || input;
        if ((!text.trim() && files.length === 0) || isLoading) return;

        setMessages(p => [...p, { id: Date.now().toString(), role: "user", content: text }]);
        setInput(""); setFiles([]); setPastes([]); setIsLoading(true);

        try {
            // YOUR BOT BACKEND URL
            const BACKEND_URL = "https://msajce-lorin-ai-rams-projects-e308a69c.vercel.app/api/chat";
            
            const res = await fetch(BACKEND_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text, model, thinking }),
            });
            const data = await res.json();
            setMessages(p => [...p, { id: (Date.now() + 1).toString(), role: "bot", content: data.response || "I encountered an error. Please try again." }]);
        } catch (e) { 
            setMessages(p => [...p, { id: Date.now().toString(), role: "bot", content: "Connection Error: Please ensure your Bot is awake at msajce-lorin.vercel.app" }]);
        } finally { setIsLoading(false); }
    };

    return (
        <div className="flex flex-col h-screen bg-white dark:bg-[#212121]">
            <header className="h-14 flex items-center justify-center border-b border-bg-300 dark:border-white/5 bg-white/80 dark:bg-bg-100/50 backdrop-blur-md">
                <div className="flex items-center gap-2 font-bold text-lg tracking-tight">LORIN <span className="bg-accent/10 text-accent text-[10px] px-1.5 py-0.5 rounded-full">PRO</span></div>
            </header>

            <main className="flex-1 overflow-y-auto no-scrollbar py-8">
                {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center px-4">
                        <Icons.Logo className="w-16 h-16 mb-8" />
                        <h1 className="text-3xl font-bold mb-12">How can I assist you today?</h1>
                        <div className="grid grid-cols-2 gap-3 w-full">
                            {["Bus Routes", "Faculties", "Admissions", "Library"].map(q => (
                                <button key={q} onClick={() => handleSend(q)} className="p-4 rounded-2xl border border-bg-300 text-left text-sm hover:bg-bg-200 transition-all">{q}</button>
                            ))}
                        </div>
                    </div>
                ) : (
                    <div className="max-w-3xl mx-auto px-4 space-y-8">
                        {messages.map(m => (
                            <div key={m.id} className={`flex gap-4 group ${m.role === "user" ? "flex-row-reverse text-right" : ""}`}>
                                <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${m.role === "user" ? "bg-zinc-700" : "bg-accent shadow-lg shadow-accent/20"}`}>
                                    {m.role === "user" ? <User size={18} className="text-white" /> : <Bot size={18} className="text-white" />}
                                </div>
                                <div className="flex-1 space-y-1">
                                    <p className="text-[11px] font-bold uppercase text-text-500 tracking-widest">{m.role === "user" ? "Principal / Faculty" : "LORIN Intelligence"}</p>
                                    <div className={`inline-block max-w-[85%] text-zinc-800 dark:text-zinc-200 leading-relaxed whitespace-pre-wrap ${m.role === "user" ? "bg-bg-200 p-3 rounded-2xl" : ""}`}>{m.content}</div>
                                </div>
                            </div>
                        ))}
                        {isLoading && <div className="flex gap-4"><div className="w-9 h-9 bg-accent rounded-full flex items-center justify-center"><Bot size={18} className="text-white" /></div><div className="flex gap-1.5 items-center h-9"><div className="w-2 h-2 bg-accent/30 rounded-full animate-bounce" /><div className="w-2 h-2 bg-accent/30 rounded-full animate-bounce [animation-delay:0.2s]" /><div className="w-2 h-2 bg-accent/30 rounded-full animate-bounce [animation-delay:0.4s]" /></div></div>}
                        <div ref={scrollRef} className="h-32" />
                    </div>
                )}
            </main>

            <div className="pb-8 bg-gradient-to-t from-white dark:from-[#212121] via-white to-transparent pt-4">
                <div className="max-w-3xl mx-auto px-4">
                    <div className="bg-white dark:bg-bg-200 rounded-3xl border border-bg-300 shadow-2xl p-3 focus-within:ring-1 focus-within:ring-accent/30 transition-all">
                        {(files.length > 0 || pastes.length > 0) && (
                            <div className="flex gap-3 overflow-x-auto pb-3 mb-2 no-scrollbar">
                                {pastes.map(p => <PastedCard key={p.id} content={p} onRemove={(id: string) => setPastes(x => x.filter(v => v.id !== id))} />)}
                                {files.map(f => <FileCard key={f.id} file={f} onRemove={(id: string) => setFiles(x => x.filter(v => v.id !== id))} />)}
                            </div>
                        )}
                        <textarea value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }} placeholder="Message LORIN..." className="w-full bg-transparent border-0 outline-none p-1 text-[16px] resize-none" rows={1} />
                        <div className="flex items-center justify-between mt-2 pt-2 border-t border-bg-300/50">
                            <div className="flex items-center gap-1">
                                <button className="p-1.5 text-text-400 hover:text-accent hover:bg-bg-300/50 rounded-lg"><Icons.Plus className="w-5 h-5" /></button>
                                <button onClick={() => setThinking(!thinking)} className={`p-1.5 rounded-lg ${thinking ? "text-accent bg-accent/10" : "text-text-400 hover:bg-bg-300/50"}`}><Icons.Thinking className="w-5 h-5" /></button>
                            </div>
                            <div className="flex items-center gap-2">
                                <ModelSelector selected={model} onSelect={setModel} />
                                <button onClick={() => handleSend()} disabled={!input.trim() || isLoading} className={`p-2 rounded-2xl transition-all ${input.trim() ? "bg-accent text-white shadow-lg active:scale-95" : "bg-bg-300 text-text-500"}`}><Icons.ArrowUp className="w-4 h-4" /></button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
