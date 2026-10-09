"""Navtelecom NTCB/FLEX 1.0 receiver profile (protocol manual v6, sections 1/A).

Transport is intentionally plain TCP for a private network. No device-control
commands are implemented. IMEI is an identifier, not a password.
"""
import struct
from functools import reduce
from operator import xor


class ProtocolError(ValueError):
    pass


def checksum(data):
    return reduce(xor, data, 0)


def crc8(data):
    value = 0xff
    for byte in data:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ (0x31 if value & 0x80 else 0)) & 0xff
    return value


def ntcb(payload, receiver=0, sender=1):
    header = struct.pack('<4sIIHB', b'@NTC', receiver, sender, len(payload), checksum(payload))
    return header + bytes([checksum(header)]) + payload


# First twenty fields are stable across FLEX structures 1, 2 and 3. Require
# an explicit small profile; never guess lengths of unsupported sensor fields.
FORMATS = dict(enumerate(('I', 'H', 'I', 'B', 'B', 'B', 'B', 'B', 'I', 'i',
                          'i', 'i', 'f', 'H', 'f', 'f', 'H', 'H', 'H', 'H'), 1))
RECOMMENDED_FIELDS = (1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 13, 14, 19, 20)


class Profile:
    def __init__(self, payload):
        if len(payload) < 10 or payload[:6] != b'*>FLEX' or payload[6] != 0xb0:
            raise ProtocolError('Invalid FLEX negotiation')
        protocol, structure, bits = payload[7:10]
        if protocol not in (10, 20, 30) or structure not in (10, 20, 30):
            raise ProtocolError('Unsupported FLEX version')
        if bits != {10: 69, 20: 122, 30: 255}[structure] or len(payload) != 10 + (bits + 7) // 8:
            raise ProtocolError('Invalid FLEX mask length')
        mask = payload[10:]
        if bits % 8 and mask[-1] & ((1 << (8 - bits % 8)) - 1):
            raise ProtocolError('Nonzero reserved mask bits')
        self.fields = [n for n in range(1, bits + 1) if mask[(n-1)//8] & (0x80 >> ((n-1) % 8))]
        if not {1, 2, 3}.issubset(self.fields) or any(n not in FORMATS for n in self.fields):
            raise ProtocolError('Unsupported field profile; configure fields 1 through 20 only')
        self.layout = struct.Struct('<' + ''.join(FORMATS[n] for n in self.fields))
        # Negotiate the base protocol and structure before accepting telemetry.
        self.ready = protocol == structure == 10
        self.reply = b'*<FLEX\xb0\x0a\x0a'

    def records(self, packet):
        if not self.ready or crc8(packet[:-1]) != packet[-1]:
            raise ProtocolError('Invalid FLEX checksum or negotiation')
        command = packet[1:2]
        offset = {b'A': 3, b'T': 6, b'C': 2}.get(command)
        if offset is None:
            raise ProtocolError('Unsupported FLEX message')
        count = packet[2] if command == b'A' else 1
        if count < 1 or len(packet) != offset + count * self.layout.size + 1:
            raise ProtocolError('Invalid FLEX length')
        records = [dict(zip(self.fields, self.layout.unpack_from(packet, offset + i*self.layout.size))) for i in range(count)]
        if command == b'T' and records[0][1] != struct.unpack_from('<I', packet, 2)[0]:
            raise ProtocolError('Conflicting event index')
        ack = packet[:offset]
        return records, ack + bytes([crc8(ack)])


async def read_frame(reader, profile):
    """Read exactly one bounded frame; TCP fragmentation/coalescing is normal."""
    first = await reader.readexactly(1)
    if first == b'\x7f':
        return 'ping', None
    if first == b'@':
        head = first + await reader.readexactly(15)
        magic, receiver, sender, length, payload_crc, header_crc = struct.unpack('<4sIIHBB', head)
        if magic != b'@NTC' or checksum(head[:15]) != header_crc or length > 1024:
            raise ProtocolError('Invalid NTCB header')
        payload = await reader.readexactly(length)
        if checksum(payload) != payload_crc:
            raise ProtocolError('Invalid NTCB payload')
        return 'ntcb', (receiver, sender, payload)
    if first != b'~' or profile is None or not profile.ready:
        raise ProtocolError('Unexpected frame')
    command = await reader.readexactly(1)
    if command == b'A':
        prefix = await reader.readexactly(1)
        count = prefix[0]
    elif command == b'T':
        prefix, count = await reader.readexactly(4), 1
    elif command == b'C':
        prefix, count = b'', 1
    else:
        raise ProtocolError('Unsupported FLEX command')
    size = count * profile.layout.size
    if not count or size > 8192:
        raise ProtocolError('Oversized FLEX data')
    return 'flex', first + command + prefix + await reader.readexactly(size + 1)
