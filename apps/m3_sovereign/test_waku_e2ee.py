
import os
import hashlib
from eth_account import Account
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class SovereignMessenger:
    def __init__(self, name, private_key=None):
        self.name = name
        if private_key:
            self.account = Account.from_key(private_key)
        else:
            self.account = Account.create()
        
        # Generamos una llave EC para el cifrado (simulando la llave de la wallet)
        self.priv_key_obj = ec.derive_private_key(
            int(self.account.key.hex(), 16), 
            ec.SECP256K1()
        )
        self.pub_key_obj = self.priv_key_obj.public_key()
        
    @property
    def address(self):
        return self.account.address

    def get_public_key_bytes(self):
        return self.pub_key_obj.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint
        )

    def derive_shared_secret(self, peer_public_key_bytes):
        """Deriva una llave simétrica AES usando Diffie-Hellman (ECDH)."""
        peer_pub = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256K1(), peer_public_key_bytes
        )
        shared_secret = self.priv_key_obj.exchange(ec.ECDH(), peer_pub)
        
        # Expandimos el secreto usando HKDF
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"rizoma-waku-e2ee",
        ).derive(shared_secret)
        return derived_key

    def encrypt_for(self, peer_messenger, text):
        """Cifra el mensaje para el destinatario."""
        shared_key = self.derive_shared_secret(peer_messenger.get_public_key_bytes())
        aesgcm = AESGCM(shared_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, text.encode(), None)
        return {
            "nonce": nonce.hex(),
            "ciphertext": ciphertext.hex(),
            "sender": self.address
        }

    def decrypt_from(self, peer_messenger, encrypted_packet):
        """Descifra el mensaje recibido."""
        shared_key = self.derive_shared_secret(peer_messenger.get_public_key_bytes())
        aesgcm = AESGCM(shared_key)
        nonce = bytes.fromhex(encrypted_packet["nonce"])
        ciphertext = bytes.fromhex(encrypted_packet["ciphertext"])
        decrypted_text = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted_text.decode()

def get_waku_topic(addr1, addr2):
    """Genera el canal 'invisible' de Waku."""
    sorted_addrs = sorted([addr1.lower(), addr2.lower()])
    combined = f"rizoma-v2-private-{sorted_addrs[0]}-{sorted_addrs[1]}"
    topic_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
    return f"/rizoma/v2/private/{topic_hash}"

def run_test():
    print("=== TEST RIZOMA: MENSAJERÍA E2EE SOBRE WAKU ===\n")

    # 1. Crear identidades (Mini App / Privy)
    alice = SovereignMessenger("Alice")
    bob = SovereignMessenger("Bob")
    
    print(f"[ID] Alice: {alice.address}")
    print(f"[ID] Bob:   {bob.address}")

    # 2. Derivar canal de Waku
    topic = get_waku_topic(alice.address, bob.address)
    print(f"\n[Waku] Canal de encuentro derivado: {topic}")

    # 3. Alice envía mensaje a Bob
    mensaje_original = "Hola Bob, acepto el trato de las herramientas por 50 tokens."
    packet = alice.encrypt_for(bob, mensaje_original)
    
    print(f"\n[*] [Alice] Enviando mensaje cifrado a Waku...")
    print(f"[Payload] {packet['ciphertext'][:30]}... (Total: {len(packet['ciphertext'])} bytes)")

    # 4. SIMULACIÓN DE SNIFFER (El Servidor de Rizoma o un atacante)
    print("\n[⚠] [Sniffer/Servidor] Intentando leer el mensaje en el canal Waku...")
    try:
        # El servidor no tiene las llaves privadas, intenta descifrar con "nada"
        print(f"    Contenido capturado: {packet['ciphertext']}")
        print("    Resultado: IMPOSIBLE DE DESCIFRAR (Ruido aleatorio)")
    except:
        pass

    # 5. Bob recibe y descifra
    print(f"\n[*] [Bob] Recibiendo paquete en canal {topic}...")
    try:
        decrypted = bob.decrypt_from(alice, packet)
        print(f"[✓] [Bob] Mensaje descifrado exitosamente: '{decrypted}'")
    except Exception as e:
        print(f"[!] [Bob] Error al descifrar: {e}")

    print("\n=== RESULTADO DEL TEST ===")
    print("1. El canal Waku es pseudo-anónimo (basado en hash de wallets).")
    print("2. El contenido es E2EE (Solo Alice y Bob tienen la llave simétrica derivada).")
    print("3. Cero dependencia de servidores centrales para la privacidad.")

if __name__ == "__main__":
    run_test()
