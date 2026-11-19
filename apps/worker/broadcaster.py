import redis
import json
import os
from eth_account import Account
from eth_account.messages import encode_defunct
from datetime import datetime, timezone
import uuid
from packages.domain.identity import KeyStore

class NetworkBroadcaster:
    def __init__(self):
        self.redis = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
        # Identidad propia de esta instalación; nunca una clave de desarrollo compartida.
        self.private_key = os.getenv("GATEWAY_PRIVATE_KEY")
        if not self.private_key:
            _, self.private_key = KeyStore().get_or_create("gateway:default")
        self.account = Account.from_key(self.private_key)
        self.gateway_id = self.account.address
        self.topic = "rizoma.v2.global"

    def broadcast_signal(self, action_type, agent_reasoning, parameters):
        """
        Emite una señal de curación/emergencia a la red global.
        """
        timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        nonce = uuid.uuid4().hex
        
        # Estructura del evento según protocolo v2
        payload = {
            "reasoning": agent_reasoning,
            "parameters": parameters
        }
        
        # Mensaje canónico para firma: rizoma.signal|{gateway_id}|{timestamp}|{nonce}|{action_type}
        msg_text = f"rizoma.signal|{self.gateway_id}|{timestamp}|{nonce}|{action_type}"
        signature = Account.sign_message(encode_defunct(text=msg_text), private_key=self.private_key).signature.hex()

        event = {
            "protocol": "rizoma.v2",
            "action": "signal",
            "action_type": action_type,
            "actor_id": self.gateway_id,
            "timestamp": timestamp,
            "nonce": nonce,
            "payload": payload,
            "signature": signature
        }

        print(f"[*] Emitiendo señal de red ({action_type}): {agent_reasoning}")
        self.redis.publish(self.topic, json.dumps(event))
        return event
