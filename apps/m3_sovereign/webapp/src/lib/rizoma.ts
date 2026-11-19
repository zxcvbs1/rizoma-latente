import { ethers } from 'ethers';
import { createLightNode, createDecoder, createEncoder, waitForRemotePeer, Protocols } from '@waku/sdk';
import type { LightNode } from '@waku/sdk';

// Tópicos de Waku para la Capa Latente
const CONTENT_TOPIC = "/rizoma/v1/intentions/proto";

// Clave pública del protocolo para señales generales; no ofrece confidencialidad.
const NETWORK_KEY = ethers.getBytes(ethers.id("rizoma-ocean-2026-key"));

export interface Message {
  id: string;
  sender: string;
  text: string;
  timestamp: number;
  isMe: boolean;
  isEncrypted?: boolean;
  type?: string;      
  data?: any;         
  objectId?: string;  
  action?: string;    
}

export interface Intention {
  sender: string;
  publicKey?: string;
  text: string;
  timestamp: number;
  alias?: string;
  type?: string;      
  data?: any;         
  objectId?: string;
}

export interface AddonComposition {
  layout: 'LIST' | 'GRID' | 'FLOW' | 'DETAIL';
  components: Array<{
    atom: 'HEADER' | 'TEXT' | 'BADGE' | 'PROGRESS' | 'BUTTON' | 'MEMBER_LIST' | 'QR_CODE' | 'MAP' | 'GAUGE';
    props: any;
    binding?: string; 
  }>;
}

export interface Conversation {
  peerAddress: string;
  peerPublicKey?: string;
  lastMessage: string;
  topic: string;
  unreadCount: number;
  folderId?: string;
  isGroup?: boolean;
  groupKey?: Uint8Array; 
  groupTopic?: string;   
}

export interface Folder {
  id: string;
  name: string;
}

export interface UserProfile {
  address: string;
  email: string;
  alias?: string;
  publicKey?: string;
}

export interface Contact extends UserProfile {
  notes?: string;
  isFavorite?: boolean;
}

export interface RizomaStats {
  masa: number;
  resonancias: number;
  antiguedad: string;
}

class RizomaSovereign {
  private wakuNode: LightNode | null = null;
  private wallet: ethers.Wallet | null = null;
  private profile: UserProfile | null = null;
  public wakuStatus: 'offline' | 'connecting' | 'online' = 'offline';
  public onStatusChange: (status: string) => void = () => {};

  constructor() {}

