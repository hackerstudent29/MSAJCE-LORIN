"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { Plus, ChevronDown, ArrowUp, X, FileText, Loader2, Check, Archive } from "lucide-react";

/* --- ICONS --- */
export const Icons = {
    Logo: (props: React.SVGProps<SVGSVGElement>) => (
        <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" role="presentation" {...props}>
            <defs>
                <ellipse id="petal-pair" cx="100" cy="100" rx="90" ry="22" />
            </defs>
            <g fill="#D46B4F" fillRule="evenodd">
                <use href="#petal-pair" transform="rotate(0 100 100)" />
                <use href="#petal-pair" transform="rotate(45 100 100)" />
                <use href="#petal-pair" transform="rotate(90 100 100)" />
                <use href="#petal-pair" transform="rotate(135 100 100)" />
            </g>
        </svg>
    ),
    Plus: Plus,
    Thinking: (props: React.SVGProps<SVGSVGElement>) => <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M10.3857 2.50977C14.3486 2.71054 17.5 5.98724 17.5 10C17.5 14.1421 14.1421 17.5 10 17.5C5.85786 17.5 2.5 14.1421 2.5 10C2.5 9.72386 2.72386 9.5 3 9.5C3.27614 9.5 3.5 9.72386 3.5 10C3.5 13.5899 6.41015 16.5 10 16.5C13.5899 16.5 16.5 13.5899 16.5 10C16.5 6.5225 13.7691 3.68312 10.335 3.50879L10 3.5L9.89941 3.49023C9.67145 3.44371 9.5 3.24171 9.5 3C9.5 2.72386 9.72386 2.5 10 2.5L10.3857 2.50977ZM10 5.5C10.2761 5.5 10.5 5.72386 10.5 6V9.69043L13.2236 11.0527C13.4706 11.1762 13.5708 11.4766 13.4473 11.7236C13.3392 11.9397 13.0957 12.0435 12.8711 11.9834L12.7764 11.9473L9.77637 10.4473C9.60698 10.3626 9.5 10.1894 9.5 10V6C9.5 5.72386 9.72386 5.5 10 5.5ZM3.66211 6.94141C4.0273 6.94159 4.32303 7.23735 4.32324 7.60254C4.32324 7.96791 4.02743 8.26446 3.66211 8.26465C3.29663 8.26465 3 7.96802 3 7.60254C3.00021 7.23723 3.29676 6.94141 3.66211 6.94141ZM4.95605 4.29395C5.32146 4.29404 5.61719 4.59063 5.61719 4.95605C5.6171 5.3214 5.3214 5.61709 4.95605 5.61719C4.59063 5.61719 4.29403 5.32146 4.29395 4.95605C4.29395 4.59057 4.59057 4.29395 4.95605 4.29395ZM7.60254 3C7.96802 3 8.26465 3.29663 8.26465 3.66211C8.26446 4.02743 7.96791 4.32324 7.60254 4.32324C7.23736 4.32302 6.94159 4.0273 6.94141 3.66211C6.94141 3.29676 7.23724 3.00022 7.60254 3Z"></path></svg>,
    SelectArrow: ChevronDown,
    ArrowUp: ArrowUp,
    X: X,
    FileText: FileText,
    Loader2: Loader2,
    Check: Check,
    Archive: Archive,
};

/* --- UTILS --- */
const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
};

export interface AttachedFile {
    id: string;
    file: File;
    type: string;
    preview: string | null;
    uploadStatus: string;
}

interface PastedContent {
    id: string;
    content: string;
    timestamp: Date;
}

/* --- COMPONENTS --- */

