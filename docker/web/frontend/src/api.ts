// T13 #22 서버와 같은 출처의 REST API만 호출한다.
// 입력: 명령·조회 파라미터. 출력: 계약 JSON 또는 실패 코드.
// 근거: docs/interfaces/web_api.md.
import type { ApiError, CommandType, SortResult, Summary } from './types';

export class RequestFailure extends Error {
  constructor(public readonly code:string, public readonly status:number, message:string) { super(message); }
}

export async function request<T>(url:string, init?:RequestInit):Promise<T> {
  let response:Response;
  try { response = await fetch(url, { ...init, headers: {'Content-Type':'application/json', ...init?.headers}, cache:'no-store' }); }
  catch { throw new RequestFailure('NETWORK_DOWN', 0, '웹 서버에 연결할 수 없습니다.'); }
  if (!response.ok) {
    const body = await response.json().catch(()=>null) as ApiError|null;
    throw new RequestFailure(body?.message ?? 'HTTP_ERROR', response.status, body?.detail ?? '요청을 처리하지 못했습니다.');
  }
  return response.json() as Promise<T>;
}

export function getSummary():Promise<Summary> { return request('/api/sessions/current'); }
export function getResults(sessionId:string, result?:string):Promise<{items:SortResult[]}> {
  const params = new URLSearchParams({session_id:sessionId, limit:'50'});
  if (result) params.set('result',result);
  return request(`/api/results?${params}`);
}
export function putPlan(planned:number):Promise<Summary> {
  return request('/api/sessions/current/plan',{method:'PUT',body:JSON.stringify({planned})});
}
export function issueCommand(type:CommandType,args:Record<string,string>={}):Promise<{command_id:string}> {
  return request('/api/commands',{method:'POST',body:JSON.stringify({type,args,raw_text:'HMI 버튼'})});
}
