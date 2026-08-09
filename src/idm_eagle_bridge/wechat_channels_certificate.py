from __future__ import annotations

import hashlib
import base64
import json
import math
import os
import secrets
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


_SHA256_WITH_RSA = "1.2.840.113549.1.1.11"
_RSA_ENCRYPTION = "1.2.840.113549.1.1.1"


def _length(value: int) -> bytes:
    if value < 0x80:
        return bytes([value])
    encoded = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _length(len(value)) + value


def _sequence(*items: bytes) -> bytes:
    return _tlv(0x30, b"".join(items))


def _set(*items: bytes) -> bytes:
    return _tlv(0x31, b"".join(items))


def _integer(value: int) -> bytes:
    if value < 0:
        raise ValueError("DER integer must be non-negative")
    encoded = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    if encoded[0] & 0x80:
        encoded = b"\x00" + encoded
    return _tlv(0x02, encoded)


def _oid(value: str) -> bytes:
    parts = [int(part) for part in value.split(".")]
    if len(parts) < 2 or parts[0] > 2 or parts[1] >= 40:
        raise ValueError("invalid OID")
    encoded = bytearray([parts[0] * 40 + parts[1]])
    for part in parts[2:]:
        stack = [part & 0x7F]
        part >>= 7
        while part:
            stack.append(0x80 | (part & 0x7F))
            part >>= 7
        encoded.extend(reversed(stack))
    return _tlv(0x06, bytes(encoded))


def _algorithm(oid: str) -> bytes:
    return _sequence(_oid(oid), _tlv(0x05, b""))


def _name(common_name: str) -> bytes:
    return _sequence(
        _set(_sequence(_oid("2.5.4.10"), _tlv(0x0C, "留底".encode("utf-8")))),
        _set(_sequence(_oid("2.5.4.3"), _tlv(0x0C, common_name.encode("utf-8")))),
    )


def _time_value(timestamp: int) -> bytes:
    value = time.strftime("%Y%m%d%H%M%SZ", time.gmtime(timestamp)).encode("ascii")
    return _tlv(0x18, value)


def _extension(oid: str, payload: bytes, critical: bool = False) -> bytes:
    parts = [_oid(oid)]
    if critical:
        parts.append(_tlv(0x01, b"\xff"))
    parts.append(_tlv(0x04, payload))
    return _sequence(*parts)


def _pem(label: str, data: bytes) -> bytes:
    import base64

    encoded = base64.b64encode(data)
    lines = [encoded[index : index + 64] for index in range(0, len(encoded), 64)]
    return b"-----BEGIN " + label.encode("ascii") + b"-----\n" + b"\n".join(lines) + b"\n-----END " + label.encode("ascii") + b"-----\n"


def _is_probable_prime(candidate: int, rounds: int = 32) -> bool:
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)
    for prime in small_primes:
        if candidate == prime:
            return True
        if candidate % prime == 0:
            return False
    divisor = candidate - 1
    power = 0
    while divisor % 2 == 0:
        power += 1
        divisor //= 2
    for _ in range(rounds):
        base = secrets.randbelow(candidate - 3) + 2
        value = pow(base, divisor, candidate)
        if value in (1, candidate - 1):
            continue
        for _ in range(power - 1):
            value = pow(value, 2, candidate)
            if value == candidate - 1:
                break
        else:
            return False
    return True


def _prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