const FilePreviewCard: React.FC<{ file: AttachedFile; onRemove: (id: string) => void }> = ({ file, onRemove }) => {
    const isImage = file.type.startsWith("image/") && file.preview;
    return (
        <div className="relative group flex-shrink-0 w-24 h-24 rounded-xl overflow-hidden border border-bg-300 bg-bg-200 animate-fade-in transition-all hover:border-text-400">
            {isImage ? (
                <div className="w-full h-full relative">
                    <img src={file.preview!} alt={file.file.name} className="w-full h-full object-cover" />
                    <div className="absolute inset-0 bg-black/20 group-hover:bg-black/0 transition-colors" />
                </div>
            ) : (
                <div className="w-full h-full p-3 flex flex-col justify-between">
                    <div className="flex items-center gap-2">
                        <div className="p-1.5 bg-bg-300 rounded">
                            <Icons.FileText className="w-4 h-4 text-text-300" />
                        </div>
                        <span className="text-[10px] font-medium text-text-400 uppercase tracking-wider truncate">
                            {file.file.name.split('.').pop()}
                        </span>
                    </div>
                    <p className="text-xs font-medium text-text-200 truncate">{file.file.name}</p>
                </div>
            )}
            <button onClick={() => onRemove(file.id)} className="absolute top-1 right-1 p-1 bg-black/50 hover:bg-black/70 rounded-full text-white opacity-0 group-hover:opacity-100 transition-opacity">
                <Icons.X className="w-3 h-3" />
            </button>
            {file.uploadStatus === 'uploading' && (
                <div className="absolute inset-0 bg-black/40 flex items-center justify-center">
                    <Icons.Loader2 className="w-5 h-5 text-white animate-spin" />
                </div>
            )}
        </div>
    );
};

const PastedContentCard: React.FC<{ content: PastedContent; onRemove: (id: string) => void }> = ({ content, onRemove }) => (
    <div className="relative group flex-shrink-0 w-28 h-28 rounded-2xl overflow-hidden border border-bg-300 bg-white dark:bg-bg-200 animate-fade-in p-3 flex flex-col justify-between shadow-sm">
        <p className="text-[10px] text-text-400 leading-tight font-mono line-clamp-4">{content.content}</p>
        <span className="text-[9px] font-bold text-text-500 uppercase tracking-wider">PASTED</span>
        <button onClick={() => onRemove(content.id)} className="absolute top-2 right-2 p-1 bg-bg-200 border border-bg-300 rounded-full opacity-0 group-hover:opacity-100 transition-opacity">
            <Icons.X className="w-2 h-2" />
        </button>
    </div>
);

interface Model {
    id: string;
    name: string;
    description: string;
}

