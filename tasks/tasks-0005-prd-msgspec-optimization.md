# Task List: msgspec Optimization & Wire Protocol Implementation

> **PRD:** [0005-prd-msgspec-optimization.md](./0005-prd-msgspec-optimization.md)
> **Guide:** [oracle-msgspec-guide.md](./oracle-msgspec-guide.md)
> **Recommendations:** [oracle-msgspec-recommendations.md](./oracle-msgspec-recommendations.md)
> **Generated:** 2024-12-19

______________________________________________________________________

## Relevant Files

### New Files to Create

| File                                              | Description                                                   |
| ------------------------------------------------- | ------------------------------------------------------------- |
| `klaw_core/runtime/channels/wire.py`              | Wire protocol message types (WireEnvelope, DataMessage, etc.) |
| `klaw_core/runtime/channels/codec.py`             | CodecPool and BufferPool for encoding/decoding                |
| `klaw_core/runtime/types.py`                      | Constrained type aliases (PositiveInt, ChannelCapacity, etc.) |
| `klaw_core/runtime/channels/schema.py`            | Schema registry for version evolution                         |
| `klaw_core/runtime/channels/views.py`             | View structs for partial decoding                             |
| `klaw_core/runtime/config.py`                     | New msgspec-based config (replaces `_config.py`)              |
| `tests/runtime/channels/test_wire.py`             | Unit tests for wire protocol                                  |
| `tests/runtime/channels/test_codec.py`            | Unit tests for codec infrastructure                           |
| `tests/runtime/test_types.py`                     | Unit tests for constrained types                              |
| `tests/runtime/channels/test_schema.py`           | Unit tests for schema registry                                |
| `tests/runtime/channels/test_views.py`            | Unit tests for view structs                                   |
| `tests/runtime/channels/test_wire_properties.py`  | Property-based tests (Hypothesis)                             |
| `tests/benchmarks/test_msgspec_performance.py`    | Performance regression benchmarks                             |
| `tests/runtime/channels/test_wire_integration.py` | Integration tests                                             |
| `docs/user-guide/index.md`                        | User guide entry point                                        |
| `docs/user-guide/wire-protocol.md`                | Wire protocol documentation                                   |
| `docs/user-guide/codec.md`                        | Codec usage documentation                                     |
| `docs/user-guide/types.md`                        | Constrained types reference                                   |
| `docs/user-guide/channels.md`                     | Channel patterns with wire protocol                           |
| `docs/user-guide/performance.md`                  | Performance optimization tips                                 |

### Existing Files to Modify

| File                                          | Description                               |
| --------------------------------------------- | ----------------------------------------- |
| `klaw_core/runtime/channels/protocols.py`     | Add variance annotations to TypeVars      |
| `klaw_core/runtime/channels/ray/actor.py`     | Make generic, add `_TypeValidator`        |
| `klaw_core/runtime/channels/ray/constants.py` | Add `omit_defaults=True`                  |
| `klaw_core/result.py`                         | Add docstring note, explicit `Generic[T]` |
| `klaw_core/option.py`                         | Add docstring note, explicit `Generic[T]` |
| `klaw_core/runtime/_config.py`                | Migrate to msgspec (or replace)           |
| `klaw_core/runtime/errors.py`                 | Add roundtrip tests                       |
| `tests/strategies.py`                         | Add msgspec strategies for Hypothesis     |

### Notes

- Tests should be placed in the `tests/` directory mirroring `src/` structure
- Run tests with: `uv run pytest tests/ -v`
- Run specific test file: `uv run pytest tests/runtime/channels/test_wire.py -v`
- Run benchmarks: `uv run pytest tests/benchmarks/ --benchmark-only`
- Type check: `uv run mypy src/klaw_core/`

______________________________________________________________________

## Tasks

### Phase 1: Wire Protocol Foundation (Critical)

