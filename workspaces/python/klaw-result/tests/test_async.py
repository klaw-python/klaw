"""Tests for async utilities: AsyncResult, async_collect, async_lru_safe."""

import asyncio

import pytest

from klaw_result import Err, Ok, Result
from klaw_result.async_ import (
    AsyncResult,
    async_collect,
    async_collect_concurrent,
    async_filter_ok,
    async_first_ok,
    async_iter_ok,
    async_lru_safe,
    async_map,
    async_partition,
)


class TestAsyncResult:
    """Tests for AsyncResult wrapper."""

    @pytest.mark.asyncio
    async def test_await_ok(self):
        """Can await AsyncResult to get Ok."""

        async def get_ok() -> Result[int, str]:
            return Ok(42)

        result = await AsyncResult(get_ok())
        assert result == Ok(42)

    @pytest.mark.asyncio
    async def test_await_err(self):
        """Can await AsyncResult to get Err."""

        async def get_err() -> Result[int, str]:
            return Err("error")

        result = await AsyncResult(get_err())
        assert result == Err("error")

    @pytest.mark.asyncio
    async def test_from_ok(self):
        """AsyncResult.from_ok creates Ok result."""
        result = await AsyncResult.from_ok(42)
        assert result == Ok(42)

    @pytest.mark.asyncio
    async def test_from_err(self):
        """AsyncResult.from_err creates Err result."""
        result = await AsyncResult.from_err("error")
        assert result == Err("error")

    @pytest.mark.asyncio
    async def test_from_result_ok(self):
        """AsyncResult.from_result wraps existing Ok."""
        result = await AsyncResult.from_result(Ok(42))
        assert result == Ok(42)

    @pytest.mark.asyncio
    async def test_from_result_err(self):
        """AsyncResult.from_result wraps existing Err."""
        result = await AsyncResult.from_result(Err("error"))
        assert result == Err("error")

    @pytest.mark.asyncio
    async def test_amap_ok(self):
        """amap transforms Ok value."""
        result = await AsyncResult.from_ok(5).amap(lambda x: x * 2)
        assert result == Ok(10)

    @pytest.mark.asyncio
    async def test_amap_err(self):
        """amap preserves Err."""
        result = await AsyncResult.from_err("error").amap(lambda x: x * 2)
        assert result == Err("error")

    @pytest.mark.asyncio
    async def test_amap_async_ok(self):
        """amap_async transforms with async function."""

        async def double(x: int) -> int:
            await asyncio.sleep(0)
            return x * 2

        result = await AsyncResult.from_ok(5).amap_async(double)
        assert result == Ok(10)

    @pytest.mark.asyncio
    async def test_amap_err_transforms_error(self):
        """amap_err transforms Err value."""
        result = await AsyncResult.from_err("error").amap_err(str.upper)
        assert result == Err("ERROR")

    @pytest.mark.asyncio
    async def test_amap_err_preserves_ok(self):
        """amap_err preserves Ok."""
        result = await AsyncResult.from_ok(42).amap_err(str.upper)
        assert result == Ok(42)

    @pytest.mark.asyncio
    async def test_aand_then_ok(self):
        """aand_then chains sync Result function."""

        def validate(x: int) -> Result[int, str]:
            return Ok(x) if x > 0 else Err("not positive")

        result = await AsyncResult.from_ok(5).aand_then(validate)
        assert result == Ok(5)

    @pytest.mark.asyncio
    async def test_aand_then_err(self):
        """aand_then preserves original Err."""

        def validate(x: int) -> Result[int, str]:
            return Ok(x * 2)

        result = await AsyncResult.from_err("original").aand_then(validate)
        assert result == Err("original")

    @pytest.mark.asyncio
    async def test_aand_then_chain_fails(self):
        """aand_then propagates new Err."""

        def validate(x: int) -> Result[int, str]:
            return Err("validation failed")

        result = await AsyncResult.from_ok(5).aand_then(validate)
        assert result == Err("validation failed")

    @pytest.mark.asyncio
    async def test_aand_then_async_ok(self):
        """aand_then_async chains async Result function."""

        async def fetch(x: int) -> Result[str, str]:
            await asyncio.sleep(0)
            return Ok(f"item-{x}")

        result = await AsyncResult.from_ok(5).aand_then_async(fetch)
        assert result == Ok("item-5")

    @pytest.mark.asyncio
    async def test_aor_else_ok(self):
        """aor_else preserves Ok."""

        def recover(e: str) -> Result[int, str]:
            return Ok(0)

        result = await AsyncResult.from_ok(42).aor_else(recover)
        assert result == Ok(42)

    @pytest.mark.asyncio
    async def test_aor_else_err(self):
        """aor_else recovers from Err."""

        def recover(e: str) -> Result[int, str]:
            return Ok(0)

        result = await AsyncResult.from_err("error").aor_else(recover)
        assert result == Ok(0)

    @pytest.mark.asyncio
    async def test_aor_else_async(self):
        """aor_else_async recovers with async function."""

        async def recover(e: str) -> Result[int, str]:
            await asyncio.sleep(0)
            return Ok(0)

        result = await AsyncResult.from_err("error").aor_else_async(recover)
        assert result == Ok(0)

    @pytest.mark.asyncio
    async def test_aunwrap_or(self):
        """aunwrap_or returns value or default."""
        assert await AsyncResult.from_ok(42).aunwrap_or(0) == 42
        assert await AsyncResult.from_err("e").aunwrap_or(0) == 0

    @pytest.mark.asyncio
    async def test_aunwrap_or_else(self):
        """aunwrap_or_else computes default from error."""

        def compute_default(e: str) -> int:
            return len(e)

        assert await AsyncResult.from_ok(42).aunwrap_or_else(compute_default) == 42
        assert await AsyncResult.from_err("error").aunwrap_or_else(compute_default) == 5

    @pytest.mark.asyncio
    async def test_aok(self):
        """aok converts to Option."""
        from klaw_result import Nothing, Some

        assert await AsyncResult.from_ok(42).aok() == Some(42)
        assert await AsyncResult.from_err("e").aok() == Nothing

    @pytest.mark.asyncio
    async def test_aerr(self):
        """aerr converts to Option."""
        from klaw_result import Nothing, Some

        assert await AsyncResult.from_ok(42).aerr() == Nothing
        assert await AsyncResult.from_err("e").aerr() == Some("e")

    @pytest.mark.asyncio
    async def test_azip_both_ok(self):
        """azip combines two Ok results."""
        ar1 = AsyncResult.from_ok(1)
        ar2 = AsyncResult.from_ok("a")
        result = await ar1.azip(ar2)
        assert result == Ok((1, "a"))

    @pytest.mark.asyncio
    async def test_azip_first_err(self):
        """azip returns first Err."""
        ar1 = AsyncResult.from_err("e1")
        ar2 = AsyncResult.from_ok("a")
        result = await ar1.azip(ar2)
        assert result == Err("e1")

    @pytest.mark.asyncio
    async def test_azip_second_err(self):
        """azip returns second Err if first is Ok."""
        ar1 = AsyncResult.from_ok(1)
        ar2 = AsyncResult.from_err("e2")
        result = await ar1.azip(ar2)
        assert result == Err("e2")

    @pytest.mark.asyncio
    async def test_azip_runs_concurrently(self):
        """azip runs both awaitables concurrently."""
        order: list[int] = []

        async def slow1() -> Result[int, str]:
            order.append(1)
            await asyncio.sleep(0.01)
            order.append(2)
            return Ok(1)

        async def slow2() -> Result[int, str]:
            order.append(3)
            await asyncio.sleep(0.01)
            order.append(4)
            return Ok(2)

        ar1 = AsyncResult(slow1())
        ar2 = AsyncResult(slow2())
        result = await ar1.azip(ar2)

        assert result == Ok((1, 2))
        assert order[0] in (1, 3) and order[1] in (1, 3)

    @pytest.mark.asyncio
    async def test_chained_operations(self):
        """Multiple operations can be chained."""

        async def fetch(id: int) -> Result[dict, str]:
            return Ok({"id": id, "name": f"user-{id}"})

        result = await AsyncResult(fetch(1)).amap(lambda d: d["name"]).amap(str.upper)
        assert result == Ok("USER-1")

    def test_repr(self):
        """AsyncResult has repr."""
        ar = AsyncResult.from_ok(42)
        assert "AsyncResult" in repr(ar)


