# Tasks: Ray Channels

Generated from [0004-prd-ray-channels.md](./0004-prd-ray-channels.md)

## Relevant Files

### Source Files

- `workspaces/python/klaw-core/src/klaw_core/runtime/errors.py` - Add `ChannelBackendError` struct+exception
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/protocols.py` - Add `ReferenceSender`, `ReferenceReceiver` protocols
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/stats.py` - New file for `ChannelStats`, `ChannelCheckpoint` dataclasses
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/factory.py` - Update to dispatch to Ray backend
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/__init__.py` - Update exports
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/__init__.py` - Ray submodule public exports
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/constants.py` - `DEFAULT_RAY_NAMESPACE`, `ReaderInfo`
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/actor.py` - `RayChannelActor` implementation
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/core.py` - `RaySender`, `RayReceiver` wrappers
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/reference.py` - `RayReferenceSender`, `RayReferenceReceiver`
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/broadcast.py` - `RayBroadcastActor`, sender/receiver
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/watch.py` - `RayWatchActor`, sender/receiver
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/factory.py` - Ray-specific factory functions
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/supervisor.py` - `ChannelSupervisor`, `get_channel_supervisor()`
- `workspaces/python/klaw-core/src/klaw_core/runtime/channels/ray/pools.py` - `ChannelReader`, `ReaderPoolController`

### Test Files

- `workspaces/python/klaw-core/tests/runtime/test_channels_ray_actor.py` - Unit tests for RayChannelActor
- `workspaces/python/klaw-core/tests/runtime/test_channels_ray_core.py` - Tests for RaySender/RayReceiver
- `workspaces/python/klaw-core/tests/runtime/test_channels_ray_reference.py` - Tests for reference channels
- `workspaces/python/klaw-core/tests/runtime/test_channels_ray_broadcast.py` - Tests for Ray broadcast
- `workspaces/python/klaw-core/tests/runtime/test_channels_ray_watch.py` - Tests for Ray watch
- `workspaces/python/klaw-core/tests/runtime/test_channels_ray_factory.py` - Tests for factory dispatch and named channels
- `workspaces/python/klaw-core/tests/runtime/test_channels_ray_supervisor.py` - Tests for supervisor and pools
- `workspaces/python/klaw-core/tests/runtime/test_channels_ray_distributed.py` - Cross-process integration tests
- `workspaces/python/klaw-core/tests/runtime/conftest.py` - Add Ray fixtures

### Notes

- Unit tests should be placed in `tests/runtime/` alongside existing channel tests
- Use `uv run pytest workspaces/python/klaw-core/tests/runtime/` to run tests
- Ray tests should use `ray.init(local_mode=True)` fixture for unit tests
- Follow existing struct+exception dual pattern for new error types
- Mark Ray tests with `@pytest.mark.ray` for selective execution

______________________________________________________________________

## Tasks

- [ ] 1.0 Foundation: Error Types and Protocols

  - [ ] 1.1 Add `ChannelBackendError` struct to `errors.py` with fields: `message`, `backend`, `actor_name`, `namespace`
  - [ ] 1.2 Add `ChannelBackendErrorException` class that subclasses `ChannelClosedError` with same fields
  - [ ] 1.3 Add `to_exception()` and `to_struct()` conversion methods following existing pattern
  - [ ] 1.4 Export new error types in `errors.py` `__all__`
  - [ ] 1.5 Create `stats.py` with `ChannelStats` dataclass (sender_count, receiver_count, queue_size, capacity, senders_closed, receivers_closed, created_at, high_watermark, total_sent, total_received, backend_extras)
  - [ ] 1.6 Add `ChannelCheckpoint` dataclass to `stats.py` (created_at, total_sent, total_received, senders_closed, receivers_closed)
  - [ ] 1.7 Add `ReferenceSender[T]` protocol to `protocols.py` extending `Sender[T]` with `send_batch()` method
  - [ ] 1.8 Add `ReferenceReceiver[T]` protocol to `protocols.py` extending `Receiver[T]` with `recv_batch()` method
  - [ ] 1.9 Export new protocols in `protocols.py` `__all__`

- [ ] 2.0 Core Ray Channel Actor

  - [ ] 2.1 Create `ray/` directory structure with `__init__.py`
  - [ ] 2.2 Create `ray/constants.py` with `DEFAULT_RAY_NAMESPACE = "klaw"` and optional env var override
  - [ ] 2.3 Create `ReaderInfo` dataclass in `ray/constants.py` (reader_id, node_id, registered_at, last_seen_at, total_received)
  - [ ] 2.4 Create `ray/actor.py` with `RayChannelActor` class skeleton and `@ray.remote(max_restarts=4, max_task_retries=-1)` decorator
  - [ ] 2.5 Implement `__init__` with capacity, unbounded params, asyncio.Queue, ref counts, and stats tracking
  - [ ] 2.6 Implement `register_sender()` and `deregister_sender()` returning status codes
  - [ ] 2.7 Implement `register_receiver(reader_id, node_id)` and `deregister_receiver(reader_id)` with node tracking
  - [ ] 2.8 Implement `put(item, timeout)` async method returning `"ok" | "full" | "closed"`
  - [ ] 2.9 Implement `put_nowait(item)` sync method returning status codes
  - [ ] 2.10 Implement `get(timeout, reader_id)` async method returning `(status, value)` tuple
  - [ ] 2.11 Implement `get_nowait(reader_id)` sync method returning `(status, value)` tuple
  - [ ] 2.12 Implement `put_batch(items, timeout)` for atomic batch send
  - [ ] 2.13 Implement `get_batch(max_items, timeout, reader_id)` for batch receive
  - [ ] 2.14 Implement `get_metadata()` returning dict with `type`, `capacity`, `unbounded`
  - [ ] 2.15 Implement `get_stats()` returning `ChannelStats` with all metrics including per_node_receivers in backend_extras
  - [ ] 2.16 Implement `get_checkpoint_state()` returning `ChannelCheckpoint`
  - [ ] 2.17 Implement `apply_checkpoint_state(state)` for recovery
  - [ ] 2.18 Implement `get_capacity()`, `is_closed()`, `get_reader_stats()` helper methods
  - [ ] 2.19 Add internal `_update_watermark()` and `_update_reader_stats()` helpers

- [ ] 3.0 RaySender and RayReceiver Wrappers

  - [ ] 3.1 Create `ray/core.py` with imports and type variables
  - [ ] 3.2 Implement `RaySender[T]` class with `__slots__` for actor, capacity, closed, registered, namespace
  - [ ] 3.3 Implement `RaySender._ensure_registered()` async method with lazy registration
  - [ ] 3.4 Implement `RaySender.send(value)` mapping actor status codes to exceptions
  - [ ] 3.5 Implement `RaySender.try_send(value)` returning `Result[None, ChannelFull | ChannelClosed | ChannelBackendError]`
  - [ ] 3.6 Implement `RaySender.send_batch(values)` for batch operations
  - [ ] 3.7 Implement `RaySender.clone()` returning new instance with same actor
  - [ ] 3.8 Implement `RaySender.close()` calling deregister_sender
  - [ ] 3.9 Wrap all actor calls in try/except for `ray.exceptions.RayError` → `ChannelBackendError`
  - [ ] 3.10 Implement `RayReceiver[T]` class with `__slots__` for actor, capacity, closed, registered, reader_id, node_id, namespace
  - [ ] 3.11 Implement `RayReceiver._get_node_id()` using `ray.get_runtime_context().get_node_id()`
  - [ ] 3.12 Implement `RayReceiver._ensure_registered()` with reader_id and node_id
  - [ ] 3.13 Implement `RayReceiver.recv(timeout)` mapping status codes to exceptions
  - [ ] 3.14 Implement `RayReceiver.try_recv()` returning `Result[T, ChannelEmpty | ChannelClosed | ChannelBackendError]`
  - [ ] 3.15 Implement `RayReceiver.recv_batch(max_items, timeout)` for batch receive
  - [ ] 3.16 Implement `RayReceiver.__aiter__()` and `__anext__()` for async iteration
  - [ ] 3.17 Implement `RayReceiver.clone()` returning new instance with fresh reader_id
  - [ ] 3.18 Implement `RayReceiver.close()` calling deregister_receiver

- [ ] 4.0 Reference Channels for Large Payloads

  - [ ] 4.1 Create `ray/reference.py` with imports
  - [ ] 4.2 Implement `RayReferenceSender[T]` wrapping a `RaySender[ray.ObjectRef]`
  - [ ] 4.3 Implement `RayReferenceSender.send(value)` using `ray.put(value)` then sending ref
  - [ ] 4.4 Implement `RayReferenceSender.send_batch(values)` with batch `ray.put()`
  - [ ] 4.5 Implement `RayReferenceSender.try_send()`, `clone()`, `close()` delegating to inner sender
  - [ ] 4.6 Implement `RayReferenceReceiver[T]` wrapping a `RayReceiver[ray.ObjectRef]`
  - [ ] 4.7 Implement `RayReferenceReceiver.recv()` calling `ray.get()` on received ref
  - [ ] 4.8 Implement `RayReferenceReceiver.recv_batch(max_items)` with batch `ray.get()`
  - [ ] 4.9 Implement `RayReferenceReceiver.try_recv()`, `__aiter__`, `__anext__`, `clone()`, `close()`

- [ ] 5.0 Ray-Specific Channel Types (Broadcast, Watch)

  - [ ] 5.1 Create `ray/broadcast.py` with `RayBroadcastActor` class
  - [ ] 5.2 Implement broadcast actor with per-reader queues dict and fan-out send logic
  - [ ] 5.3 Implement `register_receiver(reader_id, node_id)` creating per-reader queue
  - [ ] 5.4 Implement `send(value)` fanning out to all registered reader queues
  - [ ] 5.5 Implement `recv(reader_id)` getting from reader's specific queue
  - [ ] 5.6 Implement `get_metadata()` returning `{"type": "broadcast", ...}`
  - [ ] 5.7 Implement `RayBroadcastSender[T]` and `RayBroadcastReceiver[T]` wrappers
  - [ ] 5.8 Create `ray/watch.py` with `RayWatchActor` class
  - [ ] 5.9 Implement watch actor with single `_value` slot and waiters dict
  - [ ] 5.10 Implement `send(value)` updating value and waking all waiters
  - [ ] 5.11 Implement `recv(reader_id)` returning current value or waiting for first
  - [ ] 5.12 Implement `borrow()` for non-blocking current value access
  - [ ] 5.13 Implement `get_metadata()` returning `{"type": "watch", ...}`
  - [ ] 5.14 Implement `RayWatchSender[T]` and `RayWatchReceiver[T]` wrappers with `borrow()` and `changed()` methods

- [ ] 6.0 Factory Functions and Integration

  - [ ] 6.1 Create `ray/factory.py` with imports and logger
  - [ ] 6.2 Implement `ray_channel(capacity, unbounded, name, namespace)` creating actor and returning `(RaySender, RayReceiver)`
  - [ ] 6.3 Handle named channels with `lifetime="detached"`, `get_if_exists=True` actor options
  - [ ] 6.4 Implement `get_ray_channel(name, namespace)` using `ray.get_actor()` and `get_metadata()` for type dispatch
  - [ ] 6.5 Implement `delete_ray_channel(name, namespace)` using `ray.kill(actor, no_restart=True)`
  - [ ] 6.6 Implement `list_ray_channels(namespace)` using `ray.util.list_named_actors(all_namespaces=True)`
  - [ ] 6.7 Implement `ray_broadcast_channel(capacity_per_reader, name, namespace)` factory
  - [ ] 6.8 Implement `ray_watch_channel(initial, name, namespace)` factory
  - [ ] 6.9 Update top-level `factory.py` to accept `backend: Literal["local", "ray"] | None` parameter
  - [ ] 6.10 Update `channel()` to dispatch to `ray_channel()` when `distributed=True` or `backend="ray"`
  - [ ] 6.11 Add lazy import of `ray/factory.py` to avoid importing Ray when not needed
  - [ ] 6.12 Create `ray/__init__.py` exporting all Ray-specific types and factories
  - [ ] 6.13 Update `channels/__init__.py` to optionally expose `ChannelStats`, `ChannelCheckpoint`

- [ ] 7.0 Supervisor and Reader Pools

  - [ ] 7.1 Create `ray/supervisor.py` with `ChannelSupervisor` actor class
  - [ ] 7.2 Implement supervisor `__init__` with channels dict and checkpoints dict
  - [ ] 7.3 Implement `create_channel(name, capacity, unbounded, channel_type)` storing actor handles
  - [ ] 7.4 Implement `delete_channel(name)` with `ray.kill()`
  - [ ] 7.5 Implement `list_channels()` returning channel names
  - [ ] 7.6 Implement `get_checkpoint(name)` fetching and caching checkpoint state
  - [ ] 7.7 Implement `restore_from_checkpoint(name, state_dict)` applying checkpoint
  - [ ] 7.8 Implement `get_channel_supervisor(namespace, name)` helper with get-or-create pattern using `get_if_exists=True`
  - [ ] 7.9 Create `ray/pools.py` with `ChannelReader` actor base class
  - [ ] 7.10 Implement `ChannelReader.__init__(channel_name, namespace)` storing config
  - [ ] 7.11 Implement `ChannelReader.start()` connecting to channel and iterating
  - [ ] 7.12 Implement `ChannelReader.process(item)` as overridable method
  - [ ] 7.13 Implement `ReaderPoolController` actor with readers list
  - [ ] 7.14 Implement `ReaderPoolController.__init__(channel_name, initial_size)` spawning readers
  - [ ] 7.15 Implement `ReaderPoolController.scale(delta)` for dynamic sizing
  - [ ] 7.16 Implement `ReaderPoolController.num_readers()` for introspection

- [ ] 8.0 Testing

  - [ ] 8.1 Add `ray_init` pytest fixture in `conftest.py` using `ray.init(local_mode=True)` with teardown
  - [ ] 8.2 Add `pytest.mark.ray` marker registration in `conftest.py` or `pytest.ini`
  - [ ] 8.3 Create `test_channels_ray_actor.py` with basic send/recv tests
  - [ ] 8.4 Add tests for ref-counting (register/deregister senders and receivers)
  - [ ] 8.5 Add tests for batch operations (put_batch, get_batch)
  - [ ] 8.6 Add tests for stats and checkpoint methods
  - [ ] 8.7 Create `test_channels_ray_core.py` testing `RaySender`/`RayReceiver` protocol compliance
  - [ ] 8.8 Add tests for async iteration over `RayReceiver`
  - [ ] 8.9 Add tests for clone semantics
  - [ ] 8.10 Add tests for error handling (`ChannelBackendError` on actor failure)
  - [ ] 8.11 Create `test_channels_ray_reference.py` testing large payload efficiency
  - [ ] 8.12 Add tests verifying `ObjectRef` is passed through channel (not value)
  - [ ] 8.13 Create `test_channels_ray_broadcast.py` testing fan-out semantics
  - [ ] 8.14 Create `test_channels_ray_watch.py` testing latest-value semantics
  - [ ] 8.15 Create `test_channels_ray_factory.py` testing `ray_channel()` creation
  - [ ] 8.16 Add tests for named channel persistence (`get_ray_channel`, `delete_ray_channel`, `list_ray_channels`)
  - [ ] 8.17 Add tests for factory dispatch (`distributed=True`, `backend="ray"`)
  - [ ] 8.18 Create `test_channels_ray_supervisor.py` testing supervisor lifecycle
  - [ ] 8.19 Add tests for `get_channel_supervisor()` singleton behavior
  - [ ] 8.20 Add tests for `ReaderPoolController` scaling
  - [ ] 8.21 Create `test_channels_ray_distributed.py` with cross-process tests (spawn separate workers)
  - [ ] 8.22 Add test for channel communication between Ray tasks
  - [ ] 8.23 Add test for named channel access from multiple drivers/jobs
