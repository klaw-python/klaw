# PRD: msgspec Optimization & Wire Protocol Implementation

> **PRD Number:** 0005
> **Feature Name:** msgspec-optimization
> **Created:** 2024-12-19
> **Status:** Draft
> **Related Documents:**
>
> - [oracle-msgspec-guide.md](./oracle-msgspec-guide.md) - Comprehensive msgspec best practices
> - [oracle-msgspec-recommendations.md](./oracle-msgspec-recommendations.md) - Actionable implementation plan
> - [Previous Thread](https://ampcode.com/threads/T-019b391f-31b8-751c-8b76-64eccf080f37) - Initial analysis discussion

______________________________________________________________________

## 1. Introduction/Overview

### Problem Statement

klaw-core is building a Ray-based runtime/channels system as the foundation for a Dagster-like orchestrator. The current implementation uses msgspec correctly for basic structs (`Ok/Err`, `Some/Nothing`, error types, channel metadata), but lacks:

1. **Canonical wire protocol** - No standardized envelope for messages crossing process/network boundaries
1. **Encoder/decoder reuse** - Creating encoders per-call in hot paths wastes resources
1. **Type safety gaps** - `Any` leaks in `RayChannelActor`, missing variance on protocols
1. **Performance optimizations** - Not using `array_like=True`, no buffer pooling
1. **Constrained types** - No validation on resource-related fields (capacity, timeout, etc.)

### Solution

Implement all recommendations from the msgspec analysis to create a battery-included, scale-ready, future-proofed orchestrator foundation. This includes:

- Versioned wire protocol with tagged unions
- High-performance codec infrastructure
- Full type safety with variance annotations
- Constrained types for decode-time validation
- Comprehensive documentation and testing

### Why msgspec (Context)

Per [oracle-msgspec-guide.md §1](./oracle-msgspec-guide.md#1-executive-summary--why-msgspec-for-klaw-core):

| Aspect            | msgspec                      | Pydantic v2          |
| ----------------- | ---------------------------- | -------------------- |
| Static analysis   | Plugin-free (mypy + pyright) | Requires mypy plugin |
| Decode + validate | ~12× faster                  | Baseline             |
| Struct creation   | ~17× faster                  | Baseline             |
| Library size      | ~0.46 MiB                    | ~6.71 MiB            |
| Strict by default | ✅ Yes                       | ❌ Requires config   |

______________________________________________________________________

## 2. Goals

### Primary Goals

| ID  | Goal                         | Success Criteria                          | Priority |
| --- | ---------------------------- | ----------------------------------------- | -------- |
| G1  | Canonical wire protocol      | All channel messages use `WireEnvelope`   | Critical |
| G2  | High-performance codec       | Encoder/decoder reuse, buffer pooling     | Critical |
| G3  | Full type safety             | No `Any` leaks, variance annotations      | High     |
| G4  | Decode-time validation       | Constrained types catch misconfigurations | High     |
| G5  | Schema evolution support     | Versioned schemas, view structs           | Medium   |
| G6  | Comprehensive documentation  | User guide with examples                  | High     |
| G7  | Performance regression tests | Benchmark suite validates ~12× speedup    | High     |

### Measurable Outcomes

- **Throughput:** Match msgspec benchmarks (~12× faster than Pydantic v2 for JSON decode + validate)
- **Latency:** No allocation in hot paths (buffer reuse)
- **Type coverage:** Zero `Any` types in public APIs
- **Test coverage:** 100% on new modules, property-based tests for serialization

______________________________________________________________________

## 3. User Stories

### US-1: Channel Developer

> As a developer building channel implementations,
> I want a canonical wire format with typed encoders/decoders,
> So that I don't have to worry about serialization details in each channel type.

**Acceptance Criteria:**

- Single `WireEnvelope` type handles all message variants
- `CodecPool` provides thread-safe encoder/decoder access
- Type hints flow through to IDE completions

### US-2: Performance Engineer

> As a performance engineer optimizing throughput,
> I want zero-allocation encoding in hot paths,
> So that GC pauses don't impact message latency.

**Acceptance Criteria:**

- `BufferPool` provides reusable `bytearray` instances
- `encode_into()` writes directly to pre-allocated buffers
- Benchmarks show no allocations in steady-state

### US-3: Configuration Author

> As someone writing klaw configuration files,
> I want clear error messages when I misconfigure values,
> So that I catch mistakes at load time, not at runtime.

**Acceptance Criteria:**

- Invalid capacity (≤0) fails with clear message
- Invalid timeout fails with clear message
- Unknown fields in strict mode are rejected

### US-4: Static Analysis User

> As a developer using mypy/pyright,
> I want full type inference on channel operations,
> So that I catch type errors at edit time.

**Acceptance Criteria:**

- `Sender[T]` is contravariant (can accept subtypes)
- `Receiver[T]` is covariant (can yield subtypes)
- `RayChannelActor[T]` preserves type through generic

### US-5: New Contributor

> As a new contributor to klaw-core,
> I want comprehensive documentation on the wire protocol,
> So that I can understand how messages flow through the system.

**Acceptance Criteria:**

- `docs/user-guide/index.md` covers wire protocol basics
- Each message type has usage examples
- Links to msgspec docs for advanced topics

______________________________________________________________________

## 4. Functional Requirements

### Phase 1: Wire Protocol Foundation (Critical)

#### FR-1.1: Create `wire.py` module

**Location:** `klaw_core/runtime/channels/wire.py`

The module MUST define:

1. `WIRE_SCHEMA_VERSION: int = 1` - Schema version for evolution
1. `MessageKind(IntEnum)` - Discriminator values:
   - `DATA = 1`
   - `CONTROL = 2`
   - `HEARTBEAT = 3`
   - `ACK = 4`
   - `ERROR = 5`
1. `WireHeader` struct with:
   - `version: int` (default: `WIRE_SCHEMA_VERSION`)
   - `kind: MessageKind` (default: `DATA`)
   - `channel_id: str` (default: `""`)
   - `seq: int` (default: `0`)
   - `ts: int` (Unix timestamp millis, default: `0`)
   - Options: `array_like=True, frozen=True, gc=False`
1. `DataMessage[T]` struct with:
   - `header: WireHeader`
   - `payload: T`
   - Options: `tag=1, array_like=True, frozen=True, gc=False`
1. `ControlMessage` struct with:
   - `header: WireHeader`
   - `action: str` ("create", "close", "resize", "pause", "resume")
   - `metadata: msgspec.Raw` (default: `msgspec.Raw(b"")`)
   - Options: `tag=2, array_like=True, frozen=True, gc=False`
1. `Heartbeat` struct with:
   - `header: WireHeader`
   - `sender_id: str` (default: `""`)
   - Options: `tag=3, array_like=True, frozen=True, gc=False`
1. `Ack` struct with:
   - `header: WireHeader`
   - `acked_seq: int` (default: `0`)
   - `status: str` (default: `"ok"`)
   - Options: `tag=4, array_like=True, frozen=True, gc=False`
1. `WireError` struct with:
   - `header: WireHeader`
   - `code: str` (default: `""`)
   - `message: str` (default: `""`)
   - `details: msgspec.Raw` (default: `msgspec.Raw(b"")`)
   - Options: `tag=5, array_like=True, frozen=True, gc=False`
1. `WireEnvelope` type alias:
   ```python
   WireEnvelope = DataMessage[msgspec.Raw] | ControlMessage | Heartbeat | Ack | WireError
   ```

**Reference:** [oracle-msgspec-recommendations.md §1.1](./oracle-msgspec-recommendations.md#11-canonical-channel-envelope-critical)

#### FR-1.2: Create `codec.py` module

**Location:** `klaw_core/runtime/channels/codec.py`

The module MUST define:

1. `CodecPool` class with:
   - Thread-local encoder instances (`threading.local`)
   - Shared decoder for `WireEnvelope`
   - Methods:
     - `encode(msg: WireEnvelope) -> bytes`
     - `encode_into(msg: WireEnvelope, buf: bytearray, offset: int = 0) -> int`
     - `decode(buf: bytes | bytearray | memoryview) -> WireEnvelope`
     - `decode_payload[T](raw: msgspec.Raw, payload_type: type[T]) -> T`
1. `BufferPool` class with:
   - Pool of reusable `bytearray` instances
   - Thread-safe acquire/release
   - Configurable buffer size and pool limit
   - Methods:
     - `acquire() -> bytearray`
     - `release(buf: bytearray) -> None`
1. Module-level singleton:
   - `get_codec_pool() -> CodecPool`
   - `get_buffer_pool() -> BufferPool`
1. Convenience functions:
   - `encode(msg: WireEnvelope) -> bytes`
   - `decode(buf: bytes | bytearray | memoryview) -> WireEnvelope`

**Reference:** [oracle-msgspec-recommendations.md §1.2-1.3](./oracle-msgspec-recommendations.md#12-encoderdecoder-pool-critical)

#### FR-1.3: Create `types.py` module

**Location:** `klaw_core/runtime/types.py`

The module MUST define constrained type aliases:

1. `PositiveInt = Annotated[int, msgspec.Meta(gt=0)]`
1. `NonNegativeInt = Annotated[int, msgspec.Meta(ge=0)]`
1. `ChannelCapacity = Annotated[int, msgspec.Meta(ge=1, le=1_000_000)]`
1. `TimeoutSeconds = Annotated[float, msgspec.Meta(ge=0.0, le=86400.0)]`
1. `ConcurrencyLimit = Annotated[int, msgspec.Meta(ge=1, le=10_000)]`
1. `Identifier = Annotated[str, msgspec.Meta(min_length=1, max_length=255, pattern=r'^[a-zA-Z_][a-zA-Z0-9_-]*$')]`
1. `Namespace = Annotated[str, msgspec.Meta(min_length=1, max_length=63, pattern=r'^[a-z][a-z0-9-]*$')]`

**Reference:** [oracle-msgspec-recommendations.md §3](./oracle-msgspec-recommendations.md#3-constrained-types-critical)

______________________________________________________________________

### Phase 2: Type Safety (High)

#### FR-2.1: Update `protocols.py` with variance

**Location:** `klaw_core/runtime/channels/protocols.py`

Changes:

1. Define variance-annotated TypeVars:
   ```python
   T_co = TypeVar('T_co', covariant=True)
   T_contra = TypeVar('T_contra', contravariant=True)
   ```
1. Update `Sender[T_contra]` - contravariant (can accept subtypes)
1. Update `Receiver[T_co]` - covariant (can yield subtypes)
1. Update `ReferenceSender` and `ReferenceReceiver` accordingly

**Reference:** [oracle-msgspec-recommendations.md §4](./oracle-msgspec-recommendations.md#4-protocol-variance-high)

#### FR-2.2: Make `RayChannelActor` generic

**Location:** `klaw_core/runtime/channels/ray/actor.py`

Changes:

1. Add `Generic[T]` to class definition
1. Replace `Any` with `T` in method signatures:
   - `put(item: T, ...)`
   - `get(...) -> SingleResult[T]`
   - `get_nowait(...) -> SingleResult[T]`
   - `put_batch(items: tuple[T, ...], ...)`
   - `get_batch(...) -> BatchResult[T]`
1. Create `_TypeValidator[T]` helper class:
   - Caches `msgspec.convert` call
   - Lazy initialization
   - Thread-safe

**Reference:** [oracle-msgspec-recommendations.md §5](./oracle-msgspec-recommendations.md#5-generic-raychennelactor-high)

#### FR-2.3: Update decorators with ParamSpec

**Location:** `klaw_core/decorators.py` (or appropriate module)

Changes:

1. Use `ParamSpec` for signature preservation:
   ```python
   P = ParamSpec('P')
   T = TypeVar('T')
   E = TypeVar('E')
   ```
1. Update `@result` decorator to preserve function signature
1. Ensure IDE/type-checker sees correct parameter types

**Reference:** [oracle-msgspec-recommendations.md §8](./oracle-msgspec-recommendations.md#8-paramspec-decorators-high)

#### FR-2.4: Document Result/Option as in-process only

**Location:** `klaw_core/result.py`, `klaw_core/option.py`

Add docstring note to module:

```python
"""Result type: Ok[T] | Err[E] for explicit error handling.

Note:
    Ok/Err are intended for in-process control flow and executor/task APIs.
    For channel/Ray wire messages, use domain-specific msgspec.Struct schemas
    or the WireEnvelope types from klaw_core.runtime.channels.wire.
    Do not expose Result directly over the wire.
"""
```

**Reference:** [oracle-msgspec-recommendations.md §6.1 Recommendation 1](./oracle-msgspec-recommendations.md)

______________________________________________________________________

### Phase 3: Future-Proofing (Medium)

#### FR-3.1: Create `schema.py` registry

**Location:** `klaw_core/runtime/channels/schema.py`

The module MUST define:

1. `SchemaRegistry` class with:
   - Version → decoder mapping
   - Methods:
     - `register(version: int, envelope_type: type) -> None`
     - `get_decoder(version: int) -> msgspec.msgpack.Decoder`
     - `decode(buf: bytes) -> WireEnvelope` (peeks version, routes to decoder)
1. Default registry with version 1 → `WireEnvelope`

**Reference:** [oracle-msgspec-recommendations.md §6](./oracle-msgspec-recommendations.md#6-schema-registry-medium)

#### FR-3.2: Create `views.py` for partial decoding

**Location:** `klaw_core/runtime/channels/views.py`

The module MUST define:

1. `EnvelopeView` - Minimal struct for routing:
   ```python
   class EnvelopeView(msgspec.Struct):
       header: WireHeader
   ```
1. `TaskEventView` - For control plane inspection:
   ```python
   class TaskEventView(msgspec.Struct):
       id: str
       ts: int
       kind: str
   ```

**Reference:** [oracle-msgspec-guide.md §4.6](./oracle-msgspec-guide.md#46-view-structs-for-partial-decoding)

#### FR-3.3: Update config system

**Location:** `klaw_core/runtime/config.py`

Changes:

1. Use msgspec.Struct for all config classes
1. Add `forbid_unknown_fields=True` for strict validation
1. Add `omit_defaults=True` for sparse serialization
1. Use constrained types from `types.py`
1. Implement environment variable overrides (`KLAW_*`)
1. Use `strict=False` at TOML decode boundary only

**Reference:** [oracle-msgspec-recommendations.md §7](./oracle-msgspec-recommendations.md#7-configuration-patterns-medium)

______________________________________________________________________

### Phase 4: Polish (Low)

#### FR-4.1: Flip `_ChannelActorState` to `gc=True`

**Location:** `klaw_core/runtime/channels/ray/actor.py`

Change:

```python
class _ChannelActorState(msgspec.Struct):  # Remove gc=False
    """Mutable internal state for RayChannelActor."""
```

**Rationale:** Long-lived, mutated state; GC savings negligible, safer without `gc=False`.

**Reference:** [oracle-msgspec-recommendations.md Recommendation 2](./oracle-msgspec-recommendations.md)

#### FR-4.2: Add explicit `Generic[T]` for older tools

**Location:** `klaw_core/result.py`, `klaw_core/option.py`

Add `Generic[T]` base class for compatibility with tools not yet PEP 695-aware:

```python
from typing import Generic, TypeVar

T = TypeVar('T')


class Ok(msgspec.Struct, Generic[T], frozen=True, gc=False):
    value: T
```

**Reference:** [oracle-msgspec-recommendations.md Recommendation 5](./oracle-msgspec-recommendations.md)

#### FR-4.3: Add `omit_defaults=True` to metadata structs

**Location:** `klaw_core/runtime/channels/ray/constants.py`

Update:

```python
class ChannelMetadata(msgspec.Struct, frozen=True, gc=False, omit_defaults=True): ...
```

**Reference:** [oracle-msgspec-recommendations.md Recommendation 12](./oracle-msgspec-recommendations.md)

______________________________________________________________________

### Phase 5: Testing

#### FR-5.1: Unit tests for wire protocol

**Location:** `tests/runtime/channels/test_wire.py`

Tests MUST cover:

1. Each message type roundtrip (encode → decode)
1. Tagged union dispatch (correct type returned)
1. `WireHeader` defaults
1. `msgspec.Raw` payload handling

#### FR-5.2: Unit tests for codec

**Location:** `tests/runtime/channels/test_codec.py`

Tests MUST cover:

1. `CodecPool` thread safety
1. `BufferPool` acquire/release
1. `encode_into` buffer writing
1. Multiple concurrent encoders

#### FR-5.3: Unit tests for constrained types

**Location:** `tests/runtime/test_types.py`

Tests MUST cover:

1. Valid values pass validation
1. Invalid values raise `ValidationError` with clear message
1. Boundary conditions (edge of range)

#### FR-5.4: Property-based tests (Hypothesis)

**Location:** `tests/runtime/channels/test_wire_properties.py`

Tests MUST cover:

1. Arbitrary `WireEnvelope` roundtrips
1. Schema version compatibility
1. Payload type preservation

#### FR-5.5: Performance regression tests

**Location:** `tests/benchmarks/test_msgspec_performance.py`

Tests MUST verify:

1. Encode/decode throughput ≥12× Pydantic v2 baseline
1. No allocations in `encode_into` path (use `tracemalloc`)
1. Buffer pool reduces GC pressure

#### FR-5.6: Integration tests

**Location:** `tests/runtime/channels/test_wire_integration.py`

Tests MUST cover:

1. Wire protocol through actual channels
1. Error struct ↔ exception roundtrip
1. Schema registry version routing

______________________________________________________________________

### Phase 6: Documentation

#### FR-6.1: Create user guide

**Location:** `docs/user-guide/index.md`

Structure:

```
docs/user-guide/
├── index.md              # Overview and navigation
├── wire-protocol.md      # WireEnvelope, message types
├── codec.md              # CodecPool, BufferPool usage
├── types.md              # Constrained types reference
├── channels.md           # Channel patterns with wire protocol
└── performance.md        # Optimization tips
```

#### FR-6.2: API reference

**Location:** Auto-generated from docstrings

All new modules MUST have:

1. Module-level docstring with overview
1. Class docstrings with usage examples
1. Method docstrings with Args/Returns/Raises

#### FR-6.3: Migration guide

**Location:** `docs/user-guide/migration.md`

Cover:

1. Updating from raw msgpack to `WireEnvelope`
1. Using constrained types
1. Integrating `CodecPool`

______________________________________________________________________

## 5. Non-Goals (Out of Scope)

| Item                              | Reason                                      |
| --------------------------------- | ------------------------------------------- |
| Cross-language wire compatibility | Focus on Python first; add Rust/Go later    |
| Schema migration tooling          | Manual versioning sufficient for v1         |
| Custom msgspec extensions         | Use standard msgspec APIs only              |
| Pydantic interop layer            | Clean break, no bridge needed               |
| Async encoder/decoder             | msgspec encode/decode is sync (fast enough) |
| Compression in wire format        | Add later if needed (separate concern)      |

______________________________________________________________________

## 6. Design Considerations

### 6.1 Wire Protocol Design

```
┌─────────────────────────────────────────────────────────────┐
│                      WireEnvelope                           │
├─────────────────────────────────────────────────────────────┤
│  tag (int) │ discriminates message type (1-5)               │
├────────────┼────────────────────────────────────────────────┤
│  header    │ WireHeader [version, kind, channel_id, seq, ts]│
├────────────┼────────────────────────────────────────────────┤
│  payload   │ Variant-specific data                          │
│            │ - DataMessage: T (user payload)                │
│            │ - ControlMessage: action + metadata            │
│            │ - Heartbeat: sender_id                         │
│            │ - Ack: acked_seq + status                      │
│            │ - WireError: code + message + details          │
└────────────┴────────────────────────────────────────────────┘
```

**Why integer tags?**

- Faster than string comparison
- Smaller wire size
- Cross-language friendly

**Why `array_like=True`?**

- ~2× decode speedup
- Positional encoding (smaller)
- Per [msgspec docs](https://jcristharif.com/msgspec/structs.html#array-like-encoding)

### 6.2 Codec Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       CodecPool                             │
├─────────────────────────────────────────────────────────────┤
│  _local (threading.local)                                   │
│    └── encoder: msgspec.msgpack.Encoder  (per-thread)       │
│                                                             │
│  _envelope_decoder: msgspec.msgpack.Decoder[WireEnvelope]   │
│    └── shared, thread-safe (decode is reentrant)            │
├─────────────────────────────────────────────────────────────┤
│  encode(msg) → bytes                                        │
│  encode_into(msg, buf, offset) → int                        │
│  decode(buf) → WireEnvelope                                 │
│  decode_payload[T](raw, type) → T                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                       BufferPool                            │
├─────────────────────────────────────────────────────────────┤
│  _pool: list[bytearray]  (free buffers)                     │
│  _lock: threading.Lock                                      │
│  _buffer_size: int (default 4096)                           │
│  _max_pool: int (default 64)                                │
├─────────────────────────────────────────────────────────────┤
│  acquire() → bytearray                                      │
│  release(buf) → None                                        │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 File Structure

```
klaw_core/
├── runtime/
│   ├── types.py              # NEW: Constrained type aliases
│   ├── config.py             # UPDATED: msgspec-based config
│   └── channels/
│       ├── wire.py           # NEW: Wire protocol types
│       ├── codec.py          # NEW: Encoder/decoder pools
│       ├── schema.py         # NEW: Schema registry
│       ├── views.py          # NEW: Partial decoding views
│       ├── protocols.py      # UPDATED: Variance annotations
│       └── ray/
│           ├── actor.py      # UPDATED: Generic[T]
│           └── constants.py  # UPDATED: omit_defaults
├── result.py                 # UPDATED: Docstring, Generic[T]
├── option.py                 # UPDATED: Docstring, Generic[T]
└── decorators.py             # UPDATED: ParamSpec
```

______________________________________________________________________

## 7. Technical Considerations

### 7.1 Dependencies

| Dependency         | Version | Purpose                |
| ------------------ | ------- | ---------------------- |
| `msgspec`          | ≥0.18.0 | Core serialization     |
| `hypothesis`       | ≥6.0.0  | Property-based testing |
| `pytest-benchmark` | ≥4.0.0  | Performance regression |

### 7.2 Compatibility

- **Python:** 3.12+ (uses PEP 695 generics)
- **mypy:** 1.0+ (full `@dataclass_transform` support)
- **pyright:** 1.1.300+ (full `@dataclass_transform` support)
- **Ray:** 2.0+ (for distributed channels)

### 7.3 Performance Constraints

Per [msgspec benchmarks](https://jcristharif.com/msgspec/benchmarks.html):

| Operation              | Target                       | Baseline (Pydantic v2) |
| ---------------------- | ---------------------------- | ---------------------- |
| JSON decode + validate | ~12× faster                  | 1×                     |
| Struct creation        | ~17× faster                  | 1×                     |
| MessagePack decode     | ~2× faster with `array_like` | without                |

### 7.4 Thread Safety

- `Encoder` is NOT thread-safe → use thread-local instances
- `Decoder` IS thread-safe (reentrant) → can share
- `BufferPool` must be thread-safe → use locks

### 7.5 Integration Points

| Component              | Integration                              |
| ---------------------- | ---------------------------------------- |
| `RayChannelActor`      | Use `CodecPool` for all serialization    |
| `LocalSender/Receiver` | No change (in-process, no serialization) |
| `Executor`             | Wire protocol for Ray backend            |
| Config loading         | `msgspec.toml.decode(..., strict=False)` |

______________________________________________________________________

## 8. Success Metrics

| Metric            | Target           | Measurement        |
| ----------------- | ---------------- | ------------------ |
| Decode throughput | ≥12× Pydantic v2 | `pytest-benchmark` |
| Encode throughput | ≥10× Pydantic v2 | `pytest-benchmark` |
| Zero-alloc encode | 0 allocations    | `tracemalloc`      |
| Type coverage     | 100% public APIs | `mypy --strict`    |
| Test coverage     | ≥90% new code    | `pytest-cov`       |
| Doc coverage      | 100% public APIs | Manual review      |

______________________________________________________________________

## 9. Open Questions

| ID  | Question                                                        | Status                              | Owner |
| --- | --------------------------------------------------------------- | ----------------------------------- | ----- |
| Q1  | Should `WireEnvelope` use `tag_field="type"` or positional tag? | Decided: positional (int tag)       | -     |
| Q2  | Max buffer size for `BufferPool`?                               | Proposed: 4KB default, configurable | -     |
| Q3  | Schema registry persistence format?                             | Open: in-memory only for v1         | -     |
| Q4  | Should constrained types be re-exported from `klaw_core`?       | Open                                | -     |
| Q5  | Hypothesis strategy for `msgspec.Raw`?                          | Open: use `st.binary()`             | -     |

______________________________________________________________________

## 10. References

### Internal Documents

- [oracle-msgspec-guide.md](./oracle-msgspec-guide.md) - Comprehensive msgspec best practices
- [oracle-msgspec-recommendations.md](./oracle-msgspec-recommendations.md) - Actionable implementation plan
- [0004-prd-ray-channels.md](./0004-prd-ray-channels.md) - Ray channels PRD (context)

### External Resources

- [msgspec Documentation](https://jcristharif.com/msgspec/)
- [msgspec Structs](https://jcristharif.com/msgspec/structs.html)
- [msgspec Performance Tips](https://jcristharif.com/msgspec/perf-tips.html)
- [msgspec Benchmarks](https://jcristharif.com/msgspec/benchmarks.html)
- [msgspec Constraints](https://jcristharif.com/msgspec/constraints.html)
- [msgspec Supported Types](https://jcristharif.com/msgspec/supported-types.html)
- [PEP 681 - @dataclass_transform](https://peps.python.org/pep-0681/)
- [PEP 561 - py.typed](https://peps.python.org/pep-0561/)
- [PEP 695 - Type Parameter Syntax](https://peps.python.org/pep-0695/)

### Existing Code

- [`result.py`](../workspaces/python/klaw-core/src/klaw_core/result.py) - Current Ok/Err implementation
- [`option.py`](../workspaces/python/klaw-core/src/klaw_core/option.py) - Current Some/Nothing implementation
- [`errors.py`](../workspaces/python/klaw-core/src/klaw_core/runtime/errors.py) - Dual struct+exception pattern
- [`actor.py`](../workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/actor.py) - RayChannelActor
- [`protocols.py`](../workspaces/python/klaw-core/src/klaw_core/runtime/channels/protocols.py) - Sender/Receiver protocols
- [`constants.py`](../workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/constants.py) - Channel structs

______________________________________________________________________

## 11. Implementation Phases

| Phase | Items                                        | Effort       | Dependencies |
| ----- | -------------------------------------------- | ------------ | ------------ |
| 1     | Wire Protocol (FR-1.1, FR-1.2, FR-1.3)       | L (1-2 days) | None         |
| 2     | Type Safety (FR-2.1, FR-2.2, FR-2.3, FR-2.4) | M (1 day)    | Phase 1      |
| 3     | Future-Proofing (FR-3.1, FR-3.2, FR-3.3)     | M (1 day)    | Phase 1      |
| 4     | Polish (FR-4.1, FR-4.2, FR-4.3)              | S (0.5 day)  | Phase 2      |
| 5     | Testing (FR-5.1 - FR-5.6)                    | L (1-2 days) | All above    |
| 6     | Documentation (FR-6.1, FR-6.2, FR-6.3)       | M (1 day)    | All above    |

**Total Estimated Effort:** 5-7 days

______________________________________________________________________

## Appendix A: Existing msgspec Patterns

Current codebase already follows these msgspec best practices:

1. **`frozen=True, gc=False` on immutable metadata**

   ```python
   class ReaderInfo(msgspec.Struct, frozen=True, gc=False):
       reader_id: str
       ...
   ```

1. **Generics with msgspec.Struct**

   ```python
   class SingleResult(msgspec.Struct, Generic[T], frozen=True, gc=False):
       status: str
       value: T | None = None
   ```

1. **Dual struct + exception pattern**

   ```python
   class ChannelClosed(msgspec.Struct, frozen=True, gc=False):
       reason: str | None = None

       def to_exception(self) -> ChannelClosedError: ...


   class ChannelClosedError(Exception):
       def to_struct(self) -> ChannelClosed: ...
   ```

______________________________________________________________________

## Appendix B: Code Examples

### Wire Protocol Usage

```python
from klaw_core.runtime.channels.wire import DataMessage, ControlMessage, WireHeader, WireEnvelope
from klaw_core.runtime.channels.codec import get_codec_pool
import msgspec

# Create a data message
header = WireHeader(channel_id='my-channel', seq=1, ts=1703001234567)
msg = DataMessage(header=header, payload=msgspec.Raw(b'{"key": "value"}'))

# Encode/decode via pool
pool = get_codec_pool()
encoded = pool.encode(msg)
decoded = pool.decode(encoded)

# Dispatch on type
match decoded:
    case DataMessage(header=h, payload=p):
        print(f'Data on {h.channel_id}: {p}')
    case ControlMessage(header=h, action=a):
        print(f'Control: {a}')
    case Heartbeat(sender_id=s):
        print(f'Heartbeat from {s}')
```

### Constrained Types Usage

```python
from klaw_core.runtime.types import ChannelCapacity, TimeoutSeconds
import msgspec


class ChannelConfig(msgspec.Struct):
    capacity: ChannelCapacity  # Must be 1-1,000,000
    timeout: TimeoutSeconds  # Must be 0-86400


# Valid
config = msgspec.json.decode(b'{"capacity": 100, "timeout": 30.0}', type=ChannelConfig)

# Invalid - raises ValidationError
msgspec.json.decode(
    b'{"capacity": 0, "timeout": 30.0}',  # capacity must be >= 1
    type=ChannelConfig,
)
```