class TestAsyncCollect:
    """Tests for async_collect function."""

    @pytest.mark.asyncio
    async def test_collect_all_ok(self):
        """async_collect collects all Ok values."""

        async def get(n: int) -> Result[int, str]:
            return Ok(n * 2)

        result = await async_collect([get(1), get(2), get(3)])
        assert result == Ok([2, 4, 6])

    @pytest.mark.asyncio
    async def test_collect_first_err(self):
        """async_collect returns first Err."""

        async def get(n: int) -> Result[int, str]:
            return Ok(n) if n != 2 else Err("error at 2")

        result = await async_collect([get(1), get(2), get(3)])
        assert result == Err("error at 2")

    @pytest.mark.asyncio
    async def test_collect_empty(self):
        """async_collect with empty list returns Ok([])."""
        result = await async_collect([])
        assert result == Ok([])

    @pytest.mark.asyncio
    async def test_collect_runs_concurrently(self):
        """async_collect runs all tasks concurrently."""
        order: list[int] = []

        async def task(n: int) -> Result[int, str]:
            order.append(n)
            await asyncio.sleep(0.01)
            return Ok(n)

        result = await async_collect([task(1), task(2), task(3)])
        assert result == Ok([1, 2, 3])
        assert set(order) == {1, 2, 3}


