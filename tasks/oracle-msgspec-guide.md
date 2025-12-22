# msgspec Guide for klaw-core

This guide synthesizes the msgspec research, benchmarks, and production usage patterns relevant to klaw-core (Ray-based runtime/channels). It's meant as the team's reference for designing message schemas, configuring encoders/decoders, and tuning performance.

______________________________________________________________________

## 1. Executive Summary – Why msgspec for klaw-core

**Why msgspec over Pydantic / dataclasses for klaw-core:**

- **Type system + tooling first.**

  - msgspec uses *standard* Python typing, is **PEP 561** compliant, and exposes `Struct` via `@dataclass_transform` so mypy/pyright understand it without plugins.
  - Pydantic relies heavily on runtime behavior and requires a **mypy plugin** for decent typing; pyright support is partial.

- **Runtime behavior optimized for our workload.**

  - `msgspec.Struct` is **strictly typed at decode time** (for external data), but **does not validate on `__init__`**, so internal object creation is cheap.
  - Encoders/decoders are **strict by default** (no silent coercions), with **`strict=False`** available where you *want* coercion (CLI/config/etc).

- **Performance and footprint.**

  - JSON+validation benchmark: msgspec is ~**12× faster** than Pydantic v2, ~**85× faster** than Pydantic v1 on representative schemas.
  - Struct creation: msgspec is ~**17× faster** than Pydantic models.
  - Library size: msgspec ~**0.46 MiB** vs Pydantic ~**6.71 MiB** (~15× smaller).
  - MessagePack & JSON implementations are among the fastest available in Python.

- **Exactly what klaw-core needs.**

  - Channel messages and Ray workers are latency/throughput sensitive, schema-stable, and highly typed → ideal for msgspec's **Struct + MessagePack** pipeline.
  - Existing patterns in `klaw-core` (e.g. `ReaderInfo`, `SingleResult[T]`, `BatchResult[T]`, `ChannelMetadata`) already follow recommended msgspec best practices: `frozen=True`, `gc=False`, and generics.

______________________________________________________________________

## 2. Typing & Static Analysis

### 2.1 msgspec vs Pydantic – typing model

| Aspect                  | msgspec                                      | Pydantic v2                                     |
| ----------------------- | -------------------------------------------- | ----------------------------------------------- |
| **Static analysis**     | Plugin-free, works with mypy **and** pyright | Requires mypy plugin; pyright degrades to `Any` |
| **Strict by default**   | ✅ Yes, no config needed                     | ❌ Requires `strict=True` everywhere            |
| **Generic inference**   | Clean `Generic[T]` across all tools          | Plugin-dependent, can leak `Any`                |
| **Frozen immutability** | Type checkers see `frozen=True`              | Runtime-only; static tools still see mutability |
| **Union safety**        | Enforces unambiguous unions                  | Can silently pick wrong branch                  |
| **Validation location** | Decode-time only (fast init)                 | Init + decode (slower)                          |

**msgspec:**

- `msgspec.Struct` behaves like a dataclass for type-checkers:
  - Fields are defined via type annotations.
  - `__init__` signature is inferred from annotations.
  - Static tools (mypy, pyright, IDEs) understand attributes directly.
- **No runtime validation in `__init__`.**
  - `Point(x=1, y="oops")` is *allowed* at runtime, but static analysis will flag it.
  - Validation happens when decoding external data (`msgspec.json.decode(..., type=Point)`), which is what matters for channels and network boundaries.
- Validation is **zero-cost relative to decode**: decoding and validating into a struct is typically faster than decoding into a dict and validating separately.

**Pydantic (v1 & v2):**

- Models validate on `__init__` and during parsing (`parse_obj`, `model_validate`).
- Typing is more dynamic:
  - Without the mypy plugin, type inference for fields, validators, etc. is incomplete.
  - Many behaviors are runtime-only and opaque to type-checkers.

