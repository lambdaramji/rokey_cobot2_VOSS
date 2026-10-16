import { useEffect, useRef, useState } from 'react';
import { RequestFailure, submitTextCommand } from '../api';
import type { PalletState } from '../types';

export interface TextReply { request_id: string; message: string }
export interface ChatQuestion { key: string; boxId: string; text: string }
type Entry = { kind: 'command'; id: string; text: string; reply: string }
  | { kind: 'notice'; id: string; text: string };

export function TextCommandPanel({connected, enabled, reply, asking, pallet}: {
  connected: boolean; enabled: boolean; reply: TextReply | null;
  asking: ChatQuestion | null; pallet: PalletState | null;
}) {
  const [text, setText] = useState('');
  const [entries, setEntries] = useState<Entry[]>([]);
  const [sending, setSending] = useState(false);
  const historyRef = useRef<HTMLDivElement>(null);
  const lastQuestion = useRef<string | null>(null);
  const lastPallet = useRef<{runId:string;state:string} | null>(null);

  useEffect(() => {
    if (!reply) return;
    setEntries(current => current.map(entry => entry.kind === 'command' && entry.id === reply.request_id
      ? {...entry, reply: reply.message} : entry));
  }, [reply]);

  useEffect(() => {
    if (!asking) { lastQuestion.current = null; return; }
    if (lastQuestion.current === asking.key) return;
    lastQuestion.current = asking.key;
    setEntries(current => [...current.slice(-29), {
      kind:'notice', id:`asking:${asking.key}`, text:`재확인 질문 · ${asking.boxId}\n${asking.text}`,
    }]);
  }, [asking]);

  useEffect(() => {
    if (!pallet) { lastPallet.current = null; return; }
    const previous = lastPallet.current;
    lastPallet.current = {runId:pallet.run_id,state:pallet.state};
    let message = '';
    if (pallet.run_id && pallet.state === 'RUNNING' && previous?.runId !== pallet.run_id) {
      message = `팔레타이징 시작 · ${pallet.route.join(' → ')}`;
    } else if (pallet.run_id && pallet.state === 'DONE' && previous?.runId === pallet.run_id && previous.state !== 'DONE') {
      message = `팔레타이징 완료 · 적재 ${pallet.done}개${pallet.failed ? `, 실패 ${pallet.failed}개` : ''}`;
    } else if (!pallet.run_id && previous?.runId) {
      message = '트럭 짐칸 비움이 확인됐습니다.';
    }
    if (message) setEntries(current => [...current.slice(-29), {
      kind:'notice', id:`pallet:${pallet.run_id}:${pallet.state}:${Date.now()}`, text:message,
    }]);
  }, [pallet]);

  useEffect(() => {
    if (historyRef.current) historyRef.current.scrollTop = historyRef.current.scrollHeight;
  }, [entries]);

  async function send() {
    const message = text.trim();
    if (!message || !enabled || !connected || sending) return;
    const id = crypto.randomUUID();
    setEntries(current => [...current.slice(-29), {kind:'command', id, text: message, reply: '명령 해석 중…'}]);
    setText('');
    setSending(true);
    try {
      await submitTextCommand(message, id);
      window.setTimeout(() => setEntries(current => current.map(entry =>
        entry.kind === 'command' && entry.id === id && entry.reply === '명령 해석 중…'
          ? {...entry, reply: '응답이 지연되고 있습니다. 음성 노드와 MQTT 연결을 확인해 주세요.'}
          : entry)), 15000);
    } catch (error) {
      const detail = error instanceof RequestFailure ? `${error.code} · ${error.message}` : '전달에 실패했습니다.';
      setEntries(current => current.map(entry => entry.kind === 'command' && entry.id === id ? {...entry, reply: detail} : entry));
    } finally {
      setSending(false);
    }
  }

  return <section className="panel text-command-panel">
    <div className="section-heading"><div><span className="eyebrow">TEXT / INTENT</span><h2>텍스트 명령</h2></div><span className="micro-note">Web PC 로컬 입력</span></div>
    <div className="text-command-history" role="log" aria-live="polite" ref={historyRef}>
      {entries.map(entry => entry.kind === 'notice'
        ? <p className="text-command-question" key={entry.id}>{entry.text}</p>
        : <div className="text-command-turn" key={entry.id}>
        <p className="text-command-user">{entry.text}</p>
        <p className="text-command-reply">{entry.reply}</p>
      </div>)}
    </div>
    <form className="text-command-form" onSubmit={event => {event.preventDefault(); void send();}}>
      <input aria-label="로봇 명령 입력" value={text} maxLength={240}
        onChange={event => setText(event.target.value)} placeholder="명령을 입력하세요"
        disabled={!enabled || !connected || sending}/>
      <button type="submit" disabled={!enabled || !connected || sending || !text.trim()}>전송</button>
    </form>
    {!enabled && <p className="micro-note">명령 입력은 Web PC 로컬에서만 가능합니다.</p>}
  </section>;
}