class TestAsyncCollectConcurrent:
    """Tests for async_collect_concurrent with limit."""

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        """Respects concurrency limit."""
        concurrent_count = 0
        max_concurrent = 0

        async def task(n: int) -> Result[int, str]:
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return Ok(n)

        tasks = [task(i) for i in range(10)]
        result = await async_collect_concurrent(tasks, limit=3)

        assert result.is_ok()
        assert max_concurrent <= 3

    @pytest.mark.asyncio
    async def test_no_limit(self):
        """Without limit, behaves like async_collect."""

        async def get(n: int) -> Result[int, str]:
            return Ok(n)

        result = await async_collect_concurrent([get(1), get(2)], limit=None)
        assert result == Ok([1, 2])


class TestAsyncMap:
    """Tests for async_map function."""

    @pytest.mark.asyncio
    async def test_maps_all_items(self):
        """async_map applies function to all items."""

        async def double(n: int) -> Result[int, str]:
            return Ok(n * 2)

        result = await async_map(double, [1, 2, 3])
        assert result == Ok([2, 4, 6])

    @pytest.mark.asyncio
    async def test_stops_on_err(self):
        """async_map returns first Err."""

        async def check(n: int) -> Result[int, str]:
            return Ok(n) if n < 3 else Err(f"too big: {n}")

        result = await async_map(check, [1, 2, 3, 4])
        assert result == Err("too big: 3")


class TestAsyncFilterOk:
    """Tests for async_filter_ok function."""

    @pytest.mark.asyncio
    async def test_filters_ok_values(self):
        """async_filter_ok keeps only Ok values."""

        async def maybe(n: int) -> Result[int, str]:
            return Ok(n) if n % 2 == 0 else Err("odd")

        values = await async_filter_ok([maybe(1), maybe(2), maybe(3), maybe(4)])
        assert values == [2, 4]

    @pytest.mark.asyncio
    async def test_empty_when_all_err(self):
        """Returns empty list when all Err."""

        async def fail(n: int) -> Result[int, str]:
            return Err("fail")

        values = await async_filter_ok([fail(1), fail(2)])
        assert values == []


class TestAsyncPartition:
    """Tests for async_partition function."""

    @pytest.mark.asyncio
    async def test_partitions_correctly(self):
        """Partitions into Ok and Err lists."""

        async def check(n: int) -> Result[int, str]:
            return Ok(n) if n > 0 else Err(f"{n} negative")

        oks, errs = await async_partition([check(-1), check(2), check(-3), check(4)])
        assert oks == [2, 4]
        assert errs == ["-1 negative", "-3 negative"]


