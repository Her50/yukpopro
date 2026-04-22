import { ReactNode } from 'react'
import { clsx } from 'clsx'
import { ChatMessage } from '../api/types'
import { format } from 'date-fns'
import { fr } from 'date-fns/locale'

// ─── Inline markdown parser ───────────────────────────────────────────────────

function renderInline(text: string): ReactNode[] {
  const parts: ReactNode[] = []
  // Matches **bold**, *italic*, _italic_, `code`
  const regex = /(\*\*[^*\n]+?\*\*|\*[^*\n]+?\*|_[^_\n]+?_|`[^`\n]+?`)/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    const token = match[0]
    const key = match.index
    if (token.startsWith('**')) {
      parts.push(<strong key={key} className="font-semibold">{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`')) {
      parts.push(
        <code key={key} className="bg-gray-100 text-pink-600 px-1.5 py-0.5 rounded text-xs font-mono">
          {token.slice(1, -1)}
        </code>
      )
    } else {
      // *italic* or _italic_
      parts.push(<em key={key} className="italic">{token.slice(1, -1)}</em>)
    }
    lastIndex = regex.lastIndex
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex))
  return parts.length ? parts : [text]
}

// ─── Block markdown renderer ──────────────────────────────────────────────────

function MarkdownContent({ text, isUser }: { text: string; isUser?: boolean }) {
  const blocks = text.split('\n')
  const result: ReactNode[] = []
  let listBuffer: ReactNode[] = []
  let numListBuffer: ReactNode[] = []
  // Tracks the running start index across consecutive flushes of the same list.
  // Preserved through empty lines / bullet interruptions; reset on unrelated content.
  let numListSeqStart = 1
  let codeLines: string[] = []
  let inCode = false
  let codeKey = 0

  const flushList = () => {
    if (listBuffer.length) {
      result.push(
        <ul key={`ul-${result.length}`} className="list-none space-y-1 my-1.5 pl-1">
          {listBuffer}
        </ul>
      )
      listBuffer = []
    }
  }
  // interrupted=true  → list was broken by a bullet/empty line but continues (keep counter)
  // interrupted=false → list ended by a paragraph/heading (reset counter to 1)
  const flushNumList = (interrupted = false) => {
    if (numListBuffer.length) {
      result.push(
        <ol key={`ol-${result.length}`} start={numListSeqStart} className="list-decimal list-inside space-y-1 my-1.5 pl-1">
          {numListBuffer}
        </ol>
      )
      numListSeqStart += numListBuffer.length
      numListBuffer = []
    }
    if (!interrupted) numListSeqStart = 1
  }

  blocks.forEach((line, idx) => {
    // Code block fence
    if (line.trimStart().startsWith('```')) {
      if (!inCode) {
        flushList(); flushNumList(false)
        inCode = true
        codeLines = []
        codeKey = idx
      } else {
        result.push(
          <pre key={`code-${codeKey}`} className="bg-gray-900 text-green-300 rounded-lg p-3 my-2 text-xs overflow-x-auto font-mono leading-relaxed">
            {codeLines.join('\n')}
          </pre>
        )
        inCode = false
      }
      return
    }
    if (inCode) { codeLines.push(line); return }

    // Headings
    if (line.startsWith('### ')) {
      flushList(); flushNumList(false)
      result.push(
        <h3 key={idx} className={clsx('font-bold text-sm mt-3 mb-1', isUser ? 'text-white' : 'text-gray-800')}>
          {renderInline(line.slice(4))}
        </h3>
      )
      return
    }
    if (line.startsWith('## ')) {
      flushList(); flushNumList(false)
      result.push(
        <h2 key={idx} className={clsx('font-bold text-base mt-3 mb-1', isUser ? 'text-white' : 'text-gray-800')}>
          {renderInline(line.slice(3))}
        </h2>
      )
      return
    }
    if (line.startsWith('# ')) {
      flushList(); flushNumList(false)
      result.push(
        <h1 key={idx} className={clsx('font-bold text-lg mt-3 mb-1', isUser ? 'text-white' : 'text-gray-800')}>
          {renderInline(line.slice(2))}
        </h1>
      )
      return
    }

    // Horizontal rule
    if (/^[-*_]{3,}$/.test(line.trim())) {
      flushList(); flushNumList(false)
      result.push(<hr key={idx} className="border-gray-200 my-2" />)
      return
    }

    // Bullet list — interrupts a numbered list but keeps the counter alive
    if (/^[-•*] /.test(line)) {
      flushNumList(true)
      const content = line.replace(/^[-•*] /, '')
      listBuffer.push(
        <li key={idx} className="flex gap-2 items-start text-sm leading-relaxed">
          <span className={clsx('mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0', isUser ? 'bg-primary-200' : 'bg-primary-500')} />
          <span>{renderInline(content)}</span>
        </li>
      )
      return
    }

    // Numbered list
    const numMatch = line.match(/^(\d+)\. (.+)/)
    if (numMatch) {
      flushList()
      numListBuffer.push(
        <li key={idx} className="text-sm leading-relaxed">
          {renderInline(numMatch[2])}
        </li>
      )
      return
    }

    // Blockquote
    if (line.startsWith('> ')) {
      flushList(); flushNumList(false)
      result.push(
        <blockquote key={idx} className={clsx(
          'border-l-4 pl-3 py-0.5 my-1 text-sm italic',
          isUser ? 'border-primary-300 text-primary-100' : 'border-primary-300 text-gray-500'
        )}>
          {renderInline(line.slice(2))}
        </blockquote>
      )
      return
    }

    // Empty line — flush bullets but keep numbered list counter alive
    if (!line.trim()) {
      flushList()
      flushNumList(true)
      result.push(<div key={idx} className="h-1.5" />)
      return
    }

    // Regular paragraph — ends any list sequence and resets counter
    flushList(); flushNumList(false)
    result.push(
      <p key={idx} className="text-sm leading-relaxed">
        {renderInline(line)}
      </p>
    )
  })

  flushList()
  flushNumList()
  return <div className="space-y-0.5 break-words">{result}</div>
}