const ModelSelector: React.FC<{ models: Model[]; selectedModel: string; onSelect: (id: string) => void }> = ({ models, selectedModel, onSelect }) => {
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);
    const currentModel = models.find(m => m.id === selectedModel) || models[0];

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) setIsOpen(false);
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    return (
        <div className="relative" ref={dropdownRef}>
            <button onClick={() => setIsOpen(!isOpen)} className={`inline-flex items-center h-8 rounded-xl px-3 text-xs gap-1 transition-colors ${isOpen ? 'bg-bg-200 text-text-100' : 'text-text-400 hover:text-text-200 hover:bg-bg-200'}`}>
                <span className="font-medium">{currentModel.name}</span>
                <Icons.SelectArrow className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>
            {isOpen && (
                <div className="absolute bottom-full right-0 mb-2 w-64 bg-white dark:bg-bg-100 border border-bg-300 rounded-2xl shadow-xl p-1.5 z-50 animate-fade-in origin-bottom-right">
                    {models.map(m => (
                        <button key={m.id} onClick={() => { onSelect(m.id); setIsOpen(false); }} className="w-full text-left px-3 py-2 rounded-xl hover:bg-bg-200 flex items-center justify-between group">
                            <div className="flex flex-col">
                                <span className="text-sm font-semibold">{m.name}</span>
                                <span className="text-[10px] text-text-400">{m.description}</span>
                            </div>
                            {selectedModel === m.id && <Icons.Check className="w-4 h-4 text-accent" />}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
};

interface ClaudeChatInputProps {
    onSendMessage: (data: {
        message: string;
        files: AttachedFile[];
        pastedContent: PastedContent[];
        model: string;
        isThinkingEnabled: boolean
    }) => void;
    isLoading?: boolean;
}

export const ClaudeChatInput: React.FC<ClaudeChatInputProps> = ({ onSendMessage, isLoading }) => {
    const [message, setMessage] = useState("");
    const [files, setFiles] = useState<AttachedFile[]>([]);
    const [pastedContent, setPastedContent] = useState<PastedContent[]>([]);
    const [isDragging, setIsDragging] = useState(false);
    const [selectedModel, setSelectedModel] = useState("sonnet-4.5");
    const [isThinkingEnabled, setIsThinkingEnabled] = useState(false);

    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const models = [
        { id: "lorin-pro", name: "LORIN Pro", description: "Most capable for complex queries" },
        { id: "lorin-standard", name: "LORIN Standard", description: "Best for everyday help" },
    ];

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto";
            textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 300) + "px";
        }
    }, [message]);

    const handleFiles = useCallback((filesList: FileList | File[]) => {
        const newFiles = Array.from(filesList).map(file => ({
            id: Math.random().toString(36).substr(2, 9),
            file,
            type: file.type || 'application/octet-stream',
            preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
            uploadStatus: 'complete'
        }));
        setFiles(prev => [...prev, ...newFiles]);
    }, []);

    const handlePaste = (e: React.ClipboardEvent) => {
        const text = e.clipboardData.getData('text');
        if (text.length > 500) {
            e.preventDefault();
            setPastedContent(prev => [...prev, { id: Math.random().toString(36).substr(2, 9), content: text, timestamp: new Date() }]);
        }
    };

    const handleSend = () => {
        if ((!message.trim() && files.length === 0 && pastedContent.length === 0) || isLoading) return;
        onSendMessage({ message, files, pastedContent, model: selectedModel, isThinkingEnabled });
        setMessage("");
        setFiles([]);
        setPastedContent([]);
    };

    return (
        <div className="relative w-full max-w-3xl mx-auto px-4" onDragOver={e => { e.preventDefault(); setIsDragging(true); }} onDragLeave={() => setIsDragging(false)} onDrop={e => { e.preventDefault(); setIsDragging(false); handleFiles(e.dataTransfer.files); }}>
            <div className="flex flex-col items-stretch bg-white dark:bg-bg-200 rounded-2xl border border-bg-300 shadow-lg focus-within:ring-1 focus-within:ring-accent/30 transition-all overflow-hidden">
                <div className="p-3">
                    {(files.length > 0 || pastedContent.length > 0) && (
                        <div className="flex gap-3 overflow-x-auto pb-3 mb-1 no-scrollbar">
                            {pastedContent.map(c => <PastedContentCard key={c.id} content={c} onRemove={id => setPastedContent(p => p.filter(x => x.id !== id))} />)}
                            {files.map(f => <FilePreviewCard key={f.id} file={f} onRemove={id => setFiles(p => p.filter(x => x.id !== id))} />)}
                        </div>
                    )}
                    <textarea
                        ref={textareaRef}
                        value={message}
                        onChange={e => setMessage(e.target.value)}
                        onPaste={handlePaste}
                        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                        placeholder="Ask LORIN anything about MSAJCE..."
                        className="w-full bg-transparent border-0 outline-none text-text-100 text-[16px] placeholder:text-text-400 resize-none py-1 leading-relaxed"
                        rows={1}
                    />
                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-bg-300/50">
                        <div className="flex items-center gap-1">
                            <button onClick={() => fileInputRef.current?.click()} className="p-1.5 text-text-400 hover:text-accent hover:bg-bg-300/50 rounded-lg transition-colors">
                                <Icons.Plus className="w-5 h-5" />
                            </button>
                            <button onClick={() => setIsThinkingEnabled(!isThinkingEnabled)} className={`p-1.5 rounded-lg transition-colors ${isThinkingEnabled ? 'text-accent bg-accent/10' : 'text-text-400 hover:bg-bg-300/50'}`}>
                                <Icons.Thinking className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="flex items-center gap-2">
                            <ModelSelector models={models} selectedModel={selectedModel} onSelect={setSelectedModel} />
                            <button onClick={handleSend} disabled={(!message.trim() && files.length === 0) || isLoading} className={`p-2 rounded-xl transition-all ${message.trim() || files.length > 0 ? 'bg-accent text-white shadow-md active:scale-95' : 'bg-bg-300 text-text-500 cursor-not-allowed'}`}>
                                <Icons.ArrowUp className="w-4 h-4" />
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <input ref={fileInputRef} type="file" multiple hidden onChange={e => { if (e.target.files) handleFiles(e.target.files); e.target.value = ''; }} />
            {isDragging && <div className="absolute inset-0 bg-accent/10 border-2 border-dashed border-accent rounded-2xl z-50 flex items-center justify-center backdrop-blur-[1px] pointer-events-none text-accent font-bold">Drop files to LORIN</div>}
        </div>
    );
};

export default ClaudeChatInput;