**Takeaway for klaw-core:**
For internal APIs and Ray worker channels, msgspec's "static typing + decode-time validation" is a better fit and avoids runtime overheads in hot paths.

______________________________________________________________________

### 2.2 `@dataclass_transform` & PEP 561

msgspec's typing stubs mark `Struct` using **PEP 681 `@dataclass_transform`**, which tells type-checkers:

- "Treat subclasses of `msgspec.Struct` like dataclasses":
  - Infer constructor signatures from fields.
  - Validate keyword arguments at call sites.
  - Know that attributes exist and have given types.

Combined with **PEP 561 (`py.typed`)** compliance:

- mypy/pyright see msgspec as a **typed library**, no additional configuration required.
- Static analysis works across:
  - `msgspec.Struct`
  - Decoders: `Decoder(type=MyStruct)` → `decode(...)` returns `MyStruct`.
  - Converters (`to_builtins`, `convert`, etc).

______________________________________________________________________

### 2.3 mypy / pyright integration

**msgspec:**

- Just install and run mypy/pyright; no plugin required.
- Example:

```python
import msgspec


class ChannelMetadata(msgspec.Struct, frozen=True, gc=False):
    channel_type: str
    capacity: int | None
    unbounded: bool


decoder = msgspec.msgpack.Decoder(ChannelMetadata)

data = decoder.decode(b'...')  # type: ChannelMetadata
reveal_type(data.channel_type)  # mypy/pyright: builtins.str
```

**Pydantic:**

- **mypy**: Recommended to enable the Pydantic mypy plugin to get correct typing for fields and validators. Without plugin, many checks are missed or treated as `Any`.
- **pyright**: Limited deep understanding of Pydantic models; some behaviors remain dynamic. No first-party plugin equivalent.

**Impact:**
Using msgspec for all klaw-core schemas keeps type-checker configuration minimal while giving accurate types across the codebase.

______________________________________________________________________

### 2.4 Generic type support

msgspec supports generics over `Struct`, dataclasses, attrs, TypedDict, NamedTuple.

Example mirroring klaw-core patterns:

```python
from __future__ import annotations
from typing import Generic, TypeVar
import msgspec

T = TypeVar('T')


class SingleResult(msgspec.Struct, Generic[T], frozen=True, gc=False):
    status: str
    value: T | None = None


class BatchResult(msgspec.Struct, Generic[T], frozen=True, gc=False):
    status: str
    items: tuple[T, ...] = ()
```

Decoding:

```python
# Typed decoders
single_decoder = msgspec.msgpack.Decoder(SingleResult[int])
batch_decoder = msgspec.msgpack.Decoder(BatchResult[str])

single = single_decoder.decode(buf)  # type: SingleResult[int]
batch = batch_decoder.decode(buf2)  # type: BatchResult[str]
```

Static tools substitute the concrete type arguments (`int`, `str`), so uses are fully typed.

______________________________________________________________________

### 2.5 Strict-by-default vs opt-in coercions

- All decoders (`json`, `msgpack`, `yaml`, `toml`) support a **`strict`** flag (default `True`).

- In **strict mode**:

  - No unsafe coercions: `"123"` → `int` is an error, not silently cast.
  - This is ideal for network boundaries and channel protocols.

- **Lax mode** (`strict=False`):

  - Enables additional coercions (e.g. `"123"` → `int`, `0`/`1` → `bool`, etc.).
  - Useful for CLI input, human-authored config files, backwards-compatible API input.

```python
decoder_strict = msgspec.json.Decoder(int, strict=True)
decoder_lax = msgspec.json.Decoder(int, strict=False)

decoder_strict.decode(b'"123"')  # ValidationError
decoder_lax.decode(b'"123"')  # 123
```

For klaw-core:

- **Channels / Ray messages:** always keep `strict=True`.
- **Config / CLI:** can consider `strict=False` where appropriate.

______________________________________________________________________

## 3. Performance Optimizations

### 3.1 Encoder / Decoder reuse

