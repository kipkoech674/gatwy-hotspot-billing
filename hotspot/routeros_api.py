"""Small RouterOS API client for the locally restricted RouterOS 6 API."""

import socket


class RouterOSError(Exception):
    """Raised when RouterOS rejects an API request or the connection fails."""


def _encode_length(length):
    if length < 0x80:
        return bytes((length,))
    if length < 0x4000:
        length |= 0x8000
        return bytes((length >> 8, length & 0xFF))
    if length < 0x200000:
        length |= 0xC00000
        return bytes((length >> 16, (length >> 8) & 0xFF, length & 0xFF))
    if length < 0x10000000:
        length |= 0xE0000000
        return bytes((length >> 24, (length >> 16) & 0xFF, (length >> 8) & 0xFF, length & 0xFF))
    return b"\xF0" + length.to_bytes(4, "big")


class RouterOSAPI:
    def __init__(self, host, username, password, port=8728, timeout=5):
        self.host = host
        self.username = username
        self.password = password
        self.port = int(port)
        self.timeout = timeout
        self.socket = None

    def __enter__(self):
        try:
            self.socket = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self.socket.settimeout(self.timeout)
            reply = self._command("/login", {"name": self.username, "password": self.password})
            if any(sentence[0] in ("!trap", "!fatal") for sentence in reply):
                raise RouterOSError("RouterOS rejected the API credentials.")
            if any(word.startswith("=ret=") for sentence in reply for word in sentence):
                raise RouterOSError("RouterOS requested legacy challenge authentication; this client expects RouterOS 6.43 or later.")
            return self
        except (OSError, TimeoutError) as exc:
            self.close()
            raise RouterOSError("Could not connect or authenticate to the MikroTik API.") from exc
        except Exception:
            self.close()
            raise

    def __exit__(self, *_exc):
        self.close()

    def close(self):
        if self.socket:
            try:
                self.socket.close()
            finally:
                self.socket = None

    def command(self, path, attributes=None, queries=()):
        try:
            replies = self._command(path, attributes or {}, queries)
        except (OSError, TimeoutError) as exc:
            raise RouterOSError("RouterOS API connection failed while running a command.") from exc
        traps = [sentence for sentence in replies if sentence[0] == "!trap"]
        traps = [sentence for sentence in replies if sentence and sentence[0] == "!trap"]
        if traps:
            detail = next((item.split("=", 2)[2] for item in traps[0][1:] if item.startswith("=message=")), "command rejected")
            raise RouterOSError(f"RouterOS API error: {detail}")
        return [self._attributes(sentence) for sentence in replies if sentence and sentence[0] == "!re"]

    def _command(self, path, attributes, queries=()):
        words = [path, *(f"={key}={value}" for key, value in attributes.items()), *(f"?{query}" for query in queries)]
        self.socket.sendall(b"".join(_encode_length(len(word.encode())) + word.encode() for word in words) + b"\x00")
        replies = []
        while True:
            sentence = self._read_sentence()
            if not sentence:
                continue
            replies.append(sentence)
            if sentence[0] in ("!done", "!fatal"):
                return replies

    def _read_exact(self, size):
        chunks = bytearray()
        while len(chunks) < size:
            part = self.socket.recv(size - len(chunks))
            if not part:
                raise RouterOSError("RouterOS closed the API connection.")
            chunks.extend(part)
        return bytes(chunks)

    def _read_word(self):
        first = self._read_exact(1)[0]
        if first < 0x80:
            length = first
        elif first < 0xC0:
            length = ((first & 0x3F) << 8) | self._read_exact(1)[0]
        elif first < 0xE0:
            tail = self._read_exact(2)
            length = ((first & 0x1F) << 16) | int.from_bytes(tail, "big")
        elif first < 0xF0:
            tail = self._read_exact(3)
            length = ((first & 0x0F) << 24) | int.from_bytes(tail, "big")
        elif first == 0xF0:
            length = int.from_bytes(self._read_exact(4), "big")
        else:
            raise RouterOSError("RouterOS sent an unsupported API control byte.")
        return self._read_exact(length).decode("utf-8", errors="replace") if length else ""

    def _read_sentence(self):
        words = []
        while True:
            word = self._read_word()
            if not word:
                return words
            words.append(word)

    @staticmethod
    def _attributes(sentence):
        result = {}
        for word in sentence[1:]:
            if word.startswith("=") and "=" in word[1:]:
                key, value = word[1:].split("=", 1)
                result[key] = value
        return result