class TestAsyncFirstOk:
    """Tests for async_first_ok function."""

    @pytest.mark.asyncio
    async def test_returns_first_ok(self):
        """Returns first Ok encountered."""

        async def try_source(n: int) -> Result[str, str]:
            return Ok(f"source{n}") if n == 2 else Err(f"fail{n}")

        result = await async_first_ok([try_source(1), try_source(2), try_source(3)])
        assert result == Ok("source2")

    @pytest.mark.asyncio
    async def test_returns_all_errors(self):
        """Returns all errors when all fail."""

        async def fail(n: int) -> Result[str, str]:
            return Err(f"fail{n}")

        result = await async_first_ok([fail(1), fail(2)])
        assert result == Err(["fail1", "fail2"])


class TestAsyncIterOk:
    """Tests for async_iter_ok function."""

    @pytest.mark.asyncio
    async def test_yields_ok_values(self):
        """Yields only Ok values."""

        async def generate():
            yield Ok(1)
            yield Err("skip")
            yield Ok(2)
            yield Err("skip")
            yield Ok(3)

        values = [v async for v in async_iter_ok(generate())]
        assert values == [1, 2, 3]


class TestAsyncLruSafe:
    """Tests for async_lru_safe decorator."""

    @pytest.mark.asyncio
    async def test_wraps_result_ok(self):
        """Wraps successful return in Ok."""

        @async_lru_safe
        async def get_value() -> int:
            return 42

        result = await get_value()
        assert result == Ok(42)

    @pytest.mark.asyncio
    async def test_wraps_exception_err(self):
        """Wraps exception in Err."""

        @async_lru_safe
        async def fail() -> int:
            raise ValueError("oops")

        result = await fail()
        assert isinstance(result, Err)
        assert isinstance(result.error, ValueError)

    @pytest.mark.asyncio
    async def test_caches_results(self):
        """Caches results across calls."""
        call_count = 0

        @async_lru_safe
        async def expensive(n: int) -> int:
            nonlocal call_count
            call_count += 1
            return n * 2

        await expensive(5)
        await expensive(5)
        await expensive(5)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_with_maxsize(self):
        """Works with maxsize parameter."""
        call_count = 0

        @async_lru_safe(maxsize=2)
        async def compute(n: int) -> int:
            nonlocal call_count
            call_count += 1
            return n

        await compute(1)
        await compute(2)
        await compute(3)
        await compute(1)

        assert call_count == 4


class TestAsyncIntegration:
    """Integration tests for async utilities."""

    @pytest.mark.asyncio
    async def test_async_pipeline(self):
        """Complete async pipeline with multiple operations."""

        async def fetch_user(id: int) -> Result[dict, str]:
            if id <= 0:
                return Err("invalid id")
            return Ok({"id": id, "name": f"user-{id}"})

        async def validate_user(user: dict) -> Result[dict, str]:
            if len(user["name"]) < 3:
                return Err("name too short")
            return Ok(user)

        result = await (
            AsyncResult(fetch_user(1))
            .aand_then_async(validate_user)
            .amap(lambda u: u["name"].upper())
        )
        assert result == Ok("USER-1")

    @pytest.mark.asyncio
    async def test_collect_with_transform(self):
        """Collect results with transformation."""

        async def fetch(id: int) -> Result[dict, str]:
            return Ok({"id": id})

        collected = await async_collect([fetch(1), fetch(2), fetch(3)])
        assert collected.is_ok()

        ids = collected.map(lambda items: [i["id"] for i in items])
        assert ids == Ok([1, 2, 3])

    @pytest.mark.asyncio
    async def test_error_recovery_chain(self):
        """Chain with error recovery."""

        async def primary() -> Result[str, str]:
            return Err("primary failed")

        async def fallback(e: str) -> Result[str, str]:
            return Ok("fallback value")

        result = await AsyncResult(primary()).aor_else_async(fallback)
        assert result == Ok("fallback value")