Creating encoders/decoders has overhead; reuse them in hot paths.

```python
# ❌ Bad (allocates encoder each time)
def encode_msg(msg: msgspec.Struct) -> bytes:
    return msgspec.msgpack.encode(msg)


# ✅ Good: create once per worker / process
import msgspec

msgpack_encoder = msgspec.msgpack.Encoder()
msgpack_decoder = msgspec.msgpack.Decoder(SingleResult[bytes])


def encode_msg(msg: msgspec.Struct) -> bytes:
    return msgpack_encoder.encode(msg)


def decode_msg(buf: bytes) -> SingleResult[bytes]:
    return msgpack_decoder.decode(buf)
```

**Pattern for klaw-core:** Each **Ray worker** should construct encoders/decoders *once* at startup and reuse them.

______________________________________________________________________

### 3.2 `gc=False` – when and how

Structs with `gc=False` are never tracked by Python's cyclic GC:

- **Reduces GC pauses** in workloads that allocate many structs.
- But: **any cycle consisting only of `gc=False` objects will leak**.

```python
# ✅ Safe candidates (no cycles, only scalars / immutable data)
class ReaderInfo(msgspec.Struct, frozen=True, gc=False):
    reader_id: str
    node_id: str
    registered_at: datetime
    last_seen_at: datetime
    total_received: int
```

**Guidelines for klaw-core:**

- ✅ Use for: Immutable metadata types (`ReaderInfo`, `ChannelMetadata`), result wrappers with acyclic payloads
- ❌ Avoid for: Graph-like structures, trees with back-references

______________________________________________________________________

### 3.3 `frozen=True` – immutability & hashing

```python
class ChannelMetadata(msgspec.Struct, frozen=True, gc=False):
    channel_type: ChannelType
    capacity: int | None
    unbounded: bool
    value_type: str | None = None
```

**Benefits:**

- Prevents post-init mutation
- Adds `__hash__` implementation (can use as dict keys)
- Safe to share across threads/process contexts
- Matches Ray's distributed semantics

______________________________________________________________________

### 3.4 `array_like=True` – ~2× decode speedup

```python
# Default: encoded as JSON objects / MessagePack maps
class Point(msgspec.Struct):
    x: int
    y: int


msgspec.json.encode(Point(1, 2))  # b'{"x":1,"y":2}'


# With array_like: encoded as arrays
class PointA(msgspec.Struct, array_like=True):
    x: int
    y: int


msgspec.json.encode(PointA(1, 2))  # b'[1,2]'
```

**Benefits:** ~2× faster decode, ~1.5× faster encode, smaller messages
**Trade-off:** Less self-describing; good for internal, schema-stable protocols

______________________________________________________________________

### 3.5 `omit_defaults=True` – smaller payloads

```python
class User(msgspec.Struct, omit_defaults=True):
    name: str
    email: str | None = None
    groups: set[str] = set()


alice = User('alice')
msgspec.json.encode(alice)  # b'{"name":"alice"}' (not full object)
```

**Effects:** Reduces wire size, speeds up encode/decode

______________________________________________________________________

### 3.6 `encode_into` – buffer reuse

```python
encoder = msgspec.msgpack.Encoder()
buffer = bytearray(64)

for msg in messages:
    encoder.encode_into(msg, buffer, 0)  # Overwrite from offset 0
    await socket.sendall(buffer)
```

**Length-prefix framing pattern:**

```python
async def send_prefixed(writer, msg):
    buf = bytearray(64)
    encoder.encode_into(msg, buf, 4)  # leave space for length
    n = len(buf) - 4
    buf[:4] = n.to_bytes(4, 'big')
    writer.write(buf)
    await writer.drain()
```

______________________________________________________________________

### 3.7 MessagePack vs JSON selection

| Format          | Best for                                                 |
| --------------- | -------------------------------------------------------- |
| **MessagePack** | Internal protocols, Ray workers, high-throughput streams |
| **JSON**        | Public APIs, CLI, debugging, interop                     |

