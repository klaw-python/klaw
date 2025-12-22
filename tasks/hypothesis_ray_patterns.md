# Hypothesis + Ray Actors: Testing Patterns

This guide captures practical patterns for using **Hypothesis** (property-based testing) with **Ray actors** to test distributed, stateful systems in a deterministic way.

The goal: let Hypothesis explore inputs while Ray exercises your actor logic — without turning your tests into quantum experiments.

______________________________________________________________________

## 1. Basic Pattern: One Actor per Example

Each Hypothesis example must see a fresh actor with clean state.

```python
import ray
from hypothesis import given, settings, strategies as st

ray.init(ignore_reinit_error=True)


@ray.remote
class Counter:
    def __init__(self):
        self.value = 0

    def add(self, x: int):
        self.value += x
        return self.value

    def get(self):
        return self.value


@settings(deadline=None, max_examples=100)
@given(st.lists(st.integers(-100, 100), min_size=1, max_size=20))
def test_counter_behaves_like_sum(ops):
    c = Counter.remote()  # fresh actor per example

    total = 0
    for x in ops:
        total = ray.get(c.add.remote(x))

    assert total == sum(ops)
```

**Key idea:** Hypothesis owns the loop over inputs; Ray just runs the actor logic.

______________________________________________________________________

## 2. Determinism Is Sacred

Actors should be deterministic for a given input sequence.

Avoid inside actors:

- Wall clocks (`time.time()`)
- Global RNG without seeding
- Network calls
- Scheduling-dependent logic

If randomness is required:

```python
import random


@ray.remote
class RNGActor:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def next(self):
        return self.rng.random()
```

Then pass the seed from Hypothesis.

______________________________________________________________________

## 3. Disable Hypothesis Deadlines

Ray adds overhead. Hypothesis defaults to 200 ms per example.

```python
@settings(deadline=None)
```

This prevents spurious deadline failures.

______________________________________________________________________

## 4. Local Mode for Debugging

When shrinking finds a bug, you want readable tracebacks.

```python
ray.init(local_mode=True)
```

Everything runs in-process, which makes debugging sane.

______________________________________________________________________

## 5. Stateful Pattern: Model vs Actor

Use Hypothesis state machines to compare your actor to a pure Python model.

```python
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize


@ray.remote
class Counter:
    def __init__(self):
        self.value = 0

    def add(self, x: int):
        self.value += x
        return self.value


class CounterMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.actor = Counter.remote()
        self.model = 0

    @initialize()
    def init(self):
        self.actor = Counter.remote()
        self.model = 0

    @rule(x=st.integers(-10, 10))
    def add(self, x):
        self.model += x
        result = ray.get(self.actor.add.remote(x))
        assert result == self.model


TestCounter = CounterMachine.TestCase
```

**Pattern:**

- Python model = oracle
- Ray actor = system under test
- Hypothesis invents call sequences

______________________________________________________________________

## 6. Async Actors Pattern

If your actor methods are async:

```python
@ray.remote
class AsyncActor:
    async def double(self, x: int) -> int:
        return x * 2


def test_async_actor():
    a = AsyncActor.remote()
    assert ray.get(a.double.remote(21)) == 42
```

Hypothesis doesn’t care — just keep the sync boundary at `ray.get`.

______________________________________________________________________

## 7. Pytest Integration

Ray as a session-scoped fixture:

```python
import pytest
import ray


@pytest.fixture(scope='session', autouse=True)
def ray_cluster():
    ray.init(ignore_reinit_error=True)
    yield
    ray.shutdown()
```

Now all Hypothesis tests can assume Ray is running.

______________________________________________________________________

## 8. What to Avoid

- Reusing actors across examples
- Parallel Hypothesis execution (`pytest -n auto`)
- External side effects (databases, S3, GPUs) unless mocked
- Assertions depending on logs or timing

Hypothesis wants a pure function worldview. Fake it convincingly.

______________________________________________________________________

## 9. When This Shines

These patterns work especially well for:

- Distributed state machines
- Actor-based coordinators
- Stream processors
- Control planes
- Custom Ray-native data engines

You get exhaustive input exploration with a real distributed runtime.

______________________________________________________________________

## 10. Mental Model

Think of each Hypothesis example as:

> “Spawn a tiny universe, run a distributed experiment, destroy it.”

If every universe obeys your invariants, your actor is probably sane.

______________________________________________________________________

Happy testing. Let the mischievous mathematician roam — but keep the lab deterministic.