@dataclass(frozen=True)
class RsaPrivateKey:
    n: int
    e: int
    d: int
    p: int
    q: int

    @classmethod
    def generate(cls, bits: int = 2048) -> "RsaPrivateKey":
        if bits < 2048:
            raise ValueError("RSA key must be at least 2048 bits")
        exponent = 65_537
        while True:
            p = _prime(bits // 2)
            q = _prime(bits - bits // 2)
            if p == q:
                continue
            phi = (p - 1) * (q - 1)
            if math.gcd(exponent, phi) == 1:
                break
        if p < q:
            p, q = q, p
        return cls(p * q, exponent, pow(exponent, -1, phi), p, q)

    @classmethod
    def from_private_pem(cls, content: bytes) -> "RsaPrivateKey":
        lines = [line.strip() for line in content.splitlines() if line and not line.startswith(b"-----")]
        try:
            data = base64.b64decode(b"".join(lines), validate=True)
            tag, payload, end = _read_der_value(data, 0)
            if tag != 0x30 or end != len(data):
                raise ValueError
            integers: list[int] = []
            offset = 0
            while offset < len(payload):
                item_tag, value, offset = _read_der_value(payload, offset)
                if item_tag != 0x02 or not value:
                    raise ValueError
                integers.append(int.from_bytes(value, "big"))
            if len(integers) != 9 or integers[0] != 0:
                raise ValueError
            return cls(integers[1], integers[2], integers[3], integers[4], integers[5])
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid RSA private key") from exc

    def private_der(self) -> bytes:
        return _sequence(
            _integer(0), _integer(self.n), _integer(self.e), _integer(self.d),
            _integer(self.p), _integer(self.q), _integer(self.d % (self.p - 1)),
            _integer(self.d % (self.q - 1)), _integer(pow(self.q, -1, self.p)),
        )

    def public_der(self) -> bytes:
        return _sequence(_integer(self.n), _integer(self.e))

    def subject_public_key_info(self) -> bytes:
        return _sequence(_algorithm(_RSA_ENCRYPTION), _tlv(0x03, b"\x00" + self.public_der()))

    def sign(self, payload: bytes) -> bytes:
        digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(payload).digest()
        size = (self.n.bit_length() + 7) // 8
        padded = b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info
        signature = pow(int.from_bytes(padded, "big"), self.d, self.n)
        return signature.to_bytes(size, "big")


def _read_der_value(data: bytes, offset: int) -> tuple[int, bytes, int]:
    if offset + 2 > len(data):
        raise ValueError("truncated DER")
    tag = data[offset]
    first = data[offset + 1]
    offset += 2
    if first & 0x80:
        count = first & 0x7F
        if count == 0 or count > 4 or offset + count > len(data):
            raise ValueError("invalid DER length")
        length = int.from_bytes(data[offset : offset + count], "big")
        offset += count
    else:
        length = first
    end = offset + length
    if end > len(data):
        raise ValueError("truncated DER value")
    return tag, data[offset:end], end


def _certificate(
    subject: str,
    subject_key: RsaPrivateKey,
    issuer: str,
    issuer_key: RsaPrivateKey,
    *,
    is_ca: bool,
    dns_names: tuple[str, ...] = (),
) -> bytes:
    now = int(time.time())
    spki = subject_key.subject_public_key_info()
    key_id = hashlib.sha1(subject_key.public_der()).digest()
    authority_id = hashlib.sha1(issuer_key.public_der()).digest()
    basic_constraints = _sequence(_tlv(0x01, b"\xff")) if is_ca else _sequence()
    key_usage = b"\x01\x06" if is_ca else b"\x05\xa0"
    extensions = [
        _extension("2.5.29.19", basic_constraints, True),
        _extension("2.5.29.15", _tlv(0x03, key_usage), True),
        _extension("2.5.29.14", _tlv(0x04, key_id)),
        _extension("2.5.29.35", _sequence(_tlv(0x80, authority_id))),
    ]
    if not is_ca:
        extensions.append(_extension("2.5.29.37", _sequence(_oid("1.3.6.1.5.5.7.3.1"))))
        extensions.append(
            _extension("2.5.29.17", _sequence(*(_tlv(0x82, value.encode("ascii")) for value in dns_names)))
        )
    tbs = _sequence(
        _tlv(0xA0, _integer(2)),
        _integer(secrets.randbits(159) | 1),
        _algorithm(_SHA256_WITH_RSA),
        _name(issuer),
        _sequence(_time_value(now - 86_400), _time_value(now + (3_650 if is_ca else 825) * 86_400)),
        _name(subject),
        spki,
        _tlv(0xA3, _sequence(*extensions)),
    )
    return _sequence(tbs, _algorithm(_SHA256_WITH_RSA), _tlv(0x03, b"\x00" + issuer_key.sign(tbs)))


@dataclass(frozen=True)
class CertificateFiles:
    root_der: Path
    root_pem: Path
    root_key: Path
    leaf_pem: Path
    leaf_key: Path
    fingerprint: str


class WechatCertificateAuthority:
    ROOT_NAME = "留底下载器 微信视频号本机捕获根证书"
    LEGACY_ROOT_NAME = "下载中转站 微信视频号本机捕获根证书"
    LEAF_NAME = "channels.weixin.qq.com"
    DNS_NAMES = (
        "channels.weixin.qq.com",
        "*.channels.weixin.qq.com",
        "res.wx.qq.com",
        "*.weixin.qq.com",
        "*.finder.video.qq.com",
    )
    LEAF_PROFILE = 2
    CERTUTIL_TIMEOUT_SECONDS = 15

    def __init__(
        self,
        root: str | Path,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.root = Path(root)
        self.runner = runner

    def ensure(self) -> CertificateFiles:
        existing = self.existing()
        if existing:
            self._ensure_leaf_profile(existing)
            return existing
        self.root.mkdir(parents=True, exist_ok=True)
        root_key = RsaPrivateKey.generate()
        leaf_key = RsaPrivateKey.generate()
        root_der = _certificate(self.ROOT_NAME, root_key, self.ROOT_NAME, root_key, is_ca=True)
        leaf_der = _certificate(
            self.LEAF_NAME, leaf_key, self.ROOT_NAME, root_key, is_ca=False, dns_names=self.DNS_NAMES
        )
        fingerprint = hashlib.sha1(root_der).hexdigest().upper()
        files = self._files(fingerprint)
        self._write_private(files.root_key, _pem("RSA PRIVATE KEY", root_key.private_der()))
        self._write_private(files.leaf_key, _pem("RSA PRIVATE KEY", leaf_key.private_der()))
        files.root_der.write_bytes(root_der)
        files.root_pem.write_bytes(_pem("CERTIFICATE", root_der))
        files.leaf_pem.write_bytes(_pem("CERTIFICATE", leaf_der))
        (self.root / "certificate.json").write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "subject": self.ROOT_NAME,
                    "leafProfile": self.LEAF_PROFILE,
                    "dnsNames": list(self.DNS_NAMES),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return files

    def _ensure_leaf_profile(self, files: CertificateFiles) -> None:
        metadata_path = self.root / "certificate.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            metadata = {}
        if (
            metadata.get("leafProfile") == self.LEAF_PROFILE
            and metadata.get("dnsNames") == list(self.DNS_NAMES)
        ):
            return
        root_key = RsaPrivateKey.from_private_pem(files.root_key.read_bytes())
        # 已信任的旧根证书不能只改显示名称；否则叶证书的 issuer
        # 将与证书库中的根证书 subject 不匹配。新安装使用新品牌，
        # 升级安装继续安全复用原证书，直至用户主动卸载。
        root_subject = str(metadata.get("subject") or self.ROOT_NAME)
        leaf_key = RsaPrivateKey.generate()
        leaf_der = _certificate(
            self.LEAF_NAME,
            leaf_key,
            root_subject,
            root_key,
            is_ca=False,
            dns_names=self.DNS_NAMES,
        )
        key_temp = files.leaf_key.with_suffix(".key.tmp")
        cert_temp = files.leaf_pem.with_suffix(".pem.tmp")
        metadata_temp = metadata_path.with_suffix(".json.tmp")
        self._write_private(key_temp, _pem("RSA PRIVATE KEY", leaf_key.private_der()))
        cert_temp.write_bytes(_pem("CERTIFICATE", leaf_der))
        metadata_temp.write_text(
            json.dumps(
                {
                    "fingerprint": files.fingerprint,
                    "subject": root_subject,
                    "leafProfile": self.LEAF_PROFILE,
                    "dnsNames": list(self.DNS_NAMES),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        os.replace(key_temp, files.leaf_key)
        os.replace(cert_temp, files.leaf_pem)
        os.replace(metadata_temp, metadata_path)

    def existing(self) -> CertificateFiles | None:
        metadata_path = self.root / "certificate.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                files = self._files(str(metadata.get("fingerprint", "")))
                if files.fingerprint and all(
                    path.exists()
                    for path in (
                        files.root_der,
                        files.root_pem,
                        files.root_key,
                        files.leaf_pem,
                        files.leaf_key,
                    )
                ):
                    return files
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        return None

    def _files(self, fingerprint: str) -> CertificateFiles:
        return CertificateFiles(
            self.root / "root.cer", self.root / "root.pem", self.root / "root.key",
            self.root / "channels.pem", self.root / "channels.key", fingerprint,
        )

    @staticmethod
    def _write_private(path: Path, content: bytes) -> None:
        path.write_bytes(content)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def is_trusted(self, fingerprint: str | None = None) -> bool:
        files = self.existing()
        target = fingerprint or (files.fingerprint if files else "")
        if not target:
            return False
        if os.name != "nt":
            return False
        result = self.runner(
            ["certutil", "-user", "-store", "Root", target],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
            timeout=self.CERTUTIL_TIMEOUT_SECONDS,
        )
        return result.returncode == 0

    def install(self) -> CertificateFiles:
        files = self.ensure()
        if os.name != "nt":
            raise RuntimeError("视频号证书信任仅支持 Windows")
        if self.is_trusted(files.fingerprint):
            return files
        result = self.runner(
            ["certutil", "-user", "-addstore", "Root", str(files.root_der)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
            timeout=self.CERTUTIL_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise RuntimeError("无法信任视频号本机捕获证书，请检查 Windows 证书权限")
        return files

    def uninstall(self) -> bool:
        files = self.existing()
        if not files:
            return False
        if os.name != "nt":
            return False
        if not self.is_trusted(files.fingerprint):
            return False
        try:
            result = self.runner(
                ["certutil", "-user", "-delstore", "Root", files.fingerprint],
                capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
                timeout=self.CERTUTIL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("移除视频号本机捕获证书超时") from exc
        if result.returncode != 0:
            raise RuntimeError("无法移除视频号本机捕获证书")
        return True
