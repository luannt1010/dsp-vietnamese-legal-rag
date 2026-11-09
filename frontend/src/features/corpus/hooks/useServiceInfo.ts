import { useCallback, useEffect, useRef, useState } from 'react';
import { getCorpus } from '../../../api/corpus';
import { getReadiness } from '../../../api/health';
import type { CorpusResponse } from '../../../api/types';

export type ServiceState = 'checking' | 'ready' | 'unavailable';

export function useServiceInfo() {
  const [state, setState] = useState<ServiceState>('checking');
  const [corpus, setCorpus] = useState<CorpusResponse>();
  const [corpusError, setCorpusError] = useState(false);
  const [checkedAt, setCheckedAt] = useState<number>();
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    const current = ++generation.current;
    setState('checking');
    setCorpusError(false);
    const [health, snapshot] = await Promise.allSettled([getReadiness(), getCorpus()]);
    if (current !== generation.current) return;
    setState(
      health.status === 'fulfilled' && health.value.status === 'ready' ? 'ready' : 'unavailable',
    );
    setCorpus(snapshot.status === 'fulfilled' ? snapshot.value : undefined);
    setCorpusError(snapshot.status === 'rejected');
    setCheckedAt(Date.now());
  }, []);

  useEffect(() => {
    void refresh();
    return () => {
      generation.current += 1;
    };
  }, [refresh]);

  return { state, corpus, corpusError, checkedAt, refresh };
}
