// T13 #22 서버와 같은 출처의 REST API만 호출한다.
// 입력: 명령·조회 파라미터. 출력: 계약 JSON 또는 실패 코드.
// 근거: docs/interfaces/web_api.md.
import type { ApiError, CommandType, PalletPlacements, SortResult, Summary } from './types';

const REQUEST_TIMEOUT_MS = 5000;

export class RequestFailure extends Error {
  constructor(public readonly code:string, public readonly status:number, message:string) { super(message); }
}

export async function request<T>(url:string, init?:RequestInit):Promise<T> {
  let response:Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: {'Content-Type':'application/json', ...init?.headers},
      cache:'no-store',
      signal: init?.signal ?? AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (failure) {
    if (failure instanceof DOMException && failure.name === 'TimeoutError') {
      throw new RequestFailure('TIMEOUT', 0, 'API 요청이 시간 제한을 초과했습니다.');
    }
    throw new RequestFailure('NETWORK_DOWN', 0, '웹 서버에 연결할 수 없습니다.');
  }
  if (!response.ok) {
    const body = await response.json().catch(()=>null) as ApiError|null;
    throw new RequestFailure(body?.message ?? 'HTTP_ERROR', response.status, body?.detail ?? '요청을 처리하지 못했습니다.');
  }
  return response.json() as Promise<T>;
}

export function getSummary():Promise<Summary> { return request('/api/sessions/current'); }
export function getLatestPalletPlacements():Promise<PalletPlacements> { return request('/api/pallet/placements/latest'); }
export function getResults(sessionId:string, result?:string):Promise<{items:SortResult[]}> {
  const params = new URLSearchParams({session_id:sessionId, limit:'50'});
  if (result) params.set('result',result);
  return request(`/api/results?${params}`);
}
export function putPlan(planned:number):Promise<Summary> {
  return request('/api/sessions/current/plan',{method:'PUT',body:JSON.stringify({planned})});
}
export type CommandArgs = Record<string,string|string[]>;  // palletize 의 route 만 배열 (web_api.md)
export function issueCommand(type:CommandType,args:CommandArgs={}):Promise<{command_id:string}> {
  return request('/api/commands',{method:'POST',body:JSON.stringify({type,args,raw_text:'HMI 버튼'})});
}
export function announceVoice(action:CommandType|'plan'):Promise<{request_id:string}> {
  return request('/api/voice/announce',{method:'POST',body:JSON.stringify({action})});
}
export function submitTextCommand(text:string,requestId:string):Promise<{request_id:string}> {
  return request('/api/voice/text',{method:'POST',body:JSON.stringify({text,request_id:requestId})});
}
