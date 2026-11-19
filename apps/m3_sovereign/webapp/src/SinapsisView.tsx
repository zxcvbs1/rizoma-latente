import { useState, useEffect, useCallback } from 'react';
import { rizoma } from './lib/rizoma';
import type { UserProfile } from './lib/rizoma';

// WP-02 (INV-01/02): el enlace de la propuesta abre ESTA vista: el texto
// original del otro y un campo vacío. No hay botón de aceptar; el único acto
// es escribir la primera palabra dirigida. La palabra viaja cifrada al topic
// derivado; al servidor solo va la transición de estado, firmada.

const API_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

interface Lado { actor: string; node: string; text: string | null; public_key?: string | null; }
interface Sinapsis { synapse_id: string; status: string; addressed_by: string | null; origin: Lado; target: Lado; }

export default function SinapsisView({ sinapsisId, profile, onNotify, onIrAlTunel }: {
  sinapsisId: string,
  profile: UserProfile,
  onNotify: (texto: string) => void,
  onIrAlTunel: () => void,
}) {
  const [sinapsis, setSinapsis] = useState<Sinapsis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [palabra, setPalabra] = useState('');
  const [enviando, setEnviando] = useState(false);

  const cargar = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/synapses/${sinapsisId}`);
      if (!res.ok) throw new Error(`HTTP_${res.status}`);
      setSinapsis(await res.json());
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'SIN_CONEXION');
    }
  }, [sinapsisId]);

  useEffect(() => { cargar(); }, [cargar]);

  if (error) return (
    <div className="animate-fade-in liquid-card p-10 border border-white/10 rounded-[2rem] text-center">
      <p className="font-mono text-sm text-outline uppercase">No pude leer la sinapsis ({error}).</p>
      <button onClick={cargar} className="mt-6 font-mono text-xs text-primary font-black uppercase">[ Reintentar ]</button>
    </div>
  );
  if (!sinapsis) return <p className="font-mono text-xs text-outline uppercase animate-pulse">Leyendo la sinapsis...</p>;

  const yo = profile.address.toLowerCase();
  const soyOrigin = (sinapsis.origin.actor || '').toLowerCase() === yo;
  const soyParte = soyOrigin || (sinapsis.target.actor || '').toLowerCase() === yo;
  const otro = soyOrigin ? sinapsis.target : sinapsis.origin;
  const yaMeDirigi = (sinapsis.addressed_by || '').toLowerCase() === yo;
  const estado = sinapsis.status;

  const dirigirse = async () => {
    if (!palabra.trim() || enviando) return;
    setEnviando(true);
    try {
      const timestamp = new Date().toISOString();
      const nonce = crypto.randomUUID().replace(/-/g, '');
      const canonical = `rizoma.link|${profile.address}|${timestamp}|${nonce}|${sinapsis.origin.node}|${sinapsis.target.node}`;
      const signature = await rizoma.signActo(canonical);

      const res = await fetch(`${API_URL}/synapses/${sinapsisId}/address`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor_id: profile.address, timestamp, nonce, signature }),
      });
      if (!res.ok) {
        const detalle = await res.json().catch(() => ({} as any));
        throw new Error(detalle.detail || `HTTP_${res.status}`);
      }

      // La palabra en sí: solo por el túnel cifrado, jamás por la API.
      if (otro.public_key) {
        try {
          await rizoma.sendMessage(otro.actor, palabra, otro.public_key);
          onNotify('Tu palabra viajó cifrada por el túnel');
        } catch {
          onNotify('Acto registrado; el túnel P2P está offline, reintentá al entrar');
        }
      } else {
        onNotify('Acto registrado; la clave del otro aparece cuando vuelva a emitir');
      }
      setPalabra('');
      await cargar();
    } catch (e: any) {
      onNotify(`No se pudo: ${e?.message || 'error'}`);
    } finally {
      setEnviando(false);
    }
  };

  const abrirTunel = () => {
    if (otro.actor) {
      rizoma.saveContact({
        address: otro.actor,
        publicKey: otro.public_key || undefined,
        alias: `Actor-${otro.actor.slice(-4).toUpperCase()}`,
        email: '',
      });
    }
    onIrAlTunel();
  };

  return (
    <div className="animate-fade-in space-y-10 max-w-2xl mx-auto">
      <div className="flex justify-between items-end border-b-2 border-white/5 pb-6">
        <h2 className="text-4xl font-black text-white tracking-tighter">SINAPSIS</h2>
        <span className="font-mono text-[10px] text-primary font-black uppercase tracking-widest bg-primary/10 px-3 py-1 rounded-full">{estado}</span>
      </div>

      <article className="liquid-card p-8 border border-white/10 rounded-[2rem] bg-white/[0.02]">
        <span className="font-mono text-[9px] text-outline/40 uppercase font-black tracking-widest block mb-4">Texto original del otro, sin resumen</span>
        <p className="text-2xl font-black text-white leading-tight tracking-tight">"{otro.text || '...'}"</p>
        <span className="font-mono text-[9px] text-outline/30 uppercase block mt-4 truncate">{otro.actor}</span>
      </article>

      {!soyParte && (
        <p className="font-mono text-xs text-outline uppercase text-center">No sos parte de esta sinapsis; solo podés ver su estado.</p>
      )}

      {soyParte && (estado === 'proposed' || (estado === 'addressed' && !yaMeDirigi)) && (
        <div className="space-y-6">
          {estado === 'addressed' && (
            <p className="font-mono text-[10px] text-secondary uppercase font-black tracking-widest">El otro ya te dirigió su palabra: está en el túnel cifrado.</p>
          )}
          <textarea
            className="chat-input w-full h-36 !bg-[#0a0a0a] !text-white text-lg font-medium border-2 border-white/10 focus:border-primary/60 transition-all resize-none p-6 rounded-2xl"
            value={palabra}
            onChange={(e) => setPalabra(e.target.value)}
            autoFocus
          />
          <button
            onClick={dirigirse}
            disabled={!palabra.trim() || enviando}
            className="btn-primary w-full py-5 text-sm font-black rounded-2xl uppercase disabled:opacity-20 disabled:cursor-not-allowed"
          >
            {enviando ? 'Firmando...' : 'Dirigirme'}
          </button>
          <p className="font-mono text-[9px] text-outline/40 uppercase leading-relaxed text-center">
            Tu palabra viaja cifrada de punta a punta; el servidor solo registra que te dirigiste.
            Si no escribís nada, esto expira solo y no queda registro.
          </p>
        </div>
      )}

      {soyParte && estado === 'addressed' && yaMeDirigi && (
        <p className="font-mono text-xs text-outline uppercase text-center leading-relaxed">
          Tu palabra está dicha. Falta la del otro.<br />Si no llega, esto expira en silencio.
        </p>
      )}

      {estado === 'active' && (
        <div className="text-center space-y-6">
          <p className="font-mono text-xs text-primary uppercase font-black tracking-widest">Vínculo activo: ambos se dirigieron.</p>
          {soyParte && (
            <button onClick={abrirTunel} className="btn-primary px-10 py-4 text-sm font-black rounded-2xl uppercase">Ir al túnel</button>
          )}
        </div>
      )}

      {estado === 'expired' && (
        <p className="font-mono text-xs text-outline uppercase text-center">Expiró en silencio. No queda registro de rechazo.</p>
      )}
    </div>
  );
}
