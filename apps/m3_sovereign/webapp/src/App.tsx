import React, { useState, useEffect } from 'react';
import { rizoma } from './lib/rizoma';
import SinapsisView from './SinapsisView';
import ImportarView from './ImportarView';
import type { Conversation, UserProfile, RizomaStats, AddonComposition } from './lib/rizoma';

// --- HELPERS GLOBALES ---
const formatTime = (ts: number) => {
  const diff = Math.floor((Date.now() - ts) / 1000);
  if (diff < 60) return "AHORA";
  if (diff < 3600) return `${Math.floor(diff / 60)}M`;
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const MaterialIcon = ({ name, fill = 0, className = "" }: { name: string, fill?: number, className?: string }) => (
  <span className={`material-symbols-outlined ${className}`} style={{ fontVariationSettings: `'FILL' ${fill}`, fontSize: 'inherit' }}>
    {name}
  </span>
);

// --- COMPONENTE: MODAL ---
const DynamicModal = ({ modal, onClose }: { modal: any, onClose: () => void }) => {
  if (!modal) return null;
  const [formData, setFormData] = useState<any>({});
  return (
    <div className="fixed inset-0 bg-black/90 backdrop-blur-xl z-[9000] flex items-center justify-center p-4">
      <div className="bg-[#1f1f20] border border-white/20 p-8 rounded-2xl max-w-2xl w-full shadow-2xl animate-fade-in overflow-y-auto max-h-[90vh]">
        <h3 className="font-mono text-primary text-xl mb-6 border-b border-white/10 pb-4 tracking-tighter flex items-center gap-3">
          <MaterialIcon name="architecture" className="text-primary" />
          {`// ${modal.title.toUpperCase()}`}
        </h3>
        <div className="space-y-6">
          {modal.fields.map((f: any) => (
            <div key={f.name} className="relative group">
              <label className="font-mono text-[10px] text-outline uppercase block mb-2 font-black tracking-widest">{f.label}</label>
              {f.type === 'textarea' ? (
                <textarea 
                  className="chat-input h-32 !bg-[#1b1b1c] !text-white text-sm font-mono border border-white/5 focus:border-primary/50 transition-all resize-none p-4 rounded-xl" 
                  placeholder={f.placeholder}
                  value={formData[f.name] || ''} 
                  onChange={(e) => setFormData({...formData, [f.name]: e.target.value})} 
                  autoFocus={f.autoFocus} 
                />
              ) : f.type === 'number' ? (
                <div className="flex gap-2 items-center">
                  <button onClick={() => setFormData({ ...formData, [f.name]: (Number(formData[f.name] || 0)) - 1 })} className="w-10 h-10 border border-primary text-primary flex items-center justify-center rounded-lg hover:bg-primary/10 active:scale-95"><MaterialIcon name="remove" /></button>
                  <input className="chat-input h-10 !bg-[#1b1b1c] !text-white text-center font-black" type="number" value={formData[f.name] || ''} onChange={(e) => setFormData({...formData, [f.name]: e.target.value})} />
                  <button onClick={() => setFormData({ ...formData, [f.name]: (Number(formData[f.name] || 0)) + 1 })} className="w-10 h-10 border border-primary text-primary flex items-center justify-center rounded-lg hover:bg-primary/10 active:scale-95"><MaterialIcon name="add" /></button>
                </div>
              ) : (
                <input className="chat-input h-10 !bg-[#1b1b1c] !text-white text-sm" type={f.type || 'text'} value={formData[f.name] || ''} onChange={(e) => setFormData({...formData, [f.name]: e.target.value})} autoFocus />
              )}
            </div>
          ))}
        </div>
        <div className="flex gap-4 mt-8">
          <button onClick={onClose} className="flex-1 py-3 font-mono text-xs text-white border border-white/10 rounded-lg uppercase">Volver</button>
          <button onClick={() => { modal.onSubmit(formData); onClose(); }} className="flex-[1.5] btn-primary py-3 text-sm">Confirmar</button>
        </div>
      </div>
    </div>
  );
};

export default function App() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [view, setView] = useState<'radar' | 'inbox' | 'chat' | 'settings' | 'addons' | 'inventory' | 'login' | 'sinapsis' | 'importar'>('login');
  const [sinapsisId, setSinapsisId] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [, setNewAlias] = useState('');
  const [radarIntentions, setRadarIntentions] = useState<any[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [, setIsLoadingWaku] = useState(false);
  const [wakuStatusMsg, setWakuStatusMsg] = useState('OFFLINE');
  const [activeModal, setActiveModal] = useState<any>(null);
  const [latentSchemas, setLatentSchemas] = useState<any[]>([]);
  const [notifications, setNotifications] = useState<{id: number, text: string}[]>([]);
  const [, setViewingActor] = useState<{profile: UserProfile, stats: RizomaStats} | null>(null);

  const addNotification = (text: string) => {
    const id = Date.now();
    setNotifications(prev => [...prev, { id, text: text.toUpperCase() }]);
    setTimeout(() => setNotifications(prev => prev.filter(n => n.id !== id)), 3000);
  };

  const refreshRadar = async () => {
    setIsLoadingWaku(true);
    try {
      const data = await rizoma.fetchIntentions();
      setRadarIntentions(data);
    } catch (e) {} finally { setIsLoadingWaku(false); }
  };

  // WP-02: el enlace de la propuesta (#/sinapsis/{id}) abre el campo vacío.
  useEffect(() => {
    const leerHash = () => {
      const sin = window.location.hash.match(/#\/sinapsis\/([0-9a-fA-F-]+)/);
      if (sin) {
        setSinapsisId(sin[1]);
        if (profile) setView('sinapsis');
        return;
      }
      // Escalera de custodia: #/importar abre la pantalla de llave (sin sesión).
      if (window.location.hash.startsWith('#/importar')) setView('importar');
    };
    leerHash();
    window.addEventListener('hashchange', leerHash);
    return () => window.removeEventListener('hashchange', leerHash);
  }, [profile]);

  useEffect(() => {
    rizoma.getLatentSchemas().then(setLatentSchemas);
    rizoma.onStatusChange = (status) => setWakuStatusMsg(status === 'online' ? 'RED_ACTIVA' : 'BUSCANDO_PAR');
    // Restaura sesión sea por correo o por llave importada (escalera §5).
    rizoma.restaurarSesion().then(p => { if (p) { setProfile(p); setNewAlias(p.alias || ''); } });
  }, []);

  useEffect(() => {
    if (profile) {
      rizoma.getConversations().then(setConversations);
      if (view === 'radar') refreshRadar();
    }
  }, [profile, view]);

  useEffect(() => {
    let unsubFn: any = null;
    if (rizoma.wakuStatus === 'online') {
      rizoma.subscribeToIntentions((msg) => {
        setRadarIntentions(prev => rizoma.aggregateSemanticState([msg, ...prev]));
      }).then(fn => unsubFn = fn);
    }
    return () => { if (unsubFn && typeof unsubFn === 'function') unsubFn(); };
  }, [wakuStatusMsg]);

  // --- ATOMIC RENDERER (VERSIÓN ESCALADA) ---
  const AtomicRenderer = ({ type, data, text, objectId }: { type: string, data: any, text: string, objectId?: string }) => {
    const schema = latentSchemas.find(s => s.id === type);
    if (!schema) return <p className="text-base font-bold uppercase">{text}</p>;

    const composition: AddonComposition = data.composition || schema.composition || {
      layout: 'LIST',
      components: [
        { atom: 'HEADER', props: { title: schema.name } },
        { atom: 'TEXT', props: { content: text } },
        { atom: 'BUTTON', props: { label: 'CONTACTAR', action: 'INTERACT' } }
      ]
    };

    const Tooltip = ({ text, children }: { text: string, children: React.ReactNode }) => (
      <div className="group/tooltip relative inline-block w-full">
        {children}
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 bg-black/90 border border-white/10 rounded-lg text-[10px] font-mono text-primary font-black uppercase tracking-widest opacity-0 group-hover/tooltip:opacity-100 transition-opacity pointer-events-none z-[100] whitespace-nowrap shadow-2xl">
          {text}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-t-black/90"></div>
        </div>
      </div>
    );

    return (
      <div className={`space-y-4 animate-fade-in mt-4 ${composition.layout === 'GRID' ? 'grid grid-cols-2 gap-4 space-y-0' : ''}`}>
        {composition.components.map((comp, i) => {
          const value = comp.binding ? data[comp.binding] : null;
          switch (comp.atom) {
            case 'HEADER':
              return <div key={i} className="border-b border-white/20 pb-2 mb-4 col-span-full"><h3 className="text-xl font-black text-white tracking-tight uppercase">{String(comp.props.title)}</h3></div>;
            case 'TEXT':
              return <p key={i} className="text-base text-on-surface leading-snug uppercase font-medium col-span-full">{String(comp.props.content || value || '')}</p>;
            case 'BADGE':
              return (
                <Tooltip key={i} text={`DATO: ${String(comp.props.label).toUpperCase()}`}>
                  <div className="inline-block bg-white/5 border border-white/10 px-3 py-1 rounded text-[10px] font-mono text-outline mr-2 mb-2 uppercase font-black tracking-widest w-full text-center hover:bg-white/10 transition-colors">
                    <span className="opacity-40">{String(comp.props.label)}:</span> {String(value || '---')}
                  </div>
                </Tooltip>
              );
            case 'PROGRESS':
              const p = Math.floor((Number(data[comp.props?.current] || 0) / Number(comp.props?.max || 1)) * 100);
              return (
                <Tooltip key={i} text={`PROGRESO: ${p}% COMPLETADO`}>
                  <div className="my-6 col-span-full bg-black/40 p-5 rounded-2xl border border-white/5 relative overflow-hidden group/progress">
                    <div className="flex justify-between text-[10px] font-mono text-primary mb-3 font-black uppercase tracking-widest relative z-10">
                      <span>SYNC_STATUS</span>
                      <span className="bg-primary/20 px-2 py-0.5 rounded-md animate-pulse">{p}%</span>
                    </div>
                    <div className="h-3 w-full bg-white/5 rounded-full overflow-hidden relative border border-white/5">
                      <div 
                        className="h-full bg-gradient-to-r from-primary/50 to-primary shadow-[0_0_15px_rgba(248,172,255,0.6)] transition-all duration-1000 ease-out relative"
                        style={{ width: `${p}%` }}
                      >
                        <div className="absolute inset-0 bg-[linear-gradient(45deg,rgba(255,255,255,0.2)_25%,transparent_25%,transparent_50%,rgba(255,255,255,0.2)_50%,rgba(255,255,255,0.2)_75%,transparent_75%,transparent)] bg-[length:20px_20px] animate-[slide_2s_linear_infinite]"></div>
                      </div>
                    </div>
                    <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 blur-[40px] rounded-full -mr-16 -mt-16 pointer-events-none"></div>
                  </div>
                </Tooltip>
              );
            case 'GAUGE':
              const g = Math.min(Math.max(Number(value || 0), 0), 10);
              return (
                <Tooltip key={i} text={`NIVEL: ${g}/10`}>
                  <div className="bg-black/60 p-6 rounded-2xl border border-white/5 flex flex-col items-center my-4 col-span-full group/gauge hover:border-secondary/30 transition-all">
                    <span className="font-mono text-[9px] text-secondary mb-4 font-black tracking-[0.3em] uppercase">{String(comp.props?.label || 'LEVEL')}</span>
                    <div className="flex gap-2">
                      {[...Array(10)].map((_, j) => (
                        <div key={j} className={`w-3.5 h-8 border transition-all duration-500 ${j < g ? 'bg-secondary border-secondary shadow-[0_0_15px_#ffb95a]' : 'bg-transparent border-white/10 opacity-20'}`}></div>
                      ))}
                    </div>
                  </div>
                </Tooltip>
              );
            case 'MEMBER_LIST':
              const members = value || data[comp.props?.current] || [];
              return (
                <Tooltip key={i} text={`${members.length} ACTORES PARTICIPANDO`}>
                  <div className="flex -space-x-3 overflow-hidden p-2 col-span-full justify-center my-2">
                    {members.map((m: string, j: number) => (
                      <div key={j} className="inline-block h-12 w-12 rounded-full border-2 border-[#131314] bg-primary/20 flex items-center justify-center text-[11px] font-black text-primary shadow-xl hover:-translate-y-1 transition-transform cursor-pointer" title={m}>
                        {m.slice(0, 2).toUpperCase()}
                      </div>
                    ))}
                    <div className="h-12 w-12 rounded-full border-2 border-dashed border-white/10 flex items-center justify-center text-[12px] text-outline font-black hover:border-primary transition-colors cursor-pointer">+</div>
                  </div>
                </Tooltip>
              );
            case 'QR_CODE':
              return (
                <Tooltip key={i} text="ESCANEAR PARA VINCULAR ACTOR">
                  <div className="bg-white p-4 rounded-3xl w-36 h-36 mx-auto my-6 flex items-center justify-center shadow-[0_0_40px_rgba(255,255,255,0.15)] col-span-full hover:scale-105 transition-transform cursor-none">
                    <div className="w-28 h-28 border-4 border-black flex flex-wrap">
                      {[...Array(16)].map((_, j) => <div key={j} className={`w-7 h-7 ${Math.random() > 0.6 ? 'bg-black' : 'bg-white'}`}></div>)}
                    </div>
                  </div>
                </Tooltip>
              );
            case 'MAP':
              return (
                <Tooltip key={i} text="RADAR TÁCTICO: LOCALIZANDO NODOS">
                  <div className="relative w-full aspect-video bg-black/40 rounded-3xl border border-white/5 overflow-hidden my-4 col-span-full group/map hover:border-primary/20 transition-all">
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="w-64 h-64 border border-primary/20 rounded-full group-hover/map:scale-110 transition-transform duration-2000"></div>
                      <div className="w-48 h-48 border border-primary/15 rounded-full absolute group-hover/map:scale-125 transition-transform duration-1500"></div>
                      <div className="w-32 h-32 border border-primary/10 rounded-full absolute group-hover/map:scale-150 transition-transform duration-1000"></div>
                      <div className="w-px h-full bg-primary/10 absolute animate-pulse"></div>
                      <div className="h-px w-full bg-primary/10 absolute animate-pulse"></div>
                      <div className="absolute w-2.5 h-2.5 bg-primary rounded-full animate-ping shadow-[0_0_15px_#f8acff]" style={{ top: '30%', left: '60%' }}></div>
                      <div className="absolute w-2 h-2 bg-secondary rounded-full shadow-[0_0_10px_#ffb95a]" style={{ top: '70%', left: '40%' }}></div>
                    </div>
                    <div className="absolute top-3 left-5 font-mono text-[9px] text-primary/60 uppercase font-black tracking-widest">SIGNAL_SEARCH_ACTIVE</div>
                    <div className="absolute bottom-3 right-5 font-mono text-[9px] text-primary/60 uppercase tracking-[0.2em] font-black">X: 124.5 | Y: 88.2</div>
                  </div>
                </Tooltip>
              );
            case 'BUTTON':
              return (
                <Tooltip key={i} text={`EJECUTAR: ${String(comp.props?.label || 'ACCION').toUpperCase()}`}>
                  <button onClick={() => handleAtomicAction(comp.props?.action, type, objectId, data)} className="btn-primary w-full py-5 text-sm font-black mt-4 rounded-2xl shadow-xl hover:shadow-primary/20 hover:scale-[1.02] active:scale-[0.98] transition-all col-span-full uppercase">
                    {String(comp.props?.label || 'CONTINUAR')}
                  </button>
                </Tooltip>
              );
            default: return null;
          }
        })}
      </div>
    );
  };

  const handleAtomicAction = async (action: string, _type: string, objectId?: string, currentData?: any) => {
    if (action === 'INTERACT') return addNotification("CONEXIÓN_ACTIVA");
    if (['JOIN_EVENT', 'CONTRIBUTE', 'SIMULATE_SCAN'].includes(action)) {
      if (!objectId) return;
      const patchData: any = {};
      if (action === 'SIMULATE_SCAN') {
        patchData.scans = (currentData?.scans || 0) + 1;
        patchData.points = [...(currentData?.points || []), { x: Math.random() * 80 + 10, y: Math.random() * 80 + 10 }];
      }
      if (action === 'JOIN_EVENT') {
        patchData.participantes = (currentData?.participantes || 0) + 1;
        patchData.members = [...(currentData?.members || []), profile?.alias || 'ACTOR_ANON'];
      }
      await rizoma.announceIntention(`ACTUALIZACIÓN`, 'INTENTION_PATCH', { action: 'PATCH', objectId, data: patchData });
      addNotification("SEÑAL_TRANSMITIDA");
    }
  };

  const [showRawMap, setShowRawMap] = useState<Record<string, boolean>>({});

  const toggleRaw = (id: string) => {
    setShowRawMap(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const renderAddonContent = (intent: any) => {
    const id = intent.objectId || `${intent.sender}-${intent.timestamp}`;
    const showRaw = showRawMap[id];

    if (showRaw) {
      return (
        <div className="bg-black/60 p-6 rounded-2xl border border-primary/20 font-mono text-[10px] text-primary/80 overflow-x-auto">
          <div className="flex justify-between mb-4 border-b border-primary/10 pb-2">
            <span>[ RAW_DATA_VIEW ]</span>
            <button onClick={() => toggleRaw(id)} className="text-white hover:text-primary">[ CERRAR ]</button>
          </div>
          <pre>{JSON.stringify(intent, null, 2)}</pre>
        </div>
      );
    }

    if (intent.type?.startsWith('rizoma/')) return <AtomicRenderer type={intent.type} data={intent.data} text={intent.text} objectId={intent.objectId} />;
    if (intent.type === 'ADDON_IDEA') {
      return (
        <div className="border-l-4 border-primary pl-6 py-4 bg-primary/5 rounded-r-xl">
          <p className="text-xl font-black text-white mb-6 tracking-tight leading-tight">{intent.text.toUpperCase()}</p>
          <div className="flex gap-4">
            <button onClick={() => handleAtomicAction('VOTE_IDEA', 'ADDON_IDEA', intent.objectId, intent.data)} className="px-6 py-3 border border-primary/30 text-primary text-[10px] font-mono font-black rounded-lg hover:bg-primary/10 transition-all uppercase tracking-widest">[ APOYAR ]</button>
            <button onClick={() => { setActiveModal({ title: "Materializar", fields: [{ name: 'yes', label: 'Escribe "SI" para crear', type: 'text' }], onSubmit: async (data: any) => { if(data.yes?.toUpperCase() === 'SI') addNotification("CREANDO..."); }}); }} className="px-6 py-3 bg-primary text-on-primary text-[10px] font-mono font-black rounded-lg shadow-lg uppercase tracking-widest">MATERIALIZAR</button>
          </div>
        </div>
      );
    }
    return <p className="text-lg leading-snug text-on-surface uppercase font-bold tracking-tight">{intent.text}</p>;
  };

  const runCommunitySimulation = async () => {
    addNotification("SOCIAL_ENGINE: INICIANDO MISIÓN...");
    const qId = `q-${Date.now()}`;
    await rizoma.announceIntention("PROYECTO_HUERTA_URBANA_ZONA_SUR", 'rizoma/mission/v1', { 
      members: ["ACTOR_ALICE", "ACTOR_BOB", "ACTOR_CHARLIE"], 
      work: 3, 
      objectId: qId,
      composition: { layout: 'GRID', components: [
        { atom: 'HEADER', props: { title: 'MISIÓN_ACTIVA' } },
        { atom: 'TEXT', props: { content: 'COORDINANDO SIEMBRA COLECTIVA EN PARQUE CENTRAL' } },
        { atom: 'MAP', props: { label: 'UBICACIÓN_EVENTO' } },
        { atom: 'PROGRESS', props: { current: 'work', max: 10 } },
        { atom: 'MEMBER_LIST', props: { label: 'RESONADORES_ACTIVOS' }, binding: 'members' },
        { atom: 'BUTTON', props: { label: 'COLABORAR', action: 'JOIN_EVENT' } }
      ]}
    });
  };

  if (view === 'importar') return (
    <ImportarView
      onImported={(p) => { setProfile(p); setView(sinapsisId ? 'sinapsis' : 'radar'); window.location.hash = ''; }}
      onCancelar={() => { setView('login'); window.location.hash = ''; }}
    />
  );

  if (view === 'login') return (
    <div className="bg-[#131314] min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md text-center">
        <h1 className="text-6xl font-black tracking-tighter text-white leading-none mb-4">RIZOMA</h1>
        <p className="font-mono text-primary text-sm tracking-[0.4em] mb-12 opacity-40">P2P_SOVEREIGN_ENGINE</p>
        <form onSubmit={async (e) => { e.preventDefault(); if(!email) return; const p = await rizoma.login(email); setProfile(p); setView(sinapsisId ? 'sinapsis' : 'radar'); }} className="space-y-6">
          <input className="chat-input text-center h-16 text-2xl font-black border-2 border-white/5 focus:border-primary !bg-[#0a0a0a] !text-white rounded-2xl" placeholder="CORREO" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
          <button className="btn-primary w-full h-16 text-xl font-black rounded-2xl" type="submit">ACCEDER</button>
        </form>
      </div>
    </div>
  );

  return (
    <div className="app-container">
      <div className="noise-overlay"></div>
      
      <header className="fixed top-0 left-0 right-0 bg-[#131314]/98 backdrop-blur-3xl z-50 border-b-2 border-white/5 h-20">
        <div className="max-w-[900px] mx-auto h-full flex justify-between items-center px-6">
          <div className="flex items-center gap-8">
            <span className="text-2xl font-black text-white tracking-tighter cursor-pointer" onClick={() => setView('radar')}>RIZOMA</span>
            <nav className="hidden md:flex gap-6">
              {['radar', 'inbox', 'addons', 'inventory'].map(v => (
                <button key={v} onClick={() => setView(v as any)} className={`font-mono text-xs tracking-widest font-black transition-all ${view === v ? 'text-primary' : 'text-outline hover:text-white'}`}>
                  {v.toUpperCase()}
                </button>
              ))}
            </nav>
          </div>
          <div onClick={() => setView('settings')} className="flex items-center gap-4 cursor-pointer group bg-white/5 p-2 rounded-xl border border-white/5 hover:border-primary transition-all">
             <div className="text-right">
               <div className="font-mono text-sm text-primary font-black uppercase leading-none">{profile?.alias}</div>
               <div className="font-mono text-[9px] text-outline opacity-40">#{profile?.address.slice(-6).toUpperCase()}</div>
             </div>
             <div className="w-10 h-10 rounded-lg bg-primary border-2 border-black flex items-center justify-center text-black text-xl font-black"><MaterialIcon name="person" fill={1} /></div>
          </div>
        </div>
      </header>

      <main className="flex-grow pt-28 pb-32 px-6 max-w-[900px] mx-auto w-full">
        {view === 'sinapsis' && sinapsisId && profile && (
          <SinapsisView
            sinapsisId={sinapsisId}
            profile={profile}
            onNotify={addNotification}
            onIrAlTunel={() => setView('inbox')}
          />
        )}
        {view === 'radar' && (
          <div className="animate-fade-in space-y-12">
            <div className="flex justify-between items-end border-b-2 border-white/5 pb-6">
               <h2 className="text-4xl font-black text-white tracking-tighter">RADAR</h2>
               <div className="flex gap-4">
                 <button onClick={runCommunitySimulation} className="font-mono text-xs bg-primary/10 text-primary px-5 py-2 rounded-xl font-black border border-primary/20 uppercase">[ SIMULAR ]</button>
                 <button onClick={refreshRadar} className="font-mono text-xs text-outline hover:text-white font-black uppercase">[ SINC ]</button>
               </div>
            </div>
            <div className="grid grid-cols-1 gap-12">
              {radarIntentions.map((intent, i) => {
                const isAddon = intent.type?.startsWith('rizoma/');
                return (
                  <article key={i} className={`liquid-card group/card transition-all p-8 shadow-2xl rounded-[2.5rem] relative overflow-hidden ${isAddon ? 'border-2 border-primary/50 bg-white/[0.04] ring-1 ring-primary/20 ring-offset-4 ring-offset-[#131314]' : 'border border-white/5 bg-white/[0.01]'}`}>
                    {isAddon && (
                      <div className="absolute top-0 right-0 p-4">
                        <div className="bg-primary/10 border border-primary/20 px-3 py-1 rounded-full flex items-center gap-2">
                           <div className="w-1.5 h-1.5 bg-primary rounded-full animate-ping"></div>
                           <span className="font-mono text-[9px] text-primary font-black uppercase tracking-tighter">PROTO_ADDON_v1</span>
                        </div>
                      </div>
                    )}
                    
                    <div className="flex justify-between items-center mb-8 border-b border-white/5 pb-6">
                      <div className="flex items-center gap-4 cursor-pointer group" onClick={() => setViewingActor({ profile: { address: intent.sender, alias: intent.alias, email: '', publicKey: intent.publicKey }, stats: { masa: 100, resonancias: 5, antiguedad: '2M' } })}>
                        <div className={`w-4 h-4 rounded-full ${isAddon ? 'bg-primary shadow-[0_0_15px_#f8acff]' : 'bg-outline opacity-40'}`}></div>
                        <div className="flex flex-col">
                          <span className="font-mono text-xl font-black text-white uppercase tracking-tighter group-hover:text-primary transition-colors">{intent.alias}</span>
                          <span className="font-mono text-[9px] text-outline opacity-40 font-bold">NODE_ID: {intent.sender.slice(-12).toUpperCase()}</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <span className="font-mono text-xs text-outline font-black opacity-30 block mb-1">{formatTime(intent.timestamp)}</span>
                        {isAddon && <span className="font-mono text-[10px] text-secondary font-black uppercase tracking-widest bg-secondary/10 px-2 py-0.5 rounded">INTENCIÓN_LÍQUIDA</span>}
                      </div>
                    </div>

                    <div className="relative z-10">
                      {renderAddonContent(intent)}
                    </div>

                    {isAddon && (
                      <div className="mt-8 flex gap-2">
                        <div className="bg-white/5 h-1 flex-grow rounded-full overflow-hidden">
                          <div className="bg-primary h-full w-1/3 animate-pulse"></div>
                        </div>
                        <div className="bg-white/5 h-1 w-12 rounded-full overflow-hidden">
                           <div className="bg-secondary h-full w-full opacity-50"></div>
                        </div>
                      </div>
                    )}

                    <div className="mt-10 pt-8 border-t border-white/5 flex justify-between items-center">
                      <div className="flex flex-col">
                         <span className="font-mono text-[10px] text-outline/20 tracking-widest uppercase font-black mb-1">Firma del Actor</span>
                         <span className="font-mono text-[9px] text-outline/40 tracking-widest truncate max-w-[200px] uppercase font-black">{intent.sender}</span>
                      </div>
                      <div className="flex gap-3">
                         {isAddon && (
                           <button onClick={() => toggleRaw(intent.objectId || `${intent.sender}-${intent.timestamp}`)} className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-outline hover:text-secondary hover:border-secondary transition-all">
                             <MaterialIcon name="code" className="text-xl" />
                           </button>
                         )}
                         <button onClick={() => addNotification("COPIANDO_SIG_PROTO...")} className="w-10 h-10 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-outline hover:text-primary hover:border-primary transition-all">
                           <MaterialIcon name="content_copy" className="text-xl" />
                         </button>
                         <button onClick={() => setView('inbox')} className={`py-4 px-10 text-xs font-black rounded-2xl transition-all ${isAddon ? 'bg-primary text-black hover:shadow-[0_0_20px_rgba(248,172,255,0.4)]' : 'bg-white/5 text-white hover:bg-white/10 border border-white/10'}`}>
                           CONECTAR
                         </button>
                      </div>
                    </div>

                    {/* Efecto de fondo sutil para addons */}
                    {isAddon && (
                      <div className="absolute -bottom-20 -right-20 w-64 h-64 bg-primary/5 rounded-full blur-[100px] pointer-events-none group-hover/card:bg-primary/10 transition-colors"></div>
                    )}
                  </article>
                );
              })}
            </div>
          </div>
        )}

        {view === 'inbox' && (
           <div className="animate-fade-in space-y-12">
             <div className="flex justify-between items-end border-b-2 border-white/5 pb-6">
               <h2 className="text-4xl font-black text-white tracking-tighter">INBOX</h2>
               <button onClick={() => setActiveModal({ title: "Nueva Conexión", fields: [{ name: 'address', label: 'ID del Actor', type: 'text' }], onSubmit: () => {} })} className="btn-primary px-6 py-2 text-xs font-black rounded-lg">+ NUEVA</button>
             </div>
             <div className="space-y-6">
               {conversations.map((c, i) => (
                 <article key={i} onClick={() => setView('chat')} className="liquid-card p-6 flex justify-between items-center cursor-pointer border border-white/10 rounded-2xl hover:bg-white/[0.03]">
                    <div className="flex items-center gap-6">
                      <div className="w-12 h-12 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-primary text-2xl font-black"><MaterialIcon name="person" fill={1} /></div>
                      <div>
                        <h3 className="text-xl font-black text-white tracking-tight">{c.topic.toUpperCase()}</h3>
                        <p className="font-mono text-[10px] text-outline uppercase font-black tracking-widest opacity-30">{c.lastMessage || 'SIN MENSAJES'}</p>
                      </div>
                    </div>
                    <MaterialIcon name="chevron_right" className="text-3xl text-primary opacity-10" />
                 </article>
               ))}
             </div>
           </div>
        )}

        {view === 'addons' && (
          <div className="animate-fade-in space-y-12">
            <div className="flex justify-between items-end border-b-2 border-white/5 pb-6">
               <h2 className="text-4xl font-black text-white tracking-tighter">ADDONS</h2>
               <button 
                onClick={() => setActiveModal({ 
                  title: "Instalar Protocolo", 
                  fields: [{ name: 'id', label: 'ID del Protocolo (rizoma/name/v1)', type: 'text' }], 
                  onSubmit: (data: any) => addNotification(`BUSCANDO PROTOCOLO: ${data.id?.toUpperCase()}`)
                })} 
                className="font-mono text-xs text-primary font-black uppercase"
               >
                 [ + INSTALAR ]
               </button>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {latentSchemas.map((schema, i) => (
                <article key={i} className="liquid-card p-8 border border-white/10 rounded-[2rem] bg-white/[0.02] hover:bg-white/[0.04] transition-all group/addon relative overflow-hidden">
                  <div className="flex justify-between items-start mb-6">
                    <div className="w-14 h-14 bg-primary/10 border border-primary/20 rounded-2xl flex items-center justify-center text-primary" dangerouslySetInnerHTML={{ __html: schema.icon }}></div>
                    <div className="bg-primary/5 border border-primary/10 px-3 py-1 rounded-full">
                      <span className="font-mono text-[8px] text-primary font-black tracking-widest uppercase">v1.0.0</span>
                    </div>
                  </div>
                  
                  <h3 className="text-2xl font-black text-white mb-2 tracking-tight group-hover/addon:text-primary transition-colors">{schema.name.toUpperCase()}</h3>
                  <p className="font-mono text-[10px] text-outline/60 uppercase mb-6 leading-relaxed">{schema.description}</p>
                  
                  <div className="space-y-3 mb-8">
                    {schema.fields.map((f: any, j: number) => (
                      <div key={j} className="flex justify-between border-b border-white/5 pb-2">
                        <span className="font-mono text-[9px] text-outline uppercase font-bold">{f.label}</span>
                        <span className="font-mono text-[9px] text-white/40 uppercase">DATA_TYPE: {f.type || 'TEXT'}</span>
                      </div>
                    ))}
                  </div>

                  <div className="flex gap-4">
                    <button onClick={() => addNotification(`CONFIGURANDO: ${schema.name.toUpperCase()}`)} className="flex-grow py-3 bg-white/5 border border-white/10 rounded-xl font-mono text-[10px] font-black text-white hover:bg-white/10 transition-all uppercase tracking-widest">CONFIGURAR</button>
                    <button 
                      onClick={async () => {
                        const updated = latentSchemas.filter((_, idx) => idx !== i);
                        setLatentSchemas(updated);
                        localStorage.setItem('rizoma_latent_schemas', JSON.stringify(updated));
                        addNotification("COMPONENTE_ELIMINADO");
                      }} 
                      className="w-12 h-12 flex items-center justify-center bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl hover:bg-red-500/20 transition-all"
                    >
                      <MaterialIcon name="delete" className="text-xl" />
                    </button>
                  </div>

                  {/* Decoración de fondo sutil */}
                  <div className="absolute -bottom-10 -right-10 w-32 h-32 bg-primary/5 rounded-full blur-3xl group-hover/addon:bg-primary/10 transition-all"></div>
                </article>
              ))}
              
              <div 
                onClick={() => setActiveModal({
                  title: "Diseñar Nueva Estructura",
                  fields: [
                    { name: 'name', label: 'Nombre del Addon', type: 'text', placeholder: 'Ej: Sistema de Intercambio de Saberes' },
                    { name: 'id', label: 'Identificador del Protocolo', type: 'text', placeholder: 'rizoma/knowledge-exchange/v1' },
                    { name: 'blueprint', label: 'Blueprint Estructural (Idea de Diseño)', type: 'textarea', placeholder: 'Describe la lógica, la composición visual deseada y el flujo de interacción...' },
                    { name: 'attributes', label: 'Atributos de Datos (Campos)', type: 'textarea', placeholder: 'Ej: materia: string, mentor: address, horas: number...' }
                  ],
                  onSubmit: async (data: any) => {
                    if (!data.name || !data.id) return;
                    const newSchema = {
                      id: data.id,
                      name: data.name,
                      description: data.blueprint,
                      icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="12" y1="8" x2="12" y2="16"></line><line x1="8" y1="12" x2="16" y2="12"></line></svg>',
                      fields: (data.attributes || '').split(',').map((f: string) => {
                        const [n, t] = f.trim().split(':');
                        return { name: n || 'field', label: n?.toUpperCase() || 'DATO', type: t || 'text' };
                      }),
                      composition: { 
                        layout: 'LIST', 
                        components: [
                          { atom: 'HEADER', props: { title: data.name.toUpperCase() } },
                          { atom: 'TEXT', props: { content: 'ESQUEMA_EN_ETAPA_DE_DISEÑO' } },
                          { atom: 'BADGE', props: { label: 'BLUEPRINT' }, binding: 'description' }
                        ] 
                      }
                    };
                    await rizoma.proposeSchema(newSchema);
                    setLatentSchemas(prev => [...prev, newSchema]);
                    addNotification("DISEÑO_ENVIADO_A_LA_RED");
                  }
                })}
                className="border-2 border-dashed border-white/5 rounded-[2rem] p-8 flex flex-col items-center justify-center gap-4 group/new cursor-pointer hover:border-primary/20 transition-all min-h-[250px]"
              >
                <div className="w-12 h-12 rounded-full bg-white/5 flex items-center justify-center text-outline group-hover/new:text-primary transition-all">
                  <MaterialIcon name="add" className="text-3xl" />
                </div>
                <span className="font-mono text-[10px] text-outline font-black uppercase tracking-widest group-hover:text-primary transition-all">PROPONER_NUEVO_ESQUEMA</span>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* NOTIFICACIONES CENTRADAS (MÁS PEQUEÑAS) */}
      <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-[9999] flex flex-col gap-4 w-full max-w-[500px] px-6">
        {notifications.map(n => (
          <div key={n.id} className="bg-white text-black font-mono font-black text-xs px-8 py-4 shadow-xl border-4 border-black animate-fade-in uppercase tracking-tighter text-center leading-tight">
            {`> ${n.text}`}
          </div>
        ))}
      </div>

      <DynamicModal modal={activeModal} onClose={() => setActiveModal(null)} />
    </div>
  );
}
