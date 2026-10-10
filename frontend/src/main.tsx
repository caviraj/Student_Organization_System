import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';

async function enableMocking() {
  if (import.meta.env.VITE_USE_MOCKS === 'true') {
    const { worker } = await import('./mocks/browser');
    return worker.start({
      onUnhandledFrame: 'bypass',
    });
  }
}

enableMocking().finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
});
