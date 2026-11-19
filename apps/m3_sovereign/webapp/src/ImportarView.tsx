import { useState, useEffect } from 'react';
import { rizoma } from './lib/rizoma';
import type { UserProfile } from './lib/rizoma';

// WP-21 / escalera de custodia (01_red §5): la persona se lleva su llave
// delegada del puente a este dispositivo. El bot dio un código de un solo uso
// con /llave; acá se canjea contra el nodo y la llave queda custodiada local.
// Subir de escalón no cambia identidad ni historial: la dirección es la misma.

const API_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

export default function ImportarView({ onImported, onCancelar }: {
  onImported: (profile: UserProfile) => void,
  onCancelar: () => void,
}) {
  const [codigo, setCodigo] = useState('');
  const [estado, setEstado] = useState<'idle' | 'canjeando' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);

  // Permitir código en el hash (#/importar/<codigo>) además del pegado manual.
  useEffect(() => {
    const m = window.location.hash.match(/#\/importar\/([0-9a-fA-F]+)/);
    if (m) setCodigo(m[1]);
  }, []);

  const importar = async () => {
    const c = codigo.trim();
    if (!c || estado === 'canjeando') return;
    setEstado('canjeando');
    setError(null);
    try {
      const res = await fetch(`${API_URL}/puente/canjear-llave`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codigo: c }),
      });
      if (!res.ok) {
        const detalle = await res.json().catch(() => ({} as any));
        throw new Error(detalle.detail || `HTTP_${res.status}`);
      }
      const { private_key } = await res.json();
      if (!private_key) throw new Error('el nodo no devolvió la llave');
      const profile = await rizoma.importarLlave(private_key);
      onImported(profile);
    } catch (e: any) {
      setEstado('error');
      setError(e?.message || 'no se pudo canjear');
    }
  };

  return (
    <div className="bg-[#131314] min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <h1 className="text-4xl font-black tracking-tighter text-white leading-none mb-2">
          Llevarte tu llave
        </h1>
        <p className="font-mono text-primary text-xs tracking-[0.25em] mb-8 opacity-40">
          ESCALERA_DE_CUSTODIA
        </p>
        <p className="text-sm text-outline mb-8 leading-relaxed">
          Tu identidad es tuya. Pegá el código de un solo uso que te dio el bot
          con <span className="font-mono text-white">/llave</span> y pasa a
          custodiarse en este dispositivo. Tu dirección y tu historial no cambian.
        </p>

        <input
          className="chat-input w-full h-14 text-center text-lg font-mono tracking-wider border-2 border-white/5 focus:border-primary !bg-[#0a0a0a] !text-white rounded-2xl mb-4"
          placeholder="código"
          value={codigo}
          onChange={(e) => { setCodigo(e.target.value); setEstado('idle'); }}
          autoFocus
        />

        {estado === 'error' && (
          <p className="font-mono text-[11px] text-red-400 uppercase mb-4 text-center">
            {error} (el código vence en 5 minutos y es de un solo uso)
          </p>
        )}

        <button
          onClick={importar}
          disabled={!codigo.trim() || estado === 'canjeando'}
          className="btn-primary w-full h-14 text-lg font-black rounded-2xl uppercase disabled:opacity-20 disabled:cursor-not-allowed"
        >
          {estado === 'canjeando' ? 'Canjeando...' : 'Importar mi llave'}
        </button>

        <button
          onClick={onCancelar}
          className="w-full mt-4 py-3 font-mono text-xs text-outline hover:text-white uppercase tracking-widest"
        >
          Entrar con correo en su lugar
        </button>
      </div>
    </div>
  );
}
