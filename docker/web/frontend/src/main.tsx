// T13 #22 React 웹 HMI 진입점.
// 입력: Spring Boot REST/SSE. 출력: 분류 관제 화면.
// 근거: ADR-0006, docs/interfaces/web_api.md.
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
