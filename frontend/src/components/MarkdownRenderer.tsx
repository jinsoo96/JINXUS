'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { Copy, Check, ChevronDown, ChevronUp } from 'lucide-react';
import { useState, useCallback, memo, useRef, useEffect } from 'react';

function CopyButton({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [code]);

  return (
    <button onClick={handleCopy}
      className="p-1.5 rounded-md bg-zinc-700 hover:bg-zinc-600 transition-colors text-zinc-300"
      title="복사"
    >
      {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
    </button>
  );
}

// 코드 블록 (NextChat 패턴: 400px 초과 시 자동 접기)
function CodeBlock({ language, code }: { language: string; code: string }) {
  const [collapsed, setCollapsed] = useState(true);
  const codeRef = useRef<HTMLDivElement>(null);
  const [isLong, setIsLong] = useState(false);

  useEffect(() => {
    if (codeRef.current && codeRef.current.scrollHeight > 400) {
      setIsLong(true);
    }
  }, [code]);

  return (
    <div className="relative group my-3">
      <div className="flex items-center justify-between px-4 py-1.5 bg-zinc-800 rounded-t-lg border-b border-zinc-700">
        <span className="text-xs text-zinc-400 font-mono">{language}</span>
        <div className="flex items-center gap-1">
          {isLong && (
            <button onClick={() => setCollapsed(!collapsed)}
              className="p-1 rounded hover:bg-zinc-600 text-zinc-400 transition-colors"
              title={collapsed ? '펼치기' : '접기'}
            >
              {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
            </button>
          )}
          <CopyButton code={code} />
        </div>
      </div>
      <div ref={codeRef}
        style={{ maxHeight: collapsed && isLong ? '400px' : undefined, overflow: 'hidden', position: 'relative' }}
      >
        <SyntaxHighlighter style={oneDark} language={language} PreTag="div"
          customStyle={{ margin: 0, borderTopLeftRadius: 0, borderTopRightRadius: 0, fontSize: '0.85rem' }}
        >
          {code}
        </SyntaxHighlighter>
        {collapsed && isLong && (
          <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-[#282c34] to-transparent pointer-events-none" />
        )}
      </div>
      {collapsed && isLong && (
        <button onClick={() => setCollapsed(false)}
          className="w-full py-1.5 text-xs text-zinc-400 hover:text-zinc-200 bg-zinc-800/80 rounded-b-lg border-t border-zinc-700 transition-colors"
        >
          코드 전체 보기 ({code.split('\n').length}줄)
        </button>
      )}
    </div>
  );
}

// components 객체를 컴포넌트 외부에서 한 번만 생성
const markdownComponents = {
  code({ className, children, ...props }: { className?: string; children?: React.ReactNode; [key: string]: unknown }) {
    const match = /language-(\w+)/.exec(className || '');
    const codeString = String(children).replace(/\n$/, '');

    if (match) {
      return <CodeBlock language={match[1]} code={codeString} />;
    }

    return (
      <code className="bg-zinc-700/50 text-primary px-1.5 py-0.5 rounded text-sm" {...props}>
        {children}
      </code>
    );
  },
  a({ href, children }: { href?: string; children?: React.ReactNode }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
        {children}
      </a>
    );
  },
  table({ children }: { children?: React.ReactNode }) {
    return (
      <div className="overflow-x-auto my-3">
        <table className="min-w-full border border-zinc-700 text-sm">{children}</table>
      </div>
    );
  },
  th({ children }: { children?: React.ReactNode }) {
    return <th className="border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-left">{children}</th>;
  },
  td({ children }: { children?: React.ReactNode }) {
    return <td className="border border-zinc-700 px-3 py-1.5">{children}</td>;
  },
};

const remarkPlugins = [remarkGfm];

// React.memo — content 같으면 재렌더링 안 함
const MarkdownRenderer = memo(function MarkdownRenderer({ content }: { content: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none break-words">
      <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents as never}>
        {content}
      </ReactMarkdown>
    </div>
  );
});

export default MarkdownRenderer;
