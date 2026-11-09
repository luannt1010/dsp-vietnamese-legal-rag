import { useEffect, useRef, useState } from 'react';
import { askQuestion } from '../../../api/questions';
import { ApiError } from '../../../api/client';
import { validateQuery } from '../validation';
import type { QuestionEntry } from '../types';

// Session state lives above the screens, so switching history never cancels a request.
// Nothing is persisted to localStorage or sent as conversational memory.
export function useQuestionSession() {
  const [entries, setEntries] = useState<QuestionEntry[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const locked = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function submit(query: string): Promise<boolean> {
    if (locked.current || validateQuery(query)) return false;
    locked.current = true;
    setIsSending(true);
    const id = crypto.randomUUID();
    const entry = { id, query: query.trim(), createdAt: Date.now() };
    setEntries((current) => [{ ...entry, state: 'pending' }, ...current]);
    setActiveId(id);
    try {
      const response = await askQuestion(entry.query);
      if (mounted.current)
        setEntries((current) =>
          current.map((item) =>
            item.id === id ? { ...entry, state: 'answered', response } : item,
          ),
        );
      return response.status === 'completed' || response.status === 'insufficient_evidence';
    } catch (error) {
      const failure =
        error instanceof ApiError
          ? error
          : new ApiError('Không thể hoàn tất câu hỏi. Vui lòng thử lại.', 'network');
      if (mounted.current)
        setEntries((current) =>
          current.map((item) =>
            item.id === id ? { ...entry, state: 'error', error: failure } : item,
          ),
        );
      return false;
    } finally {
      locked.current = false;
      if (mounted.current) setIsSending(false);
    }
  }

  return {
    entries,
    activeId,
    select: setActiveId,
    isSending,
    submit,
    activeEntry: entries.find((entry) => entry.id === activeId),
    newQuestion: () => setActiveId(null),
  };
}
