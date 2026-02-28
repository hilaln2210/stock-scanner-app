import { useState, useRef, useEffect, useCallback } from "react";
import { Bot, X, Send, ChevronDown, ChevronUp, Loader2, Sparkles } from "lucide-react";

const BASE_URL = "/api";

function MessageBubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      {!isUser && (
        <div className="w-7 h-7 rounded-full bg-violet-600 flex items-center justify-center mr-2 mt-0.5 shrink-0">
          <Sparkles size={13} className="text-white" />
        </div>
      )}
      <div
        className={`max-w-[82%] px-3 py-2 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? "bg-violet-600 text-white rounded-tr-sm"
            : "bg-zinc-800 text-zinc-100 rounded-tl-sm border border-zinc-700"
        }`}
        dir="auto"
      >
        {msg.content}
        {msg.streaming && (
          <span className="inline-block w-1.5 h-4 bg-violet-400 animate-pulse ml-0.5 rounded-sm align-middle" />
        )}
      </div>
    </div>
  );
}

export default function AIAssistant() {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "שלום! אני כאן לעזור לך עם ניתוח התיק, מניות מהבריפינג, ושאלות מסחריות. שאלי אותי על כל מניה, פוזיציה, או הזדמנות.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    if (open && !minimized) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, open, minimized]);

  useEffect(() => {
    if (open && !minimized) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open, minimized]);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { role: "user", content: text };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput("");
    setLoading(true);

    // Add placeholder for streaming assistant reply
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", streaming: true },
    ]);

    try {
      // Send only role+content (strip streaming flag)
      const apiMessages = history.map(({ role, content }) => ({ role, content }));

      const response = await fetch(`${BASE_URL}/ai/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: apiMessages }),
        signal: (abortRef.current = new AbortController()).signal,
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.token) {
              accumulated += payload.token;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: accumulated,
                  streaming: true,
                };
                return updated;
              });
            } else if (payload.done) {
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: accumulated,
                  streaming: false,
                };
                return updated;
              });
            } else if (payload.error) {
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: `שגיאה: ${payload.error}`,
                  streaming: false,
                };
                return updated;
              });
            }
          } catch (_) {}
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: "שגיאת חיבור — נסי שוב.",
            streaming: false,
          };
          return updated;
        });
      }
    } finally {
      setLoading(false);
    }
  }, [input, messages, loading]);

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-violet-600 hover:bg-violet-500 shadow-lg shadow-violet-900/50 flex items-center justify-center transition-all hover:scale-105 active:scale-95"
        title="AI Trading Assistant"
      >
        <Bot size={24} className="text-white" />
      </button>
    );
  }

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex flex-col bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl shadow-black/60 transition-all duration-200 ${
        minimized ? "w-72 h-12" : "w-96 h-[520px]"
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2.5 border-b border-zinc-700 rounded-t-2xl bg-zinc-800/80 shrink-0">
        <div className="w-7 h-7 rounded-full bg-violet-600 flex items-center justify-center">
          <Sparkles size={13} className="text-white" />
        </div>
        <span className="flex-1 text-sm font-semibold text-zinc-100 truncate">AI Trading Assistant</span>
        <button
          onClick={() => setMinimized((v) => !v)}
          className="p-1 rounded hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          {minimized ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        <button
          onClick={() => {
            setOpen(false);
            abortRef.current?.abort();
          }}
          className="p-1 rounded hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          <X size={16} />
        </button>
      </div>

      {!minimized && (
        <>
          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-0.5 scrollbar-thin scrollbar-thumb-zinc-700">
            {messages.map((msg, i) => (
              <MessageBubble key={i} msg={msg} />
            ))}
            {loading && messages[messages.length - 1]?.content === "" && (
              <div className="flex justify-start mb-3">
                <div className="w-7 h-7 rounded-full bg-violet-600 flex items-center justify-center mr-2 mt-0.5 shrink-0">
                  <Sparkles size={13} className="text-white" />
                </div>
                <div className="px-3 py-2 rounded-2xl rounded-tl-sm bg-zinc-800 border border-zinc-700">
                  <Loader2 size={16} className="animate-spin text-violet-400" />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="px-3 pb-3 pt-2 border-t border-zinc-700 shrink-0">
            <div className="flex items-end gap-2 bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 focus-within:border-violet-500 transition-colors">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKey}
                placeholder="שאלי על מניה, תיק, הזדמנות..."
                dir="auto"
                rows={1}
                className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-500 resize-none outline-none max-h-28 leading-relaxed"
                style={{ lineHeight: "1.5" }}
                onInput={(e) => {
                  e.target.style.height = "auto";
                  e.target.style.height = Math.min(e.target.scrollHeight, 112) + "px";
                }}
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim() || loading}
                className="shrink-0 w-8 h-8 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center transition-colors"
              >
                <Send size={15} className="text-white" />
              </button>
            </div>
            <p className="text-xs text-zinc-600 mt-1.5 text-center">Enter לשליחה · Shift+Enter לשורה חדשה</p>
          </div>
        </>
      )}
    </div>
  );
}