**klaw-core guideline:** Use `msgspec.msgpack` for channel payloads, `msgspec.json` for config/diagnostics.

______________________________________________________________________

### 3.8 Performance comparison

| Scenario               | msgspec  | vs Pydantic v2 | vs Pydantic v1 |
| ---------------------- | -------- | -------------- | -------------- |
| JSON decode + validate | 1.0×     | ~12× faster    | ~85× faster    |
| Struct creation        | 1.0×     | ~17× faster    | -              |
| Library size           | 0.46 MiB | ~15× smaller   | -              |

______________________________________________________________________

## 4. Advanced Patterns

### 4.1 Tagged unions for polymorphic messages

```python
class Get(msgspec.Struct, tag=True):
    key: str


class Put(msgspec.Struct, tag=True):
    key: str
    value: bytes


class Delete(msgspec.Struct, tag=True):
    key: str


Request = Get | Put | Delete

decoder = msgspec.msgpack.Decoder(Request)
encoder = msgspec.msgpack.Encoder()

buf = encoder.encode(Put('k', b'data'))
req = decoder.decode(buf)  # type: Request

match req:
    case Get(key):
        ...
    case Put(key, value):
        ...
    case Delete(key):
        ...
```

**Custom tag field/value:**

```python
class EventBase(msgspec.Struct, tag_field='kind'): ...


class DataEvent(EventBase, tag='data'): ...


class HeartbeatEvent(EventBase, tag='hb'): ...
```

______________________________________________________________________

### 4.2 Constraints with `Annotated[T, Meta(...)]`

```python
from typing import Annotated
from msgspec import Struct, Meta

NonNegativeInt = Annotated[int, Meta(ge=0)]
CPULimit = Annotated[float, Meta(ge=0.1, le=64.0)]
Username = Annotated[str, Meta(min_length=3, max_length=32, pattern='^[a-z0-9_-]+$')]


class WorkerLimits(Struct):
    worker_id: str
    max_concurrency: NonNegativeInt
    cpu_limit: CPULimit = 1.0
```

**Supported constraints:**

- Numeric: `ge`, `gt`, `le`, `lt`, `multiple_of`
- Strings: `min_length`, `max_length`, `pattern`
- Sequences: `min_length`, `max_length`
- Datetimes: `tz` (aware/naive)

______________________________________________________________________

### 4.3 Field factories

```python
from typing import Dict
import msgspec


class ChannelState(msgspec.Struct, frozen=True, gc=False):
    last_offsets: Dict[str, int] = msgspec.field(default_factory=dict)
```

Note: Empty `[]`, `{}`, `set()` defaults are handled safely as syntactic sugar.

______________________________________________________________________

### 4.4 Custom hooks

**Encoding hook:**

```python
import datetime as dt


def enc_hook(obj):
    if isinstance(obj, dt.timedelta):
        return obj.total_seconds()
    raise NotImplementedError


encoder = msgspec.json.Encoder(enc_hook=enc_hook)
```

**Decoding hook:**

```python
def dec_hook(type_, obj):
    if type_ is dt.timedelta and isinstance(obj, (int, float)):
        return dt.timedelta(seconds=obj)
    raise NotImplementedError


decoder = msgspec.json.Decoder(dt.timedelta, dec_hook=dec_hook)
```

______________________________________________________________________

### 4.5 `msgspec.Raw` for zero-copy

```python
class Model(msgspec.Struct):
    dimensions: int
    point: msgspec.Raw  # zero-copy view into buffer


model = decoder.decode(b'{"dimensions": 2, "point": {"x": 1, "y": 2}}')

# Decode point later based on dimensions
if model.dimensions == 2:
    pt = msgspec.json.decode(model.point, type=Point2D)
```

**Use case:** Control plane inspects metadata without touching heavy payloads.

______________________________________________________________________

### 4.6 View structs for partial decoding