- [x] **1.0 Create Wire Protocol Message Types (`wire.py`) + Unit Tests**

  > **PRD Ref:** [FR-1.1](./0005-prd-msgspec-optimization.md#fr-11-create-wirepy-module)
  > **Guide Ref:** [§6.2-6.3](./oracle-msgspec-guide.md#62-channel-message-structs), [§4.1](./oracle-msgspec-guide.md#41-tagged-unions-for-polymorphism)
  > **Recommendations Ref:** [§1.1](./oracle-msgspec-recommendations.md#11-canonical-channel-envelope-critical)

  - [x] 1.1 Create `klaw_core/runtime/channels/wire.py` file with module docstring

    - [x] 1.1.1 Add module-level docstring explaining wire protocol purpose
    - [x] 1.1.2 Add imports: `msgspec`, `enum`, `typing`, `__future__.annotations`
    - [x] 1.1.3 Define `__all__` exports list

  - [x] 1.2 Define `WIRE_SCHEMA_VERSION` constant

    - [x] 1.2.1 Set `WIRE_SCHEMA_VERSION: int = 1`
    - [x] 1.2.2 Add docstring explaining versioning strategy

  - [x] 1.3 Create `MessageKind` enum

    - [x] 1.3.1 Define as `IntEnum` (not `StrEnum`) for compact encoding
    - [x] 1.3.2 Add variants: `DATA = 1`, `CONTROL = 2`, `HEARTBEAT = 3`, `ACK = 4`, `ERROR = 5`
    - [x] 1.3.3 Add class docstring explaining discriminator purpose

  - [x] 1.4 Create `WireHeader` struct

    - [x] 1.4.1 Define with options: `array_like=True, frozen=True, gc=False`
    - [x] 1.4.2 Add field `version: int` with default `WIRE_SCHEMA_VERSION`
    - [x] 1.4.3 Add field `kind: MessageKind` with default `MessageKind.DATA`
    - [x] 1.4.4 Add field `channel_id: str` with default `""`
    - [x] 1.4.5 Add field `seq: int` with default `0`
    - [x] 1.4.6 Add field `ts: int` with default `0` (Unix timestamp millis)
    - [x] 1.4.7 Add class docstring with layout comment `[version, kind, channel_id, seq, ts]`

  - [x] 1.5 Create `DataMessage[T]` struct

    - [x] 1.5.1 Define as `Generic[T]` with options: `tag=1, array_like=True, frozen=True, gc=False`
    - [x] 1.5.2 Add field `header: WireHeader`
    - [x] 1.5.3 Add field `payload: T`
    - [x] 1.5.4 Add class docstring explaining data plane usage

  - [x] 1.6 Create `ControlMessage` struct

    - [x] 1.6.1 Define with options: `tag=2, array_like=True, frozen=True, gc=False`
    - [x] 1.6.2 Add field `header: WireHeader`
    - [x] 1.6.3 Add field `action: str` (valid values: "create", "close", "resize", "pause", "resume")
    - [x] 1.6.4 Add field `metadata: msgspec.Raw` with default `msgspec.Raw(b"")`
    - [x] 1.6.5 Add class docstring explaining control plane usage

  - [x] 1.7 Create `Heartbeat` struct

    - [x] 1.7.1 Define with options: `tag=3, array_like=True, frozen=True, gc=False`
    - [x] 1.7.2 Add field `header: WireHeader`
    - [x] 1.7.3 Add field `sender_id: str` with default `""`
    - [x] 1.7.4 Add class docstring explaining liveness probe purpose

  - [x] 1.8 Create `Ack` struct

    - [x] 1.8.1 Define with options: `tag=4, array_like=True, frozen=True, gc=False`
    - [x] 1.8.2 Add field `header: WireHeader`
    - [x] 1.8.3 Add field `acked_seq: int` with default `0`
    - [x] 1.8.4 Add field `status: str` with default `"ok"`
    - [x] 1.8.5 Add class docstring explaining reliable delivery acknowledgment

  - [x] 1.9 Create `WireError` struct

    - [x] 1.9.1 Define with options: `tag=5, array_like=True, frozen=True, gc=False`
    - [x] 1.9.2 Add field `header: WireHeader`
    - [x] 1.9.3 Add field `code: str` with default `""`
    - [x] 1.9.4 Add field `message: str` with default `""`
    - [x] 1.9.5 Add field `details: msgspec.Raw` with default `msgspec.Raw(b"")`
    - [x] 1.9.6 Add class docstring explaining error response format

  - [x] 1.10 Define `WireEnvelope` type alias

    - [x] 1.10.1 Create union: `WireEnvelope = DataMessage[msgspec.Raw] | ControlMessage | Heartbeat | Ack | WireError`
    - [x] 1.10.2 Add docstring explaining canonical envelope usage

  - [x] 1.11 Create unit tests (`tests/runtime/channels/test_wire.py`)

    - [x] 1.11.1 Create test file with imports and fixtures
    - [x] 1.11.2 Test `WireHeader` default values
    - [x] 1.11.3 Test `WireHeader` custom values
    - [x] 1.11.4 Test `DataMessage` creation and field access
    - [x] 1.11.5 Test `ControlMessage` creation with all action types
    - [x] 1.11.6 Test `Heartbeat` creation
    - [x] 1.11.7 Test `Ack` creation
    - [x] 1.11.8 Test `WireError` creation
    - [x] 1.11.9 Test `MessageKind` enum values
    - [x] 1.11.10 Test immutability (frozen) - assignment should raise
    - [x] 1.11.11 Test hashability (frozen structs are hashable)

  - [x] 1.12 Verify implementation

    - [x] 1.12.1 Run `uv run pytest tests/runtime/channels/test_wire.py -v` ✓ 30 passed
    - [x] 1.12.2 Run `uv run mypy src/klaw_core/runtime/channels/wire.py` ✓ no issues
    - [x] 1.12.3 Run `uv run ruff check src/klaw_core/runtime/channels/wire.py` ✓ all checks passed

______________________________________________________________________

- [x] **2.0 Create Codec Pool Infrastructure (`codec.py`) + Unit Tests**

  > **PRD Ref:** [FR-1.2](./0005-prd-msgspec-optimization.md#fr-12-create-codecpy-module)
  > **Guide Ref:** [§3.1](./oracle-msgspec-guide.md#31-encoder--decoder-reuse)
  > **Recommendations Ref:** [§1.2](./oracle-msgspec-recommendations.md#12-encoderdecoder-pool-critical)

  - [x] 2.1 Create `klaw_core/runtime/channels/codec.py` file with module docstring

    - [x] 2.1.1 Add module-level docstring explaining codec pool purpose
    - [x] 2.1.2 Add imports: `msgspec`, `threading`, `typing`
    - [x] 2.1.3 Import wire types from `wire.py`
    - [x] 2.1.4 Define `__all__` exports list

  - [x] 2.2 Create `CodecPool` class

    - [x] 2.2.1 Define `__slots__` for memory efficiency: `("_local", "_envelope_decoder")`
    - [x] 2.2.2 Implement `__init__` method
      - [x] 2.2.2.1 Initialize `_local = threading.local()`
      - [x] 2.2.2.2 Initialize `_envelope_decoder = msgspec.msgpack.Decoder(WireEnvelope)`
      - [x] 2.2.2.3 ~~Initialize `_lock`~~ (not needed - decoder is thread-safe)
    - [x] 2.2.3 Implement `_encoder` property (thread-local)
      - [x] 2.2.3.1 Check if `_local.encoder` exists
      - [x] 2.2.3.2 Create `msgspec.msgpack.Encoder()` if not
      - [x] 2.2.3.3 Return the encoder
    - [x] 2.2.4 Implement `encode(msg: WireEnvelope) -> bytes` method
      - [x] 2.2.4.1 Use `self._encoder.encode(msg)`
      - [x] 2.2.4.2 Add docstring with example
    - [x] 2.2.5 Implement `encode_into(msg: WireEnvelope, buf: bytearray, offset: int = 0) -> int` method
      - [x] 2.2.5.1 Use `self._encoder.encode_into(msg, buf, offset)`
      - [x] 2.2.5.2 Return bytes written (buffer is truncated)
      - [x] 2.2.5.3 Add docstring explaining zero-allocation usage
    - [x] 2.2.6 Implement `decode(buf: bytes | bytearray | memoryview) -> WireEnvelope` method
      - [x] 2.2.6.1 Use `self._envelope_decoder.decode(buf)`
      - [x] 2.2.6.2 Add docstring with example
    - [x] 2.2.7 Implement `decode_payload[T](raw: msgspec.Raw, payload_type: type[T]) -> T` method
      - [x] 2.2.7.1 Create typed decoder: `msgspec.msgpack.Decoder(payload_type)`
      - [x] 2.2.7.2 Decode and return
      - [x] 2.2.7.3 Add docstring explaining deferred payload decoding
    - [x] 2.2.8 Add class docstring with usage example

  - [x] 2.3 Create module-level singleton

    - [x] 2.3.1 Define `_codec_pool: CodecPool | None = None`
    - [x] 2.3.2 Define `_codec_pool_lock = threading.Lock()`
    - [x] 2.3.3 Implement `get_codec_pool() -> CodecPool` function
      - [x] 2.3.3.1 Use double-checked locking pattern
      - [x] 2.3.3.2 Return singleton instance
      - [x] 2.3.3.3 Add docstring

  - [x] 2.4 Create convenience functions

    - [x] 2.4.1 Implement `encode(msg: WireEnvelope) -> bytes`
    - [x] 2.4.2 Implement `decode(buf: bytes | bytearray | memoryview) -> WireEnvelope`
    - [x] 2.4.3 Add docstrings to both

  - [x] 2.5 Create unit tests (`tests/runtime/channels/test_codec.py`)

    - [x] 2.5.1 Create test file with imports and fixtures
    - [x] 2.5.2 Test `CodecPool` instantiation
    - [x] 2.5.3 Test `encode` returns bytes
    - [x] 2.5.4 Test `decode` returns correct type
    - [x] 2.5.5 Test encode/decode roundtrip for `DataMessage`
    - [x] 2.5.6 Test encode/decode roundtrip for `ControlMessage`
    - [x] 2.5.7 Test encode/decode roundtrip for `Heartbeat`
    - [x] 2.5.8 Test encode/decode roundtrip for `Ack`
    - [x] 2.5.9 Test encode/decode roundtrip for `WireError`
    - [x] 2.5.10 Test `encode_into` writes to buffer correctly
    - [x] 2.5.11 Test `encode_into` returns correct byte count
    - [x] 2.5.12 Test `decode_payload` with typed payload
    - [x] 2.5.13 Test `get_codec_pool` returns singleton
    - [x] 2.5.14 Test convenience `encode`/`decode` functions
    - [x] 2.5.15 Test thread safety with concurrent access (use `threading.Thread`)
    - [x] 2.5.16 Test `decode` from `bytes`, `bytearray`, `memoryview` inputs
    - [x] 2.5.17 Property-based tests with Hypothesis (10 tests, ~850 examples)

  - [x] 2.6 Verify implementation

    - [x] 2.6.1 Run `uv run pytest tests/runtime/channels/test_codec.py -v` ✓ 45 passed
    - [x] 2.6.2 Run `uv run mypy src/klaw_core/runtime/channels/codec.py` ✓ no issues
    - [x] 2.6.3 Run `uv run ruff check src/klaw_core/runtime/channels/codec.py` ✓ all checks passed

______________________________________________________________________

- [x] **3.0 Create Buffer Pool for Zero-Allocation Encoding + Unit Tests** ✓

  > **PRD Ref:** [FR-1.2](./0005-prd-msgspec-optimization.md#fr-12-create-codecpy-module)
  > **Guide Ref:** [§3.6](./oracle-msgspec-guide.md)
  > **Recommendations Ref:** [§1.3](./oracle-msgspec-recommendations.md#13-buffer-pool-for-high-throughput-critical)

  - [x] 3.1 Add `BufferPool` class to `codec.py` ✓

    - [x] 3.1.1 Define `__slots__`: `("_pool", "_lock", "_buffer_size", "_max_pool")` ✓
    - [x] 3.1.2 Implement `__init__(buffer_size: int = 4096, max_pool: int = 64)` ✓
      - [x] 3.1.2.1 Initialize `_pool: list[bytearray] = []` ✓
      - [x] 3.1.2.2 Initialize `_lock = threading.Lock()` ✓
      - [x] 3.1.2.3 Store `_buffer_size` and `_max_pool` ✓
    - [x] 3.1.3 Implement `acquire() -> bytearray` method ✓
      - [x] 3.1.3.1 Lock and pop from pool if available ✓
      - [x] 3.1.3.2 Clear the buffer before returning ✓
      - [x] 3.1.3.3 Create new `bytearray(_buffer_size)` if pool empty ✓
      - [x] 3.1.3.4 Add docstring ✓
    - [x] 3.1.4 Implement `release(buf: bytearray) -> None` method ✓
      - [x] 3.1.4.1 Lock and append to pool if under `_max_pool` ✓
      - [x] 3.1.4.2 Discard if pool is full ✓
      - [x] 3.1.4.3 Add docstring ✓
    - [x] 3.1.5 Add class docstring explaining zero-allocation pattern ✓

  - [x] 3.2 Create module-level buffer pool singleton ✓

    - [x] 3.2.1 Define `_buffer_pool: BufferPool | None = None` ✓
    - [x] 3.2.2 Define `_buffer_pool_lock = threading.Lock()` ✓
    - [x] 3.2.3 Implement `get_buffer_pool() -> BufferPool` function ✓

  - [x] 3.3 Add unit tests for `BufferPool` to `test_codec.py` ✓ (53 tests total)

    - [x] 3.3.1 Test `BufferPool` instantiation with defaults ✓
    - [x] 3.3.2 Test `BufferPool` instantiation with custom sizes ✓
    - [x] 3.3.3 Test `acquire` returns `bytearray` of correct size ✓
    - [x] 3.3.4 Test `acquire` returns cleared buffer (not stale data) ✓
    - [x] 3.3.5 Test `release` and re-acquire returns same buffer ✓
    - [x] 3.3.6 Test pool respects `max_pool` limit ✓
    - [x] 3.3.7 Test `get_buffer_pool` returns singleton ✓
    - [x] 3.3.8 Test thread safety with concurrent acquire/release ✓
    - [x] 3.3.9 Test integration: `encode_into` with pooled buffer ✓
    - [x] 3.3.10 Property-based tests (5 tests) ✓
    - [x] 3.3.11 Edge case tests (8 tests) ✓
    - [x] 3.3.12 Wire protocol property tests (6 tests) ✓
    - [x] 3.3.13 Robustness tests - unicode, null bytes, long strings (6 tests) ✓
    - [x] 3.3.14 Invariant tests - equality, hash, immutability (10 tests) ✓
    - [x] 3.3.15 Decoder reentrance test ✓
    - [x] 3.3.16 Memory safety tests (2 tests) ✓

  - [x] 3.4 Verify implementation ✓

    - [x] 3.4.1 Run `uv run pytest tests/runtime/channels/test_codec.py -v -k buffer` ✓ all passed
    - [x] 3.4.2 Run `uv run mypy src/klaw_core/runtime/channels/codec.py` ✓ no issues

______________________________________________________________________

- [x] **4.0 Create Constrained Type Aliases (`types.py`) + Unit Tests** ✓

  > **PRD Ref:** [FR-1.3](./0005-prd-msgspec-optimization.md#fr-13-create-typespy-module)
  > **Guide Ref:** [§4.2](./oracle-msgspec-guide.md#42-constraints-via-annotated)
  > **Recommendations Ref:** [§3](./oracle-msgspec-recommendations.md#3-constrained-types-critical)

  - [x] 4.1 Create `klaw_core/runtime/types.py` file ✓

    - [x] 4.1.1 Add module-level docstring explaining constrained types purpose ✓
    - [x] 4.1.2 Add imports: `msgspec`, `typing.Annotated` ✓
    - [x] 4.1.3 Define `__all__` exports list ✓

  - [x] 4.2 Define numeric constraints ✓

    - [x] 4.2.1 `PositiveInt = Annotated[int, msgspec.Meta(gt=0)]` ✓
    - [x] 4.2.2 `NonNegativeInt = Annotated[int, msgspec.Meta(ge=0)]` ✓
    - [x] 4.2.3 `ChannelCapacity = Annotated[int, msgspec.Meta(ge=1, le=1_000_000)]` ✓
    - [x] 4.2.4 `TimeoutSeconds = Annotated[float, msgspec.Meta(ge=0.0, le=86400.0)]` ✓
    - [x] 4.2.5 `ConcurrencyLimit = Annotated[int, msgspec.Meta(ge=1, le=10_000)]` ✓
    - [x] 4.2.6 Add docstrings to each explaining valid ranges ✓

  - [x] 4.3 Define string constraints ✓

    - [x] 4.3.1 `Identifier = Annotated[str, msgspec.Meta(min_length=1, max_length=255, pattern=r'^[a-zA-Z_][a-zA-Z0-9_-]*$')]` ✓
    - [x] 4.3.2 `Namespace = Annotated[str, msgspec.Meta(min_length=1, max_length=63, pattern=r'^[a-z][a-z0-9-]*$')]` ✓
    - [x] 4.3.3 Add docstrings with pattern explanation ✓

  - [x] 4.4 Create unit tests (`tests/runtime/test_types.py`) ✓ 58 tests

    - [x] 4.4.1 Create test file with imports ✓
    - [x] 4.4.2 Create helper struct for testing: `class TestConfig(msgspec.Struct): ...` ✓
    - [x] 4.4.3 Test `PositiveInt` accepts 1, 100, 1000000 ✓
    - [x] 4.4.4 Test `PositiveInt` rejects 0, -1 ✓
    - [x] 4.4.5 Test `NonNegativeInt` accepts 0, 1, 100 ✓
    - [x] 4.4.6 Test `NonNegativeInt` rejects -1 ✓
    - [x] 4.4.7 Test `ChannelCapacity` accepts 1, 500000, 1000000 ✓
    - [x] 4.4.8 Test `ChannelCapacity` rejects 0, 1000001 ✓
    - [x] 4.4.9 Test `TimeoutSeconds` accepts 0.0, 30.0, 86400.0 ✓
    - [x] 4.4.10 Test `TimeoutSeconds` rejects -1.0, 86401.0 ✓
    - [x] 4.4.11 Test `ConcurrencyLimit` accepts 1, 100, 10000 ✓
    - [x] 4.4.12 Test `ConcurrencyLimit` rejects 0, 10001 ✓
    - [x] 4.4.13 Test `Identifier` accepts "foo", "foo_bar", "Foo-123" ✓
    - [x] 4.4.14 Test `Identifier` rejects "", "123foo", "foo bar" ✓
    - [x] 4.4.15 Test `Namespace` accepts "klaw", "my-namespace" ✓
    - [x] 4.4.16 Test `Namespace` rejects "", "MyNamespace", "123ns" ✓
    - [x] 4.4.17 Test error messages are clear and actionable ✓

  - [x] 4.5 Verify implementation ✓

    - [x] 4.5.1 Run `uv run pytest tests/runtime/test_types.py -v` ✓ 58 passed
    - [x] 4.5.2 Run `uv run mypy src/klaw_core/runtime/types.py` ✓ no issues
    - [x] 4.5.3 Run `uv run ruff check src/klaw_core/runtime/types.py` ✓ all passed

______________________________________________________________________

### Phase 2: Type Safety (High)

- [ ] **5.0 Add Variance Annotations to Channel Protocols + Tests**

  > **PRD Ref:** [FR-2.1](./0005-prd-msgspec-optimization.md#fr-21-update-protocolspy-with-variance)
  > **Guide Ref:** [§2.1](./oracle-msgspec-guide.md#21-msgspec-vs-pydantic--typing-model)
  > **Recommendations Ref:** [§4](./oracle-msgspec-recommendations.md#4-protocol-variance-high)

  - [ ] 5.1 Update `protocols.py` TypeVars

    - [ ] 5.1.1 Add import: `from typing import TypeVar`
    - [ ] 5.1.2 Define `T_co = TypeVar('T_co', covariant=True)`
    - [ ] 5.1.3 Define `T_contra = TypeVar('T_contra', contravariant=True)`
    - [ ] 5.1.4 Add comment explaining variance choice

  - [ ] 5.2 Update `Sender` protocol

    - [ ] 5.2.1 Change `Sender[T]` to `Sender[T_contra]`
    - [ ] 5.2.2 Update all method signatures to use `T_contra`
    - [ ] 5.2.3 Update docstring explaining contravariance

  - [ ] 5.3 Update `Receiver` protocol

    - [ ] 5.3.1 Change `Receiver[T]` to `Receiver[T_co]`
    - [ ] 5.3.2 Update all method signatures to use `T_co`
    - [ ] 5.3.3 Update docstring explaining covariance

  - [ ] 5.4 Update `ReferenceSender` and `ReferenceReceiver`

    - [ ] 5.4.1 Update `ReferenceSender[T_contra]`
    - [ ] 5.4.2 Update `ReferenceReceiver[T_co]`

  - [ ] 5.5 Update tests in `test_channels_protocol.py`

    - [ ] 5.5.1 Add test for `Sender` contravariance
    - [ ] 5.5.2 Add test for `Receiver` covariance
    - [ ] 5.5.3 Verify existing tests still pass

  - [ ] 5.6 Verify implementation

    - [ ] 5.6.1 Run `uv run pytest tests/runtime/test_channels_protocol.py -v`
    - [ ] 5.6.2 Run `uv run mypy src/klaw_core/runtime/channels/protocols.py`
    - [ ] 5.6.3 Verify no type errors in dependent files

______________________________________________________________________

- [ ] **6.0 Make RayChannelActor Generic with Type Validation + Tests**

  > **PRD Ref:** [FR-2.2](./0005-prd-msgspec-optimization.md#fr-22-make-raychannelactor-generic)
  > **Guide Ref:** [§2.4](./oracle-msgspec-guide.md#24-generic-type-support)
  > **Recommendations Ref:** [§5](./oracle-msgspec-recommendations.md#5-generic-raychennelactor-high)

  - [ ] 6.1 Create `_TypeValidator` helper class

    - [ ] 6.1.1 Define class with `__slots__`: `("_type", "_convert_fn")`
    - [ ] 6.1.2 Implement `__init__(value_type: type[T] | None)`
      - [ ] 6.1.2.1 Store `_type = value_type`
      - [ ] 6.1.2.2 Initialize `_convert_fn = None` (lazy)
    - [ ] 6.1.3 Implement `validate(item: Any) -> bool` method
      - [ ] 6.1.3.1 Return `True` if `_type is None`
      - [ ] 6.1.3.2 Lazily create converter on first call
      - [ ] 6.1.3.3 Try `msgspec.convert(item, type=self._type)`
      - [ ] 6.1.3.4 Return `True` on success, `False` on `ValidationError`
    - [ ] 6.1.4 Add class docstring explaining caching benefit

  - [ ] 6.2 Update `RayChannelActor` class signature

    - [ ] 6.2.1 Add `from typing import Generic, TypeVar`
    - [ ] 6.2.2 Define `T = TypeVar('T')`
    - [ ] 6.2.3 Change class to `class RayChannelActor(Generic[T]):`
    - [ ] 6.2.4 Update `@ray.remote` decorator (stays the same)

  - [ ] 6.3 Update `__init__` method

    - [ ] 6.3.1 Change `value_type: Any = None` to `value_type: type[T] | None = None`
    - [ ] 6.3.2 Replace `self._validate_type` usage with `self._validator`
    - [ ] 6.3.3 Initialize `self._validator = _TypeValidator(value_type)`

  - [ ] 6.4 Update method signatures

    - [ ] 6.4.1 `put(self, item: T, ...)` - change `Any` to `T`
    - [ ] 6.4.2 `put_nowait(self, item: T)` - change `Any` to `T`
    - [ ] 6.4.3 `put_batch(self, items: tuple[T, ...], ...)` - change `Any` to `T`
    - [ ] 6.4.4 `get(...) -> SingleResult[T]` - change `Any` to `T`
    - [ ] 6.4.5 `get_nowait(...) -> SingleResult[T]` - change `Any` to `T`
    - [ ] 6.4.6 `get_batch(...) -> BatchResult[T]` - change `Any` to `T`

  - [ ] 6.5 Update `_validate_type` to use validator

    - [ ] 6.5.1 Replace method body with `return self._validator.validate(item)`
    - [ ] 6.5.2 Or remove method entirely and call validator directly

  - [ ] 6.6 Update `_ChannelActorState` (prepare for Task 11.0)

    - [ ] 6.6.1 Change `value_type: Any` to `value_type: type | None`

  - [ ] 6.7 Add/update tests

    - [ ] 6.7.1 Test `_TypeValidator` with `None` type (accepts all)
    - [ ] 6.7.2 Test `_TypeValidator` with `int` type
    - [ ] 6.7.3 Test `_TypeValidator` with `list[str]` type
    - [ ] 6.7.4 Test `_TypeValidator` caching (same result on repeated calls)
    - [ ] 6.7.5 Update existing actor tests to use typed actor

  - [ ] 6.8 Verify implementation

    - [ ] 6.8.1 Run `uv run pytest tests/runtime/channels/ -v -k actor`
    - [ ] 6.8.2 Run `uv run mypy src/klaw_core/runtime/channels/ray/actor.py`

______________________________________________________________________

- [ ] **7.0 Update Result/Option Documentation (In-Process Only)**

  > **PRD Ref:** [FR-2.4](./0005-prd-msgspec-optimization.md#fr-24-document-resultoption-as-in-process-only)
  > **Recommendations Ref:** [Recommendation 1](./oracle-msgspec-recommendations.md)

  - [ ] 7.1 Update `result.py` module docstring

    - [ ] 7.1.1 Add note about in-process usage
    - [ ] 7.1.2 Reference `WireEnvelope` for wire messages
    - [ ] 7.1.3 Explain why Result shouldn't cross wire boundaries

  - [ ] 7.2 Update `option.py` module docstring

    - [ ] 7.2.1 Add note about in-process usage
    - [ ] 7.2.2 Reference `WireEnvelope` for wire messages

  - [ ] 7.3 Verify documentation

    - [ ] 7.3.1 Review docstrings read correctly
    - [ ] 7.3.2 No code changes needed, just documentation

______________________________________________________________________

### Phase 3: Future-Proofing (Medium)

- [ ] **8.0 Create Schema Registry for Version Evolution + Unit Tests**

  > **PRD Ref:** [FR-3.1](./0005-prd-msgspec-optimization.md#fr-31-create-schemapy-registry)
  > **Guide Ref:** [§4.5](./oracle-msgspec-guide.md)
  > **Recommendations Ref:** [§6](./oracle-msgspec-recommendations.md#6-schema-registry-medium)

  - [ ] 8.1 Create `klaw_core/runtime/channels/schema.py` file

    - [ ] 8.1.1 Add module-level docstring
    - [ ] 8.1.2 Add imports: `msgspec`, `typing`
    - [ ] 8.1.3 Import `WireEnvelope`, `WIRE_SCHEMA_VERSION` from `wire.py`
    - [ ] 8.1.4 Define `__all__` exports

  - [ ] 8.2 Create `SchemaRegistry` class

    - [ ] 8.2.1 Define `__slots__`: `("_decoders", "_lock")`
    - [ ] 8.2.2 Implement `__init__()` with default version 1 registered
    - [ ] 8.2.3 Implement `register(version: int, envelope_type: type) -> None`
      - [ ] 8.2.3.1 Create decoder for type
      - [ ] 8.2.3.2 Store in `_decoders` dict
    - [ ] 8.2.4 Implement `get_decoder(version: int) -> msgspec.msgpack.Decoder`
      - [ ] 8.2.4.1 Look up decoder by version
      - [ ] 8.2.4.2 Raise `KeyError` if not found
    - [ ] 8.2.5 Implement `decode(buf: bytes) -> WireEnvelope`
      - [ ] 8.2.5.1 Peek version from buffer (first byte after tag)
      - [ ] 8.2.5.2 Route to appropriate decoder
      - [ ] 8.2.5.3 Handle unknown version gracefully
    - [ ] 8.2.6 Add class docstring with usage example

  - [ ] 8.3 Create default registry singleton

    - [ ] 8.3.1 `_default_registry: SchemaRegistry | None = None`
    - [ ] 8.3.2 Implement `get_schema_registry() -> SchemaRegistry`

  - [ ] 8.4 Create unit tests (`tests/runtime/channels/test_schema.py`)

    - [ ] 8.4.1 Test registry instantiation
    - [ ] 8.4.2 Test `register` adds decoder
    - [ ] 8.4.3 Test `get_decoder` returns correct decoder
    - [ ] 8.4.4 Test `get_decoder` raises for unknown version
    - [ ] 8.4.5 Test `decode` routes to correct version
    - [ ] 8.4.6 Test default registry has version 1

  - [ ] 8.5 Verify implementation

    - [ ] 8.5.1 Run `uv run pytest tests/runtime/channels/test_schema.py -v`
    - [ ] 8.5.2 Run `uv run mypy src/klaw_core/runtime/channels/schema.py`

______________________________________________________________________

- [ ] **9.0 Create View Structs for Partial Decoding + Unit Tests**

  > **PRD Ref:** [FR-3.2](./0005-prd-msgspec-optimization.md#fr-32-create-viewspy-for-partial-decoding)
  > **Guide Ref:** [§4.6](./oracle-msgspec-guide.md#46-view-structs-for-partial-decoding)
  > **Recommendations Ref:** [§6](./oracle-msgspec-recommendations.md)

  - [ ] 9.1 Create `klaw_core/runtime/channels/views.py` file

    - [ ] 9.1.1 Add module-level docstring explaining partial decoding
    - [ ] 9.1.2 Add imports
    - [ ] 9.1.3 Define `__all__` exports

  - [ ] 9.2 Create `EnvelopeView` struct

    - [ ] 9.2.1 Define with minimal fields for routing
    - [ ] 9.2.2 Include only `header: WireHeader`
    - [ ] 9.2.3 Add docstring explaining use case

  - [ ] 9.3 Create `TaskEventView` struct

    - [ ] 9.3.1 Define with fields: `id: str`, `ts: int`, `kind: str`
    - [ ] 9.3.2 Add docstring explaining control plane inspection

  - [ ] 9.4 Create view decoders

    - [ ] 9.4.1 `envelope_view_decoder = msgspec.msgpack.Decoder(EnvelopeView)`
    - [ ] 9.4.2 Add convenience function `decode_envelope_view(buf: bytes) -> EnvelopeView`

  - [ ] 9.5 Create unit tests (`tests/runtime/channels/test_views.py`)

    - [ ] 9.5.1 Test `EnvelopeView` decodes partial message
    - [ ] 9.5.2 Test `EnvelopeView` ignores extra fields
    - [ ] 9.5.3 Test `TaskEventView` creation
    - [ ] 9.5.4 Test view decoding is faster than full decode (optional benchmark)

  - [ ] 9.6 Verify implementation

    - [ ] 9.6.1 Run `uv run pytest tests/runtime/channels/test_views.py -v`
    - [ ] 9.6.2 Run `uv run mypy src/klaw_core/runtime/channels/views.py`

______________________________________________________________________

- [ ] **10.0 Migrate Config System to msgspec + Unit Tests**

  > **PRD Ref:** [FR-3.3](./0005-prd-msgspec-optimization.md#fr-33-update-config-system)
  > **Guide Ref:** [§5.4](./oracle-msgspec-guide.md#54-configuration-patterns)
  > **Recommendations Ref:** [§7](./oracle-msgspec-recommendations.md#7-configuration-patterns-medium)

  - [ ] 10.1 Create new `klaw_core/runtime/config.py` file

    - [ ] 10.1.1 Add module-level docstring
    - [ ] 10.1.2 Add imports: `msgspec`, `os`, `pathlib`
    - [ ] 10.1.3 Import constrained types from `types.py`

  - [ ] 10.2 Create `RayConfig` struct

    - [ ] 10.2.1 Define with `omit_defaults=True, forbid_unknown_fields=True`
    - [ ] 10.2.2 Add field `namespace: str` with default `"klaw"`
    - [ ] 10.2.3 Add field `address: str | None` with default `None`
    - [ ] 10.2.4 Add field `max_concurrency: ConcurrencyLimit` with default `64`

  - [ ] 10.3 Create `ChannelDefaults` struct

    - [ ] 10.3.1 Define with `omit_defaults=True, forbid_unknown_fields=True`
    - [ ] 10.3.2 Add field `capacity: ChannelCapacity` with default `1024`
    - [ ] 10.3.3 Add field `timeout: TimeoutSeconds` with default `30.0`

  - [ ] 10.4 Create `ExecutorConfig` struct

    - [ ] 10.4.1 Add field `max_workers: ConcurrencyLimit`
    - [ ] 10.4.2 Add field `task_timeout: TimeoutSeconds`

  - [ ] 10.5 Create `TelemetryConfig` struct

    - [ ] 10.5.1 Add field `enabled: bool` with default `True`
    - [ ] 10.5.2 Add field `metrics_port: int` with constraint `ge=1024, le=65535`
    - [ ] 10.5.3 Add field `trace_sample_rate: float` with constraint `ge=0.0, le=1.0`

  - [ ] 10.6 Create `KlawConfig` root struct

    - [ ] 10.6.1 Define with `omit_defaults=True, forbid_unknown_fields=True`
    - [ ] 10.6.2 Add field `ray: RayConfig` with `default_factory`
    - [ ] 10.6.3 Add field `channels: ChannelDefaults` with `default_factory`
    - [ ] 10.6.4 Add field `executor: ExecutorConfig` with `default_factory`
    - [ ] 10.6.5 Add field `telemetry: TelemetryConfig` with `default_factory`

  - [ ] 10.7 Implement `load_config(path: str | Path | None = None) -> KlawConfig`

    - [ ] 10.7.1 Check `KLAW_CONFIG` env var for path
    - [ ] 10.7.2 Use `msgspec.toml.decode(..., strict=False)` for file
    - [ ] 10.7.3 Return default `KlawConfig()` if file missing
    - [ ] 10.7.4 Call `_apply_env_overrides(config)`

  - [ ] 10.8 Implement `_apply_env_overrides(config: KlawConfig) -> KlawConfig`

    - [ ] 10.8.1 Check `KLAW_RAY_NAMESPACE` and override
    - [ ] 10.8.2 Check `KLAW_RAY_ADDRESS` and override
    - [ ] 10.8.3 Use `msgspec.structs.replace()` for immutable updates
    - [ ] 10.8.4 Add more overrides as needed

  - [ ] 10.9 Implement `save_config(config: KlawConfig, path: str | Path) -> None`

    - [ ] 10.9.1 Use `msgspec.toml.encode(config)`
    - [ ] 10.9.2 Write to file

  - [ ] 10.10 Update `_config.py` to use new config

    - [ ] 10.10.1 Import from new `config.py`
    - [ ] 10.10.2 Update `RuntimeConfig` to use msgspec structs
    - [ ] 10.10.3 Or deprecate `_config.py` in favor of `config.py`

  - [ ] 10.11 Create unit tests (`tests/runtime/test_config_msgspec.py`)

    - [ ] 10.11.1 Test `KlawConfig` default instantiation
    - [ ] 10.11.2 Test `load_config` from TOML file
    - [ ] 10.11.3 Test `load_config` with missing file returns defaults
    - [ ] 10.11.4 Test `_apply_env_overrides` overrides values
    - [ ] 10.11.5 Test `save_config` writes valid TOML
    - [ ] 10.11.6 Test `forbid_unknown_fields` rejects unknown keys
    - [ ] 10.11.7 Test constrained types reject invalid values
    - [ ] 10.11.8 Test `strict=False` allows string-to-int coercion in TOML

  - [ ] 10.12 Verify implementation

    - [ ] 10.12.1 Run `uv run pytest tests/runtime/test_config_msgspec.py -v`
    - [ ] 10.12.2 Run `uv run mypy src/klaw_core/runtime/config.py`

______________________________________________________________________

### Phase 4: Polish (Low)

- [ ] **11.0 Flip `_ChannelActorState` to `gc=True`**

  > **PRD Ref:** [FR-4.1](./0005-prd-msgspec-optimization.md#fr-41-flip-_channelactorstate-to-gctrue)
  > **Recommendations Ref:** [Recommendation 2](./oracle-msgspec-recommendations.md)

  - [ ] 11.1 Update `actor.py`

    - [ ] 11.1.1 Change `class _ChannelActorState(msgspec.Struct, gc=False):` to `class _ChannelActorState(msgspec.Struct):`
    - [ ] 11.1.2 Add comment explaining why `gc=True` (mutable, long-lived)

  - [ ] 11.2 Verify no test regressions

    - [ ] 11.2.1 Run `uv run pytest tests/runtime/channels/ray/ -v`

______________________________________________________________________

- [ ] **12.0 Add Explicit `Generic[T]` to Result/Option for Older Tools**

  > **PRD Ref:** [FR-4.2](./0005-prd-msgspec-optimization.md#fr-42-add-explicit-generict-for-older-tools)
  > **Recommendations Ref:** [Recommendation 5](./oracle-msgspec-recommendations.md)

  - [ ] 12.1 Update `result.py`

    - [ ] 12.1.1 Add `from typing import Generic, TypeVar`
    - [ ] 12.1.2 Define `T = TypeVar("T")` and `E = TypeVar("E")`
    - [ ] 12.1.3 Change `class Ok[T]` to `class Ok(msgspec.Struct, Generic[T], frozen=True, gc=False):`
    - [ ] 12.1.4 Change `class Err[E]` to `class Err(msgspec.Struct, Generic[E], frozen=True, gc=False):`
    - [ ] 12.1.5 Update type alias syntax if needed

  - [ ] 12.2 Update `option.py`

    - [ ] 12.2.1 Add `from typing import Generic, TypeVar`
    - [ ] 12.2.2 Define `T = TypeVar("T")`
    - [ ] 12.2.3 Change `class Some[T]` to `class Some(msgspec.Struct, Generic[T], frozen=True, gc=False):`

  - [ ] 12.3 Verify backward compatibility

    - [ ] 12.3.1 Run `uv run pytest tests/test_result.py tests/test_option.py -v`
    - [ ] 12.3.2 Run `uv run mypy src/klaw_core/result.py src/klaw_core/option.py`

______________________________________________________________________

- [ ] **13.0 Add `omit_defaults=True` to Metadata Structs**

  > **PRD Ref:** [FR-4.3](./0005-prd-msgspec-optimization.md#fr-43-add-omit_defaultstrue-to-metadata-structs)
  > **Recommendations Ref:** [Recommendation 12](./oracle-msgspec-recommendations.md)

  - [ ] 13.1 Update `constants.py`

    - [ ] 13.1.1 Add `omit_defaults=True` to `ReaderInfo`
    - [ ] 13.1.2 Add `omit_defaults=True` to `SingleResult`
    - [ ] 13.1.3 Add `omit_defaults=True` to `BatchResult`
    - [ ] 13.1.4 Add `omit_defaults=True` to `ChannelMetadata`

  - [ ] 13.2 Verify serialization still works

    - [ ] 13.2.1 Run existing channel tests
    - [ ] 13.2.2 Verify default values are omitted in encoded output

______________________________________________________________________

### Phase 5: Cross-Cutting Tests

- [ ] **14.0 Property-Based Tests with Hypothesis (Cross-Cutting)**

  > **PRD Ref:** [FR-5.4](./0005-prd-msgspec-optimization.md#fr-54-property-based-tests-hypothesis)
  > **External Ref:** [Hypothesis docs](https://hypothesis.readthedocs.io/)

  - [ ] 14.1 Update `tests/strategies.py`

    - [ ] 14.1.1 Add strategy for `WireHeader`
    - [ ] 14.1.2 Add strategy for `MessageKind`
    - [ ] 14.1.3 Add strategy for `DataMessage`
    - [ ] 14.1.4 Add strategy for `ControlMessage`
    - [ ] 14.1.5 Add strategy for `Heartbeat`
    - [ ] 14.1.6 Add strategy for `Ack`
    - [ ] 14.1.7 Add strategy for `WireError`
    - [ ] 14.1.8 Add strategy for `WireEnvelope` (union of above)
    - [ ] 14.1.9 Add strategy for `msgspec.Raw` using `st.binary()`

  - [ ] 14.2 Create `tests/runtime/channels/test_wire_properties.py`

    - [ ] 14.2.1 Test: Any `WireEnvelope` roundtrips correctly
    - [ ] 14.2.2 Test: Any `DataMessage` roundtrips with payload preserved
    - [ ] 14.2.3 Test: Schema version is preserved through roundtrip
    - [ ] 14.2.4 Test: `WireHeader` fields are preserved
    - [ ] 14.2.5 Test: Multiple encode/decode cycles are idempotent
    - [ ] 14.2.6 Test: Decoded type matches encoded type (tagged dispatch)

  - [ ] 14.3 Add property tests for constrained types

    - [ ] 14.3.1 Test: Valid `PositiveInt` values always pass
    - [ ] 14.3.2 Test: Invalid `PositiveInt` values always fail
    - [ ] 14.3.3 Test: Boundary conditions for all constrained types

  - [ ] 14.4 Verify property tests

    - [ ] 14.4.1 Run `uv run pytest tests/runtime/channels/test_wire_properties.py -v`
    - [ ] 14.4.2 Verify no flaky tests (run multiple times)

______________________________________________________________________

- [ ] **15.0 Performance Regression Benchmarks**

  > **PRD Ref:** [FR-5.5](./0005-prd-msgspec-optimization.md#fr-55-performance-regression-tests)
  > **External Ref:** [msgspec benchmarks](https://jcristharif.com/msgspec/benchmarks.html)

  - [ ] 15.1 Create `tests/benchmarks/` directory

    - [ ] 15.1.1 Create `tests/benchmarks/__init__.py`
    - [ ] 15.1.2 Create `tests/benchmarks/conftest.py` with benchmark fixtures

  - [ ] 15.2 Create `tests/benchmarks/test_msgspec_performance.py`

    - [ ] 15.2.1 Benchmark `WireEnvelope` encode throughput
    - [ ] 15.2.2 Benchmark `WireEnvelope` decode throughput
    - [ ] 15.2.3 Benchmark `DataMessage` encode/decode
    - [ ] 15.2.4 Benchmark `CodecPool` vs direct encoder creation
    - [ ] 15.2.5 Benchmark `BufferPool` acquire/release
    - [ ] 15.2.6 Benchmark `encode_into` vs `encode`

  - [ ] 15.3 Create Pydantic comparison baseline

    - [ ] 15.3.1 Create equivalent Pydantic models (for comparison only)
    - [ ] 15.3.2 Benchmark Pydantic encode/decode
    - [ ] 15.3.3 Add assertion: msgspec ≥12× faster than Pydantic

  - [ ] 15.4 Add memory allocation tests

    - [ ] 15.4.1 Use `tracemalloc` to measure allocations
    - [ ] 15.4.2 Test `encode_into` with pooled buffer has zero allocations
    - [ ] 15.4.3 Document memory profile

  - [ ] 15.5 Verify benchmarks

    - [ ] 15.5.1 Run `uv run pytest tests/benchmarks/ --benchmark-only`
    - [ ] 15.5.2 Generate benchmark report
    - [ ] 15.5.3 Verify performance targets met

______________________________________________________________________

- [ ] **16.0 Integration Tests: End-to-End Wire Protocol**

  > **PRD Ref:** [FR-5.6](./0005-prd-msgspec-optimization.md#fr-56-integration-tests)

  - [ ] 16.1 Create `tests/runtime/channels/test_wire_integration.py`

    - [ ] 16.1.1 Test wire protocol through local channel
    - [ ] 16.1.2 Test wire protocol encoding in channel factory
    - [ ] 16.1.3 Test `CodecPool` used correctly in channel operations

  - [ ] 16.2 Test error roundtrips

    - [ ] 16.2.1 Test `ChannelClosed` struct → exception → struct
    - [ ] 16.2.2 Test `ChannelFull` struct → exception → struct
    - [ ] 16.2.3 Test all error types in `errors.py`

  - [ ] 16.3 Test schema registry integration

    - [ ] 16.3.1 Test version routing with real messages
    - [ ] 16.3.2 Test unknown version handling

  - [ ] 16.4 Verify integration tests

    - [ ] 16.4.1 Run `uv run pytest tests/runtime/channels/test_wire_integration.py -v`

______________________________________________________________________

### Phase 6: Documentation

- [ ] **17.0 Create User Guide Structure (`docs/user-guide/`)**

  > **PRD Ref:** [FR-6.1](./0005-prd-msgspec-optimization.md#fr-61-create-user-guide)

  - [ ] 17.1 Create directory structure

    - [ ] 17.1.1 Create `docs/user-guide/` directory
    - [ ] 17.1.2 Create `docs/user-guide/index.md`

  - [ ] 17.2 Write `index.md` content

    - [ ] 17.2.1 Add overview of klaw-core msgspec usage
    - [ ] 17.2.2 Add navigation links to sub-pages
    - [ ] 17.2.3 Add quick start example
    - [ ] 17.2.4 Link to external msgspec docs

  - [ ] 17.3 Update `mkdocs.yml` (if using mkdocs)

    - [ ] 17.3.1 Add user-guide section to nav

______________________________________________________________________

- [ ] **18.0 Write Wire Protocol Documentation**

  > **PRD Ref:** [FR-6.1](./0005-prd-msgspec-optimization.md#fr-61-create-user-guide)

  - [ ] 18.1 Create `docs/user-guide/wire-protocol.md`

    - [ ] 18.1.1 Explain wire protocol purpose
    - [ ] 18.1.2 Document `WireEnvelope` and all message types
    - [ ] 18.1.3 Show encoding/decoding examples
    - [ ] 18.1.4 Explain tagged union dispatch with `match` statement
    - [ ] 18.1.5 Document `msgspec.Raw` for deferred payload decoding
    - [ ] 18.1.6 Link to [oracle-msgspec-guide.md §6](./oracle-msgspec-guide.md#6-ray-specific-patterns-for-klaw-core)

  - [ ] 18.2 Add diagrams

    - [ ] 18.2.1 Wire envelope structure diagram
    - [ ] 18.2.2 Message flow diagram

______________________________________________________________________

- [ ] **19.0 Write Codec & Types Documentation**

  > **PRD Ref:** [FR-6.1](./0005-prd-msgspec-optimization.md#fr-61-create-user-guide)

  - [ ] 19.1 Create `docs/user-guide/codec.md`

    - [ ] 19.1.1 Explain `CodecPool` purpose and usage
    - [ ] 19.1.2 Show thread-safe encoding example
    - [ ] 19.1.3 Explain `BufferPool` for zero-allocation
    - [ ] 19.1.4 Show `encode_into` usage
    - [ ] 19.1.5 Link to [oracle-msgspec-guide.md §3.1](./oracle-msgspec-guide.md#31-encoder--decoder-reuse)

  - [ ] 19.2 Create `docs/user-guide/types.md`

    - [ ] 19.2.1 List all constrained types with valid ranges
    - [ ] 19.2.2 Show usage examples
    - [ ] 19.2.3 Explain error messages
    - [ ] 19.2.4 Link to [msgspec constraints docs](https://jcristharif.com/msgspec/constraints.html)

  - [ ] 19.3 Create `docs/user-guide/channels.md`

    - [ ] 19.3.1 Explain channel patterns with wire protocol
    - [ ] 19.3.2 Show sender/receiver with typed messages
    - [ ] 19.3.3 Link to existing channel docs

  - [ ] 19.4 Create `docs/user-guide/performance.md`

    - [ ] 19.4.1 List performance optimization tips
    - [ ] 19.4.2 Explain `array_like=True` benefit
    - [ ] 19.4.3 Explain `gc=False` usage
    - [ ] 19.4.4 Link to [msgspec perf tips](https://jcristharif.com/msgspec/perf-tips.html)

______________________________________________________________________

- [ ] **20.0 API Reference Docstrings**

  > **PRD Ref:** [FR-6.2](./0005-prd-msgspec-optimization.md#fr-62-api-reference)

  - [ ] 20.1 Audit `wire.py` docstrings

    - [ ] 20.1.1 Ensure all classes have docstrings
    - [ ] 20.1.2 Ensure all public functions have docstrings
    - [ ] 20.1.3 Add usage examples in docstrings

  - [ ] 20.2 Audit `codec.py` docstrings

    - [ ] 20.2.1 Ensure `CodecPool` has complete docstring
    - [ ] 20.2.2 Ensure `BufferPool` has complete docstring
    - [ ] 20.2.3 Ensure all methods have Args/Returns/Raises

  - [ ] 20.3 Audit `types.py` docstrings

    - [ ] 20.3.1 Ensure each type alias has docstring
    - [ ] 20.3.2 Document valid ranges

  - [ ] 20.4 Audit `schema.py` docstrings

    - [ ] 20.4.1 Ensure `SchemaRegistry` has complete docstring

  - [ ] 20.5 Audit `views.py` docstrings

    - [ ] 20.5.1 Ensure view structs have docstrings

  - [ ] 20.6 Audit `config.py` docstrings

    - [ ] 20.6.1 Ensure all config structs have docstrings
    - [ ] 20.6.2 Ensure `load_config` has complete docstring

______________________________________________________________________

## Summary

| Phase | Tasks       | Description                         |
| ----- | ----------- | ----------------------------------- |
| 1     | 1.0 - 4.0   | Wire Protocol Foundation (Critical) |
| 2     | 5.0 - 7.0   | Type Safety (High)                  |
| 3     | 8.0 - 10.0  | Future-Proofing (Medium)            |
| 4     | 11.0 - 13.0 | Polish (Low)                        |
| 5     | 14.0 - 16.0 | Cross-Cutting Tests                 |
| 6     | 17.0 - 20.0 | Documentation                       |

**Total Tasks:** 20 parent tasks, 200+ sub-tasks

______________________________________________________________________

## Quick Reference Commands

```bash
# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/runtime/channels/test_wire.py -v

# Run tests matching pattern
uv run pytest tests/ -v -k "wire"

# Run benchmarks
uv run pytest tests/benchmarks/ --benchmark-only

# Type check
uv run mypy src/klaw_core/

# Lint
uv run ruff check src/klaw_core/

# Format
uv run ruff format src/klaw_core/
```