  async initWaku() {
    if (this.wakuNode) return;
    this.wakuStatus = 'connecting';
    this.onStatusChange("BUSCANDO_NODOS_P2P...");
    try {
      this.wakuNode = await createLightNode({ defaultBootstrap: true });
      await this.wakuNode.start();
      
      // Intentar conectar con un timeout para no bloquear la app
      const peerPromise = waitForRemotePeer(this.wakuNode, [Protocols.Filter, Protocols.LightPush, Protocols.Store]);
      const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error("TIMEOUT")), 15000));
      
      await Promise.race([peerPromise, timeoutPromise]);
      
      this.wakuStatus = 'online';
      this.onStatusChange("TÚNEL P2P ONLINE");
    } catch (e) {
      console.warn("Waku failed to connect to remote peers. Operating in Local/Isolated mode.", e);
      this.wakuStatus = 'offline';
      this.onStatusChange("MODO_LOCAL (P2P_OFFLINE)");
    }
  }

  async login(email: string): Promise<UserProfile> {
    const salt = "rizoma-sovereign-2026";
    const privateKey = ethers.id(email + salt);
    this.wallet = new ethers.Wallet(privateKey);
    const shortAddr = this.wallet.address.slice(-4).toUpperCase();
    this.profile = {
      address: this.wallet.address,
      email: "", 
      alias: `Actor-${shortAddr}`,
      publicKey: this.wallet.signingKey.publicKey
    };
    localStorage.setItem('rizoma_session', JSON.stringify({ email }));
    this.initWaku();
    return this.profile;
  }

  async announceIntention(text: string, type: string = 'GENERAL', data: any = {}) {
    if (!this.wakuNode || this.wakuStatus !== 'online') throw new Error("P2P_OFFLINE");
    const encoder = createEncoder({ contentTopic: CONTENT_TOPIC, pubsubTopicShardInfo: { clusterId: 1, shard: 1 } });
    const payload = JSON.stringify({ sender: this.wallet?.address, text, timestamp: Date.now(), alias: this.profile?.alias, publicKey: this.profile?.publicKey, type, data });
    await this.wakuNode.lightPush.send(encoder, { payload: await this.encryptWithKey(payload, NETWORK_KEY) });
  }

  async getConversations(): Promise<Conversation[]> {
    const contacts = this.getContacts();
    const contactConvs = contacts.map(c => ({ peerAddress: c.address, peerPublicKey: c.publicKey, lastMessage: "SESIÓN_SEGURA", topic: c.alias || "CHAT_DIRECTO", unreadCount: 0 }));
    const groups = JSON.parse(localStorage.getItem('rizoma_groups') || '[]');
    const groupConvs = groups.map((g: any) => ({ ...g, groupKey: g.groupKey ? new Uint8Array(Object.values(g.groupKey)) : undefined }));
    return [...contactConvs, ...groupConvs];
  }

  async getMessages(peerAddress: string, peerPublicKey?: string, group?: Conversation): Promise<Message[]> {
    if (!this.wakuNode || this.wakuStatus !== 'online') return [];
    let topic = group?.isGroup ? group.groupTopic! : await this.getResonanceTopic(peerAddress);
    if (!group?.isGroup && !peerPublicKey) return [];
    const decoder = createDecoder(topic, { clusterId: 1, shard: 1 });
    const messages: Message[] = [];
    try {
      const query = this.wakuNode.store.queryGenerator([decoder], { paginationForward: true, paginationLimit: 100 });
      for await (const batch of query) {
        for (const msgOrPromise of batch) {
          const msg = await msgOrPromise;
          if (msg && msg.payload) {
            try {
              let decryptedText;
              if (group?.isGroup && group.groupKey) decryptedText = await this.decryptWithKey(msg.payload, group.groupKey);
              else if (peerPublicKey) decryptedText = await this.decryptE2EE(msg.payload, peerPublicKey);
              else continue;
              const data = JSON.parse(decryptedText);
              messages.push({ id: Math.random().toString(36).substr(2, 9), sender: data.sender, text: data.text, timestamp: data.timestamp, isMe: data.sender === this.wallet?.address, isEncrypted: true, type: data.type || 'TEXT', data: data.data || {} });
            } catch (e) {}
          }
        }
      }
    } catch (e) {}
    return messages;
  }

  async sendMessage(peerAddress: string, text: string, peerPublicKey?: string, group?: Conversation, type: string = 'TEXT', data: any = {}): Promise<Message> {
    if (!this.wakuNode || this.wakuStatus !== 'online') throw new Error("P2P_OFFLINE");
    let topic; let encryptedPayload;
    const payloadObj = { sender: this.wallet?.address, text, timestamp: Date.now(), type, data };
    if (group?.isGroup && group.groupKey) {
      topic = group.groupTopic!;
      encryptedPayload = await this.encryptWithKey(JSON.stringify(payloadObj), group.groupKey);
    } else {
      if (!peerPublicKey) throw new Error("PUBKEY_REQUIRED");
      topic = await this.getResonanceTopic(peerAddress);
      encryptedPayload = await this.encryptE2EE(JSON.stringify(payloadObj), peerPublicKey);
    }
    const encoder = createEncoder({ contentTopic: topic, pubsubTopicShardInfo: { clusterId: 1, shard: 1 } });
    await this.wakuNode.lightPush.send(encoder, { payload: encryptedPayload });
    return { id: Math.random().toString(36).substr(2, 9), sender: this.wallet?.address || "me", text, timestamp: Date.now(), isMe: true, isEncrypted: true, type, data };
  }

  async subscribeToResonances(peerAddress: string, peerPublicKey: string, callback: (msg: Message) => void) {
    if (!this.wakuNode || this.wakuStatus !== 'online') return;
    const topic = await this.getResonanceTopic(peerAddress);
    const decoder = createDecoder(topic, { clusterId: 1, shard: 1 });
    return await this.wakuNode.filter.subscribe([decoder], async (msg) => {
      if (msg?.payload) {
        try {
          const decryptedText = await this.decryptE2EE(msg.payload, peerPublicKey);
          const data = JSON.parse(decryptedText);
          callback({ id: Math.random().toString(36).substr(2, 9), sender: data.sender, text: data.text, timestamp: data.timestamp, isMe: data.sender === this.wallet?.address, isEncrypted: true, type: data.type || 'TEXT', data: data.data || {} });
        } catch (e) {}
      }
    });
  }

  async subscribeToIntentions(callback: (intention: any) => void) {
    if (!this.wakuNode || this.wakuStatus !== 'online') return;
    const decoder = createDecoder(CONTENT_TOPIC, { clusterId: 1, shard: 1 });
    return await this.wakuNode.filter.subscribe([decoder], async (msg) => {
      if (msg?.payload) {
        try {
          const decoded = JSON.parse(await this.decryptWithKey(msg.payload, NETWORK_KEY));
          callback(decoded);
        } catch (e) {}
      }
    });
  }

  async fetchIntentions(): Promise<any[]> {
    if (!this.wakuNode || this.wakuStatus !== 'online') {
      // Retornar datos mockeados si no hay conexión para que el usuario pueda ver los addons
      return this.getMockIntentions();
    }
    const decoder = createDecoder(CONTENT_TOPIC, { clusterId: 1, shard: 1 });
    const rawItems: any[] = [];
    try {
      const query = this.wakuNode.store.queryGenerator([decoder], { paginationForward: false, paginationLimit: 100 });
      for await (const messages of query) {
        for (const msgOrPromise of messages) {
          const msg = await msgOrPromise;
          if (msg?.payload) {
            try { rawItems.push(JSON.parse(await this.decryptWithKey(msg.payload, NETWORK_KEY))); } catch (e) {}
          }
        }
      }
      
      if (rawItems.length === 0) return this.getMockIntentions();

      const closedMap = new Set();
      const rawIntentions: any[] = [];
      rawItems.forEach(item => { if (item.type === 'INTENTION_PATCH' && item.action === 'CLOSE') closedMap.add(`${item.sender}-${item.targetTimestamp}`); });
      rawItems.forEach(item => {
        if (!item.type || item.type !== 'INTENTION_PATCH') {
          if (!closedMap.has(`${item.sender}-${item.timestamp}`)) rawIntentions.push(item);
        } else if (item.action !== 'CLOSE') rawIntentions.push(item);
      });
      return this.aggregateSemanticState(rawIntentions);
    } catch (e) { 
      return this.getMockIntentions(); 
    }
  }

  private getMockIntentions(): any[] {
    return [
      {
        sender: "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",
        alias: "Protocol_Zero",
        text: "BIENVENIDO AL SISTEMA RIZOMA. MODO DE RESILIENCIA ACTIVADO.",
        timestamp: Date.now(),
        type: "rizoma/mission/v1",
        objectId: "mock-1",
        data: {
          work: 7,
          members: ["Actor-AD41", "Actor-88F2", "Actor-C12B"],
          composition: {
            layout: 'GRID',
            components: [
              { atom: 'HEADER', props: { title: 'SISTEMA_OPERATIVO' } },
              { atom: 'TEXT', props: { content: 'DETECTADOS FALLOS EN LA CONEXIÓN WEBSOCKET DE WAKU (STATUS.IM). CARGANDO SEÑALES DE EMERGENCIA LOCALES.' } },
              { atom: 'PROGRESS', props: { current: 'work', max: 10 } },
              { atom: 'MAP', props: { label: 'ZONA_DE_RESCATE' } },
              { atom: 'BUTTON', props: { label: 'FORZAR_RECONEXIÓN', action: 'RETRY' } }
            ]
          }
        }
      },
      {
        sender: "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        alias: "Rosario",
        text: "Sigo recolectando semillas de tomate platense.",
        timestamp: Date.now() - 3600000,
        type: "rizoma/seed-exchange/v1",
        data: { species: "Tomate", variety: "Platense" }
      }
    ];
  }

  aggregateSemanticState(rawItems: any[]): any[] {
    const registry = new Map<string, any>();
    const sorted = [...rawItems].sort((a, b) => a.timestamp - b.timestamp);
    for (const item of sorted) {
      const id = item.objectId || `${item.sender}-${item.timestamp}`;
      if (!registry.has(id)) registry.set(id, { ...item, _history: [item] });
      else {
        const current = registry.get(id);
        const updatedData = { ...current.data, ...item.data };
        if (item.action === 'JOIN' && item.alias) updatedData.members = [...(updatedData.members || []), item.alias];
        registry.set(id, { ...current, ...item, data: updatedData, _history: [...current._history, item] });
      }
    }
    return Array.from(registry.values()).sort((a, b) => b.timestamp - a.timestamp);
  }

  async getLatentSchemas(): Promise<any[]> {
    const saved = localStorage.getItem('rizoma_latent_schemas');
    const defaultSchemas = [
      { 
        id: 'rizoma/seed-exchange/v1', 
        name: 'Intercambio de Semillas', 
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><path d="M12 2L7 7h10l-5-5zM5 10v10h14V10H5zm2 2h10v6H7v-6z"/></svg>',
        description: 'Intercambio de biodiversidad local.',
        fields: [{ name: 'species', label: 'Especie' }, { name: 'variety', label: 'Variedad' }],
        composition: { layout: 'LIST', components: [{ atom: 'HEADER', props: { title: 'SEMILLAS' } }, { atom: 'BADGE', props: { label: 'Especie' }, binding: 'species' }, { atom: 'BUTTON', props: { label: 'CONTACTAR', action: 'INTERACT' } }] }
      },
      { 
        id: 'rizoma/time-bank/v1', 
        name: 'Banco de Tiempo', 
        icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="square"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>',
        description: 'Ayuda mutua por horas.',
        fields: [{ name: 'service', label: 'Actividad' }, { name: 'hours', label: 'Horas', type: 'number' }],
        composition: { layout: 'LIST', components: [{ atom: 'HEADER', props: { title: 'TIEMPO' } }, { atom: 'BADGE', props: { label: 'Horas' }, binding: 'hours' }, { atom: 'BUTTON', props: { label: 'OFRECER', action: 'INTERACT' } }] }
      }
    ];
    return saved ? JSON.parse(saved) : defaultSchemas;
  }

  async proposeSchema(schema: any) {
    const schemas = await this.getLatentSchemas();
    schemas.push(schema);
    localStorage.setItem('rizoma_latent_schemas', JSON.stringify(schemas));
    await this.announceIntention(`Nueva funcionalidad: ${schema.name}`, 'SCHEMA_PROPOSAL', schema);
  }

  async closeIntention(originalTimestamp: number) {
    if (!this.wakuNode || this.wakuStatus !== 'online') throw new Error("Offline");
    const encoder = createEncoder({ contentTopic: CONTENT_TOPIC, pubsubTopicShardInfo: { clusterId: 1, shard: 1 } });
    const payload = JSON.stringify({ type: 'INTENTION_PATCH', action: 'CLOSE', targetTimestamp: originalTimestamp, sender: this.wallet?.address, timestamp: Date.now() });
    await this.wakuNode.lightPush.send(encoder, { payload: await this.encryptWithKey(payload, NETWORK_KEY) });
  }

  async getPublicProfile(address: string): Promise<{profile: UserProfile, stats: RizomaStats}> {
    return { profile: { address, email: "", alias: `Actor-${address.slice(-4).toUpperCase()}` }, stats: { masa: 150, resonancias: 12, antiguedad: "3 MESES" } };
  }

  async importarLlave(privateKey: string): Promise<UserProfile> {
    // Escalera de custodia (01_red §5): la persona se lleva su llave delegada
    // del puente a este dispositivo. La llave pasa a custodiarse localmente;
    // la identidad y el historial no cambian (la dirección es la misma).
    this.wallet = new ethers.Wallet(privateKey);
    const shortAddr = this.wallet.address.slice(-4).toUpperCase();
    this.profile = {
      address: this.wallet.address,
      email: "",
      alias: `Actor-${shortAddr}`,
      publicKey: this.wallet.signingKey.publicKey
    };
    localStorage.setItem('rizoma_session', JSON.stringify({ importedKey: privateKey }));
    this.initWaku();
    return this.profile;
  }

  async restaurarSesion(): Promise<UserProfile | null> {
    const saved = localStorage.getItem('rizoma_session');
    if (!saved) return null;
    const s = JSON.parse(saved);
    if (s.importedKey) return await this.importarLlave(s.importedKey);
    if (s.email) return await this.login(s.email);
    return null;
  }

  async signActo(canonical: string): Promise<string> {
    // Firma EIP-191 del acto de dirigirse (rizoma.link). La palabra NO se
    // firma ni viaja al servidor: viaja cifrada por el topic derivado.
    if (!this.wallet) throw new Error("SIN_LLAVE");
    return await this.wallet.signMessage(canonical);
  }

  updateAlias(newAlias: string) { if (this.profile) { this.profile.alias = newAlias; localStorage.setItem('rizoma_profile_alias', newAlias); } }
  getProfile(): UserProfile | null { return this.profile; }
  getContacts(): Contact[] { return JSON.parse(localStorage.getItem('rizoma_contacts') || '[]'); }
  saveContact(contact: Contact) {
    const contacts = this.getContacts();
    if (!contacts.find(c => c.address === contact.address)) { contacts.push(contact); localStorage.setItem('rizoma_contacts', JSON.stringify(contacts)); }
  }
  getFolders(): Folder[] { return JSON.parse(localStorage.getItem('rizoma_folders') || '[{"id":"1","name":"Favoritos"}]'); }
  saveFolders(folders: Folder[]) { localStorage.setItem('rizoma_folders', JSON.stringify(folders)); }
  private async getResonanceTopic(peerAddress: string): Promise<string> {
    const myAddr = this.wallet?.address || "";
    const addresses = [myAddr.toLowerCase(), peerAddress.toLowerCase()].sort();
    return `/rizoma/v1/resonance/${ethers.id(addresses.join("|"))}/proto`;
  }
  private async deriveSharedSecret(peerPublicKey: string): Promise<CryptoKey> {
    const sharedSecretHex = this.wallet!.signingKey.computeSharedSecret(peerPublicKey);
    return await crypto.subtle.importKey("raw", ethers.getBytes(sharedSecretHex).slice(0, 32), { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
  }
  private async encryptE2EE(text: string, peerPublicKey: string): Promise<Uint8Array> {
    const key = await this.deriveSharedSecret(peerPublicKey);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(text));
    const result = new Uint8Array(iv.length + ciphertext.byteLength);
    result.set(iv); result.set(new Uint8Array(ciphertext), iv.length);
    return result;
  }
  private async decryptE2EE(data: Uint8Array, peerPublicKey: string): Promise<string> {
    const key = await this.deriveSharedSecret(peerPublicKey);
    const decrypted = await crypto.subtle.decrypt({ name: "AES-GCM", iv: data.slice(0, 12) }, key, data.slice(12));
    return new TextDecoder().decode(decrypted);
  }
  private async encryptWithKey(text: string, keyBytes: Uint8Array): Promise<Uint8Array> {
    const key = await crypto.subtle.importKey("raw", keyBytes.slice(), { name: "AES-GCM" }, false, ["encrypt"]);
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ciphertext = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(text));
    const result = new Uint8Array(iv.length + ciphertext.byteLength);
    result.set(iv); result.set(new Uint8Array(ciphertext), iv.length);
    return result;
  }
  private async decryptWithKey(data: Uint8Array, keyBytes: Uint8Array): Promise<string> {
    const key = await crypto.subtle.importKey("raw", keyBytes.slice(), { name: "AES-GCM" }, false, ["decrypt"]);
    const decrypted = await crypto.subtle.decrypt({ name: "AES-GCM", iv: data.slice(0, 12) }, key, data.slice(12));
    return new TextDecoder().decode(decrypted);
  }
}
export const rizoma = new RizomaSovereign();