```python
class FullEvent(msgspec.Struct):
    id: str
    ts: int
    payload: dict[str, object]
    debug_blob: bytes
    # ...many more fields...


class EventView(msgspec.Struct):
    id: str
    ts: int


decoder_view = msgspec.json.Decoder(EventView)
view = decoder_view.decode(large_json_bytes)  # Only id and ts decoded
```

______________________________________________________________________

## 5. Real-World Usage Patterns

### 5.1 AsyncIO TCP server pattern

```python
class Get(msgspec.Struct, tag=True):
    key: str


class Put(msgspec.Struct, tag=True):
    key: str
    val: str


Request = Get | Put


class Server:
    def __init__(self):
        self.encoder = msgspec.msgpack.Encoder()
        self.decoder = msgspec.msgpack.Decoder(Request)
        self.kv: dict[str, str] = {}

    async def handle_connection(self, r, w):
        while True:
            buf = await prefixed_recv(r)
            req = self.decoder.decode(buf)
            resp = await self.handle_request(req)
            out = self.encoder.encode(resp)
            await prefixed_send(w, out)
```

### 5.2 FastAPI integration

```python
import msgspec
from fastapi import FastAPI


class User(msgspec.Struct):
    name: str
    email: str
    age: int | None = None


app = FastAPI()


@app.post('/users/', response_model=User)
def create_user(user: User) -> User:
    return user
```

### 5.3 Kafka integration

```python
class Event(msgspec.Struct, tag=True, array_like=True, frozen=True, gc=False):
    source: str
    type: Literal['created', 'updated', 'deleted']
    payload: msgspec.Raw


encoder = msgspec.msgpack.Encoder()
decoder = msgspec.msgpack.Decoder(Event)


async def produce():
    event = Event('worker-1', 'created', payload=msgspec.Raw(b'...'))
    await producer.send_and_wait('events', encoder.encode(event))
```

### 5.4 Configuration patterns

```python
class RayConfig(msgspec.Struct):
    namespace: str = 'klaw'
    max_concurrency: int = 64


class KlawConfig(msgspec.Struct):
    ray: RayConfig = RayConfig()
    channel_default_capacity: int = 1024


def load_config(path: str) -> KlawConfig:
    with open(path, 'rb') as f:
        return msgspec.toml.decode(f.read(), type=KlawConfig, strict=False)
```

______________________________________________________________________

## 6. Ray-Specific Patterns for klaw-core

### 6.1 High-throughput worker pattern

```python
# Per-worker, module-level
data_encoder = msgspec.msgpack.Encoder()
data_decoder = msgspec.msgpack.Decoder(ChannelEnvelope)


def process_loop(channel):
    while True:
        buf = channel.recv_bytes()
        msg = data_decoder.decode(buf)
        match msg.tag:
            case 'data':
                handle_data(msg.payload)
            case 'heartbeat':
                handle_heartbeat(msg)
            case 'control':
                handle_control(msg)
```

### 6.2 Channel message structs

```python
from enum import StrEnum
from typing import Generic, TypeVar
import msgspec

T = TypeVar('T')


class ChannelType(StrEnum):
    MPMC = 'mpmc'
    BROADCAST = 'broadcast'
    WATCH = 'watch'
    ONESHOT = 'oneshot'


class ReaderInfo(msgspec.Struct, frozen=True, gc=False):
    reader_id: str
    node_id: str
    registered_at: datetime
    last_seen_at: datetime
    total_received: int


class SingleResult(msgspec.Struct, Generic[T], frozen=True, gc=False):
    status: str
    value: T | None = None


class BatchResult(msgspec.Struct, Generic[T], frozen=True, gc=False):
    status: str
    items: tuple[T, ...] = ()


class ChannelMetadata(msgspec.Struct, frozen=True, gc=False):
    channel_type: ChannelType
    capacity: int | None
    unbounded: bool
    value_type: str | None = None
```

### 6.3 Tagged envelope for channels

