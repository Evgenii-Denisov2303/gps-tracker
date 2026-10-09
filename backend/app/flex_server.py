"""Run with python -m app.flex_server; expose only on a trusted network."""
import asyncio
import ipaddress
import logging
import os

from .flex import Profile, ProtocolError, ntcb, read_frame
from .flex_store import Store

log = logging.getLogger('flex')


class Receiver:
    def __init__(self, store=None, timeout=90, max_connections=32, allowed_networks=()):
        self.store = store or Store()
        self.timeout = timeout
        self.max_connections = max_connections
        self.connections = 0
        self.allowed = tuple(ipaddress.ip_network(n) for n in allowed_networks)

    async def handle(self, reader, writer):
        peer = writer.get_extra_info('peername')
        if self.connections >= self.max_connections or (self.allowed and
                not any(ipaddress.ip_address(peer[0]) in n for n in self.allowed)):
            writer.close()
            await writer.wait_closed()
            return
        self.connections += 1
        imei, profile, identifiers = None, None, None
        try:
            while True:
                # Whole-frame deadline defeats slow clients dripping single bytes.
                kind, value = await asyncio.wait_for(read_frame(reader, profile), self.timeout if imei else 15)
                if kind == 'ntcb':
                    receiver, sender, payload = value
                    if identifiers and identifiers != (receiver, sender):
                        raise ProtocolError('Changed NTCB identifiers')
                    if payload.startswith(b'*>S:') and imei is None:
                        identity = payload[4:]
                        if len(identity) != 15 or not identity.isdigit():
                            raise ProtocolError('Invalid IMEI')
                        imei = identity.decode('ascii')
                        await asyncio.to_thread(self.store.authorize, imei)
                        identifiers = receiver, sender
                        reply = b'*<S'
                    elif imei and payload.startswith(b'*>FLEX'):
                        await asyncio.to_thread(self.store.authorize, imei)
                        profile = Profile(payload)
                        reply = profile.reply
                    elif imei and not payload:
                        await asyncio.to_thread(self.store.save, imei, [])
                        continue
                    else:
                        raise ProtocolError('Unsupported NTCB message')
                    writer.write(ntcb(reply, sender, receiver))
                elif kind == 'ping' and imei and profile and profile.ready:
                    await asyncio.to_thread(self.store.save, imei, [])
                    continue
                elif kind == 'flex' and imei:
                    records, ack = profile.records(value)
                    await asyncio.to_thread(self.store.save, imei, records)
                    writer.write(ack)  # Only after successful database COMMIT.
                else:
                    raise ProtocolError('Handshake required')
                await asyncio.wait_for(writer.drain(), 10)
        except (ProtocolError, asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError) as exc:
            log.info('Connection closed: %s', type(exc).__name__)
        except Exception:
            # Do not log SQL parameters, IMEIs or coordinates from exception text.
            log.error('Receiver storage/processing failure; packet not acknowledged')
        finally:
            self.connections -= 1
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass


async def main():
    host = os.getenv('FLEX_HOST', '127.0.0.1')
    allowed = [n.strip() for n in os.getenv('FLEX_ALLOWED_NETWORKS', '').split(',') if n.strip()]
    # Docker may bind 0.0.0.0 internally, but must explicitly declare its host
    # publication private. A public mobile network is not a trusted network.
    if not ipaddress.ip_address(host).is_loopback and os.getenv('FLEX_TRUSTED_NETWORK') != 'true':
        raise RuntimeError('FLEX requires a trusted network; see docs/INSTALL_NAVTELECOM.md')
    receiver = Receiver(allowed_networks=allowed)
    server = await asyncio.start_server(receiver.handle, host, int(os.getenv('FLEX_PORT', '5221')), limit=16384)
    log.info('FLEX receiver started (private transport, base profile)')
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
