from __future__ import annotations

from collections.abc import Iterable, Iterator


_MASK64 = (1 << 64) - 1
_GOLDEN_RATIO = 0x9E3779B97F4A7C13


def _u64(value: int) -> int:
    return value & _MASK64


def _mix(values: list[int]) -> None:
    a, b, c, d, e, f, g, h = values
    a = _u64(a - e); f = _u64(f ^ (h >> 9)); h = _u64(h + a)
    b = _u64(b - f); g = _u64(g ^ _u64(a << 9)); a = _u64(a + b)
    c = _u64(c - g); h = _u64(h ^ (b >> 23)); b = _u64(b + c)
    d = _u64(d - h); a = _u64(a ^ _u64(c << 15)); c = _u64(c + d)
    e = _u64(e - a); b = _u64(b ^ (d >> 14)); d = _u64(d + e)
    f = _u64(f - b); c = _u64(c ^ _u64(e << 20)); e = _u64(e + f)
    g = _u64(g - c); d = _u64(d ^ (f >> 17)); f = _u64(f + g)
    h = _u64(h - d); e = _u64(e ^ _u64(g << 14)); g = _u64(g + h)
    values[:] = [a, b, c, d, e, f, g, h]


class Isaac64:
    """Independent ISAAC-64 implementation based on Bob Jenkins' public-domain spec."""

    def __init__(self, seed: int) -> None:
        if not 0 <= seed <= _MASK64:
            raise ValueError("ISAAC-64 seed must be an unsigned 64-bit integer")
        self._memory = [0] * 256
        self._results = [0] * 256
        self._results[0] = seed
        self._a = 0
        self._b = 0
        self._c = 0
        self._index = 255
        self._initialize()

    def _initialize(self) -> None:
        values = [_GOLDEN_RATIO] * 8
        for _ in range(4):
            _mix(values)
        for offset in range(0, 256, 8):
            for index in range(8):
                values[index] = _u64(values[index] + self._results[offset + index])
            _mix(values)
            self._memory[offset : offset + 8] = values
        for offset in range(0, 256, 8):
            for index in range(8):
                values[index] = _u64(values[index] + self._memory[offset + index])
            _mix(values)
            self._memory[offset : offset + 8] = values
        self._generate()

    def _generate(self) -> None:
        self._c = _u64(self._c + 1)
        self._b = _u64(self._b + self._c)
        for index in range(256):
            if index % 4 == 0:
                self._a = _u64(~(self._a ^ _u64(self._a << 21)))
            elif index % 4 == 1:
                self._a = _u64(self._a ^ (self._a >> 5))
            elif index % 4 == 2:
                self._a = _u64(self._a ^ _u64(self._a << 12))
            else:
                self._a = _u64(self._a ^ (self._a >> 33))
            self._a = _u64(self._a + self._memory[(index + 128) & 0xFF])
            value = self._memory[index]
            mixed = _u64(self._memory[(value >> 3) & 0xFF] + self._a + self._b)
            self._memory[index] = mixed
            self._b = _u64(self._memory[(mixed >> 11) & 0xFF] + value)
            self._results[index] = self._b

    def next_u64(self) -> int:
        result = self._results[self._index]
        if self._index == 0:
            self._generate()
            self._index = 255
        else:
            self._index -= 1
        return result

    def keystream(self) -> Iterator[int]:
        while True:
            yield from self.next_u64().to_bytes(8, "big")


class WechatVideoDecryptor:
    """Stream XOR only the declared encrypted prefix of a Channels media file."""

    def __init__(self, key: int, encrypted_length: int = 131_072, offset: int = 0) -> None:
        if encrypted_length < 0 or offset < 0:
            raise ValueError("encrypted length and offset must be non-negative")
        self.encrypted_length = encrypted_length
        self.offset = offset
        self._stream = Isaac64(key).keystream()
        for _ in range(min(offset, encrypted_length)):
            next(self._stream)

    def transform(self, data: bytes) -> bytes:
        if not data:
            return b""
        result = bytearray(data)
        encrypted_here = min(len(result), max(0, self.encrypted_length - self.offset))
        for index in range(encrypted_here):
            result[index] ^= next(self._stream)
        self.offset += len(result)
        return bytes(result)


def decrypt_chunks(
    chunks: Iterable[bytes], key: int, encrypted_length: int = 131_072, offset: int = 0
) -> Iterator[bytes]:
    decryptor = WechatVideoDecryptor(key, encrypted_length, offset)
    for chunk in chunks:
        yield decryptor.transform(chunk)