// ─── Components ───────────────────────────────────────────────────────────────

interface MessageBubbleProps {
  message: ChatMessage
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={clsx(
        'flex gap-3 animate-fade-in',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      <div
        className={clsx(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold',
          isUser ? 'bg-primary-600 text-white' : 'bg-accent-500 text-white'
        )}
      >
        {isUser ? 'V' : 'Y'}
      </div>
      <div
        className={clsx(
          'max-w-[75%] rounded-2xl px-4 py-3 shadow-sm',
          isUser
            ? 'bg-primary-600 text-white rounded-tr-sm'
            : 'bg-white text-gray-800 border border-gray-100 rounded-tl-sm'
        )}
      >
        <MarkdownContent text={message.content} isUser={isUser} />
        <div
          className={clsx(
            'text-xs mt-1.5',
            isUser ? 'text-primary-200 text-right' : 'text-gray-400'
          )}
        >
          {format(new Date(message.created_at), 'HH:mm', { locale: fr })}
        </div>
      </div>
    </div>
  )
}

export function TypingIndicator() {
  return (
    <div className="flex gap-3 animate-fade-in">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-500 flex items-center justify-center text-sm font-bold text-white">
        Y
      </div>
      <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center h-5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-2 h-2 bg-gray-400 rounded-full animate-pulse-dot"
              style={{ animationDelay: `${i * 0.16}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

export function StreamingBubble({ content }: { content: string }) {
  return (
    <div className="flex gap-3 animate-fade-in">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-500 flex items-center justify-center text-sm font-bold text-white">
        Y
      </div>
      <div className="max-w-[75%] bg-white border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
        <MarkdownContent text={content} />
        <span className="inline-block w-0.5 h-4 bg-gray-400 animate-pulse ml-0.5 align-middle" />
      </div>
    </div>
  )
}
