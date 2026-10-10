// T13 #22 MQTT JSON과 REST 응답에 대응하는 TypeScript 구조.
// 입력: web_api.md / mqtt.md. 출력: 화면 표시를 위한 타입.
export type SortState = { state:string; box_id:string; pending_question:string; track_id:number; ready:boolean; not_ready:string[]; session_id:string };
export type RobotState = { connected:boolean; state:string; action:string; gripper_width_mm:number; error_code:string; detail:string; stamp:string };
export type SortResult = { box_id?:string; code?:string; dong?:string; zone?:string; outcome?:string; confidence?:number; decided_by?:string; raw_text?:string; reason?:string; [key:string]:unknown };
export type ZoneMap = { version:string; entries:{dong:string;zone:string;code:string;aliases:string[]}[] };
export type Summary = { ok:true; session_id:string; planned:number; placed:number; held:number; failed:number; passed:number; remaining:number; by_zone:Record<string,number>; as_of:string };
export type ApiError = { ok:false; message:string; detail?:string };
export type LinkStatus = 'UP'|'DOWN';
export type CommandType = 'start'|'stop'|'resume'|'priority'|'answer'|'reset_zone';