```python
class DataMessage(msgspec.Struct, tag='data', array_like=True, frozen=True, gc=False):
    channel: str
    seq: int
    payload: msgspec.Raw


class ControlMessage(msgspec.Struct, tag='ctrl', array_like=True, frozen=True, gc=False):
    kind: str
    metadata: ChannelMetadata


ChannelEnvelope = DataMessage | ControlMessage
```

______________________________________________________________________

## 7. Configuration Reference

### Struct Options

| Option                  | Type              | Default | Effect                                      |
| ----------------------- | ----------------- | ------- | ------------------------------------------- |
| `frozen`                | bool              | `False` | Immutable instances, adds `__hash__`        |
| `order`                 | bool              | `False` | Generates ordering methods (`__lt__`, etc.) |
| `eq`                    | bool              | `True`  | Generates `__eq__`                          |
| `kw_only`               | bool              | `False` | All fields keyword-only                     |
| `omit_defaults`         | bool              | `False` | Omit default-valued fields when encoding    |
| `forbid_unknown_fields` | bool              | `False` | Error on unknown fields during decode       |
| `tag`                   | str/bool/None     | `None`  | Enable tagged unions                        |
| `tag_field`             | str/None          | `None`  | Field name for tag (default `"type"`)       |
| `rename`                | str/callable/None | `None`  | Rename fields (`"camel"`, `"kebab"`, etc.)  |
| `array_like`            | bool              | `False` | Encode as arrays (~2× faster)               |
| `gc`                    | bool              | `True`  | GC tracking (set `False` for performance)   |
| `weakref`               | bool              | `False` | Support weak references                     |
| `dict`                  | bool              | `False` | Allow extra attributes via `__dict__`       |
| `cache_hash`            | bool              | `False` | Cache hash for frozen structs               |

### Field Options (`msgspec.field`)

| Option            | Type              | Effect                               |
| ----------------- | ----------------- | ------------------------------------ |
| `default`         | any               | Static default value                 |
| `default_factory` | `Callable[[], T]` | Factory for mutable/dynamic defaults |
| `name`            | str/None          | Per-field encoded name override      |

______________________________________________________________________

## 8. References

### Core Documentation

- [msgspec docs](https://jcristharif.com/msgspec/)
- [Structs](https://jcristharif.com/msgspec/structs.html)
- [Usage (encoders/decoders)](https://jcristharif.com/msgspec/usage.html)
- [Performance tips](https://jcristharif.com/msgspec/perf-tips.html)
- [Benchmarks](https://jcristharif.com/msgspec/benchmarks.html)
- [Supported types](https://jcristharif.com/msgspec/supported-types.html)
- [Constraints](https://jcristharif.com/msgspec/constraints.html)
- [API reference](https://jcristharif.com/msgspec/api.html)

### Examples

- [AsyncIO TCP KV server](https://jcristharif.com/msgspec/examples/asyncio-kv.html)
- [GeoJSON (tagged unions)](https://jcristharif.com/msgspec/examples/geojson.html)
- [Conda repodata (view structs)](https://jcristharif.com/msgspec/examples/conda-repodata.html)

### Production Usage

- [msgspec GitHub](https://github.com/jcrist/msgspec) (3.4k+ stars)
- [fastapi-msgspec](https://github.com/iurii-skorniakov/fastapi-msgspec)
- [msgspec-ext (settings library)](https://github.com/msgflux/msgspec-ext)

### Comparison

- [Pydantic docs](https://docs.pydantic.dev/latest/)
- [Pydantic mypy plugin](https://docs.pydantic.dev/latest/integrations/mypy/)

______________________________________________________________________

**This guide should be treated as the baseline for all new schemas and wire formats in klaw-core.**

When in doubt, prefer:

- `msgspec.Struct` with `frozen=True`, `gc=False` for metadata
- Tagged unions + `array_like=True` for polymorphic, high-throughput channels
- Typed decoders with `strict=True` at network boundaries
