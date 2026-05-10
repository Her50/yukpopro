/**
 * Sprint S1.3 — Page Chat Unifié YukpoSecrétariat.
 *
 * Page d'entrée par défaut. L'utilisateur arrive ici, tape son besoin,
 * Yukpo route automatiquement vers le bon module. Plus besoin de naviguer
 * entre rédaction / OCR / audio / infographie / traduction.
 */
import ChatUnifieSec from '../components/ChatUnifieSec'

export default function ChatPage() {
  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-100px)]">
      <ChatUnifieSec />
    </div>
  )
}
