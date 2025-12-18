"""Tests for typed fn lambda placeholder."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st
from klaw_core import fn
from klaw_core.fn import Expr, Lambda, Stream


class TestFnBasic:
    """Tests for basic fn functionality."""

    def test_fn_is_lambda(self):
        """Fn is a Lambda instance."""
        assert isinstance(fn, Lambda)

    def test_fn_is_expr(self):
        """Lambda extends Expr."""
        assert isinstance(fn, Expr)

    def test_fn_is_frozen(self):
        """Fn is frozen (immutable)."""
        with pytest.raises(AttributeError):
            fn.x = 42  # type: ignore[attr-defined]

    def test_fn_identity(self):
        """fn() returns the input value (identity function)."""
        assert fn(42) == 42
        assert fn('hello') == 'hello'
        assert fn([1, 2, 3]) == [1, 2, 3]

    def test_fn_repr(self):
        """Fn has readable repr."""
        assert repr(fn) == 'fn'


class TestExprOperators:
    """Tests for operator syntax on Expr."""

    def test_add(self):
        """Fn + n creates addition expression."""
        add_one = fn + 1
        assert isinstance(add_one, Expr)
        assert add_one(5) == 6

    def test_radd(self):
        """N + fn creates addition expression."""
        add_one = 1 + fn
        assert add_one(5) == 6

    def test_sub(self):
        """Fn - n creates subtraction expression."""
        sub_one = fn - 1
        assert sub_one(5) == 4

    def test_rsub(self):
        """N - fn creates subtraction expression."""
        from_ten = 10 - fn
        assert from_ten(3) == 7

    def test_mul(self):
        """Fn * n creates multiplication expression."""
        double = fn * 2
        assert double(5) == 10

    def test_rmul(self):
        """N * fn creates multiplication expression."""
        double = 2 * fn
        assert double(5) == 10

    def test_truediv(self):
        """Fn / n creates division expression."""
        half = fn / 2
        assert half(10) == 5.0

    def test_rtruediv(self):
        """N / fn creates division expression."""
        ten_over = 10 / fn
        assert ten_over(2) == 5.0

    def test_floordiv(self):
        """Fn // n creates floor division expression."""
        half = fn // 2
        assert half(10) == 5
        assert half(11) == 5

    def test_rfloordiv(self):
        """N // fn creates floor division expression."""
        ten_over = 10 // fn
        assert ten_over(3) == 3

    def test_mod(self):
        """Fn % n creates modulo expression."""
        mod_three = fn % 3
        assert mod_three(10) == 1

    def test_rmod(self):
        """N % fn creates modulo expression."""
        ten_mod = 10 % fn
        assert ten_mod(3) == 1

    def test_pow(self):
        """Fn ** n creates power expression."""
        squared = fn**2
        assert squared(5) == 25

    def test_rpow(self):
        """N ** fn creates power expression."""
        two_to = 2**fn
        assert two_to(3) == 8

    def test_neg(self):
        """-fn creates negation expression."""
        negate = -fn
        assert negate(5) == -5
        assert negate(-3) == 3

    def test_pos(self):
        """+fn creates positive expression."""
        pos = +fn
        assert pos(5) == 5

    def test_invert(self):
        """~fn creates bitwise invert expression."""
        invert = ~fn
        assert invert(0) == -1
        assert invert(-1) == 0

    def test_abs(self):
        """abs(fn) creates absolute value expression."""
        absolute = abs(fn)
        assert absolute(5) == 5
        assert absolute(-5) == 5

    def test_and(self):
        """Fn & n creates bitwise AND expression."""
        mask = fn & 0xFF
        assert mask(0x1234) == 0x34

    def test_or(self):
        """Fn | n creates bitwise OR expression."""
        set_bit = fn | 0x80
        assert set_bit(0x01) == 0x81

    def test_xor(self):
        """Fn ^ n creates bitwise XOR expression."""
        flip = fn ^ 0xFF
        assert flip(0x0F) == 0xF0

    def test_lshift(self):
        """Fn << n creates left shift expression."""
        shift = fn << 2
        assert shift(1) == 4

    def test_rshift(self):
        """Fn >> n creates right shift expression."""
        shift = fn >> 2
        assert shift(16) == 4

    def test_lt(self):
        """Fn < n creates less-than expression."""
        less_than_5 = fn < 5
        assert less_than_5(3) is True
        assert less_than_5(5) is False

    def test_le(self):
        """Fn <= n creates less-or-equal expression."""
        at_most_5 = fn <= 5
        assert at_most_5(5) is True
        assert at_most_5(6) is False

    def test_gt(self):
        """Fn > n creates greater-than expression."""
        greater_than_5 = fn > 5
        assert greater_than_5(7) is True
        assert greater_than_5(5) is False

    def test_ge(self):
        """Fn >= n creates greater-or-equal expression."""
        at_least_5 = fn >= 5
        assert at_least_5(5) is True
        assert at_least_5(4) is False

    def test_eq(self):
        """Fn == n creates equality expression."""
        is_five = fn == 5
        assert is_five(5) is True
        assert is_five(3) is False

    def test_ne(self):
        """Fn != n creates inequality expression."""
        not_five = fn != 5
        assert not_five(3) is True
        assert not_five(5) is False

    def test_getitem_dict(self):
        """fn['key'] creates dict access expression."""
        get_name = fn['name']
        assert get_name({'name': 'Alice'}) == 'Alice'

    def test_getitem_list(self):
        """fn[index] creates list access expression."""
        get_first = fn[0]
        assert get_first([1, 2, 3]) == 1

    def test_getitem_slice(self):
        """fn[a:b] creates slice expression."""
        get_slice = fn[1:3]
        assert get_slice([1, 2, 3, 4, 5]) == [2, 3]

    def test_getitem_nested(self):
        """fn['a']['b'] creates nested access expression."""
        get_nested = fn['user']['name']
        data = {'user': {'name': 'Bob'}}
        assert get_nested(data) == 'Bob'

    def test_chain_arithmetic(self):
        """Multiple arithmetic ops can be chained."""
        expr = (fn + 1) * 2
        assert expr(5) == 12

    def test_chain_with_getitem(self):
        """Arithmetic can be chained with item access."""
        first_doubled = fn[0] * 2
        assert first_doubled([5, 6, 7]) == 10

    def test_expr_repr(self):
        """Expr has readable repr."""
        r = repr(fn + 1)
        assert 'add' in r or 'fn' in r

    def test_getitem_repr(self):
        """fn['key'] has readable repr."""
        r = repr(fn['key'])
        assert 'getitem' in r or 'fn' in r


class TestExprChaining:
    """Tests for chaining operations."""

    def test_add_then_mul(self):
        """(fn + 1) * 2 chains correctly."""
        expr = (fn + 1) * 2
        assert expr(5) == 12  # (5+1)*2

    def test_mul_then_add(self):
        """Fn * 2 + 1 chains correctly."""
        expr = fn * 2 + 1
        assert expr(5) == 11  # 5*2+1

    def test_sub_then_pow(self):
        """(fn - 1) ** 2 chains correctly."""
        expr = (fn - 1) ** 2
        assert expr(5) == 16  # (5-1)^2

    def test_nested_getitem(self):
        """fn['a']['b']['c'] chains correctly."""
        data = {'user': {'profile': {'name': 'Alice'}}}
        get_name = fn['user']['profile']['name']
        assert get_name(data) == 'Alice'

    def test_getitem_then_arithmetic(self):
        """fn[0] * 2 chains correctly."""
        expr = fn[0] * 2
        assert expr([5, 6, 7]) == 10

    def test_arithmetic_then_getitem(self):
        """(fn * 2)[0] - multiply then index result."""
        # [5,6,7] * 2 = [5,6,7,5,6,7], then [0] = 5
        expr = (fn * 2)[0]
        assert expr([5, 6, 7]) == 5
        # "ab" * 2 = "abab", [0] = "a"
        assert expr('ab') == 'a'

    def test_complex_chain(self):
        """Multiple operations chain correctly."""
        expr = ((fn + 10) * 2) - 5
        assert expr(5) == 25  # ((5+10)*2)-5 = 30-5 = 25

    def test_comparison_chain(self):
        """Arithmetic then comparison."""
        expr = fn * 2 > 5
        assert expr(3) is True  # 6 > 5
        assert expr(2) is False  # 4 > 5


class TestExprWithMapFilter:
    """Tests for using Expr with map/filter."""

    def test_map_double(self):
        """Fn * 2 works with map."""
        result = list(map(fn * 2, [1, 2, 3]))
        assert result == [2, 4, 6]

    def test_filter_positive(self):
        """Fn > 0 works with filter."""
        result = list(filter(fn > 0, [-1, 0, 1, 2, -3]))
        assert result == [1, 2]

    def test_map_getitem(self):
        """fn['key'] works with map."""
        data = [{'name': 'Alice'}, {'name': 'Bob'}]
        result = list(map(fn['name'], data))
        assert result == ['Alice', 'Bob']

    def test_map_chain(self):
        """Chained expr works with map."""
        result = list(map(fn * 2 + 1, [1, 2, 3]))
        assert result == [3, 5, 7]

    def test_filter_chain(self):
        """Chained comparison works with filter."""
        result = list(filter(fn * 2 > 5, [1, 2, 3, 4, 5]))
        assert result == [3, 4, 5]  # 6, 8, 10 > 5


class TestFnStringMethods:
    """Tests for string method factories."""

    def test_upper(self):
        """fn.upper() creates uppercase function."""
        upper = fn.upper()
        assert upper('hello') == 'HELLO'

    def test_lower(self):
        """fn.lower() creates lowercase function."""
        lower = fn.lower()
        assert lower('HELLO') == 'hello'

    def test_strip(self):
        """fn.strip() creates strip function."""
        strip = fn.strip()
        assert strip('  hello  ') == 'hello'

    def test_strip_chars(self):
        """fn.strip(chars) strips specific chars."""
        strip = fn.strip('xy')
        assert strip('xyhelloxy') == 'hello'

    def test_split(self):
        """fn.split() creates split function."""
        split = fn.split(',')
        assert split('a,b,c') == ['a', 'b', 'c']

    def test_split_maxsplit(self):
        """fn.split(sep, maxsplit) limits splits."""
        split = fn.split(',', 1)
        assert split('a,b,c') == ['a', 'b,c']

    def test_replace(self):
        """fn.replace() creates replace function."""
        replace = fn.replace('l', 'L')
        assert replace('hello') == 'heLLo'

    def test_startswith(self):
        """fn.startswith() creates predicate."""
        starts = fn.startswith('he')
        assert starts('hello') is True
        assert starts('world') is False

    def test_endswith(self):
        """fn.endswith() creates predicate."""
        ends = fn.endswith('lo')
        assert ends('hello') is True
        assert ends('world') is False

    def test_title(self):
        """fn.title() creates title case function."""
        title = fn.title()
        assert title('hello world') == 'Hello World'

    def test_capitalize(self):
        """fn.capitalize() creates capitalize function."""
        cap = fn.capitalize()
        assert cap('hello') == 'Hello'

    def test_isdigit(self):
        """fn.isdigit() creates digit predicate."""
        isdigit = fn.isdigit()
        assert isdigit('123') is True
        assert isdigit('12a') is False

    def test_isalpha(self):
        """fn.isalpha() creates alpha predicate."""
        isalpha = fn.isalpha()
        assert isalpha('hello') is True
        assert isalpha('hello1') is False

    def test_removeprefix(self):
        """fn.removeprefix() removes prefix."""
        rm = fn.removeprefix('test_')
        assert rm('test_foo') == 'foo'
        assert rm('other') == 'other'

    def test_removesuffix(self):
        """fn.removesuffix() removes suffix."""
        rm = fn.removesuffix('.txt')
        assert rm('file.txt') == 'file'
        assert rm('file.py') == 'file.py'


class TestFnDictMethods:
    """Tests for dict method factories."""

    def test_get(self):
        """fn.get() creates getter with default."""
        get_a = fn.get('a', 0)
        assert get_a({'a': 1}) == 1
        assert get_a({'b': 2}) == 0

    def test_keys(self):
        """fn.keys() returns dict keys."""
        keys = fn.keys()
        assert list(keys({'a': 1, 'b': 2})) == ['a', 'b']

    def test_values(self):
        """fn.values() returns dict values."""
        values = fn.values()
        assert list(values({'a': 1, 'b': 2})) == [1, 2]

    def test_items(self):
        """fn.items() returns dict items."""
        items = fn.items()
        assert list(items({'a': 1})) == [('a', 1)]


class TestFnListMethods:
    """Tests for list method factories."""

    def test_copy(self):
        """fn.copy() creates list copy function."""
        copy = fn.copy()
        original = [1, 2, 3]
        copied = copy(original)
        assert copied == original
        assert copied is not original


class TestFnArithmetic:
    """Tests for arithmetic operators."""

    def test_add(self):
        """fn.add(n) creates addition function."""
        add_one = fn.add(1)
        assert add_one(5) == 6

    def test_radd(self):
        """fn.radd(n) creates reverse addition function."""
        add_one = fn.radd(1)
        assert add_one(5) == 6

    def test_sub(self):
        """fn.sub(n) creates subtraction function."""
        sub_one = fn.sub(1)
        assert sub_one(5) == 4

    def test_rsub(self):
        """fn.rsub(n) creates reverse subtraction function."""
        from_ten = fn.rsub(10)
        assert from_ten(3) == 7

    def test_mul(self):
        """fn.mul(n) creates multiplication function."""
        double = fn.mul(2)
        assert double(5) == 10

    def test_rmul(self):
        """fn.rmul(n) creates reverse multiplication function."""
        double = fn.rmul(2)
        assert double(5) == 10

    def test_truediv(self):
        """fn.truediv(n) creates division function."""
        half = fn.truediv(2)
        assert half(10) == 5.0

    def test_rtruediv(self):
        """fn.rtruediv(n) creates reverse division function."""
        ten_over = fn.rtruediv(10)
        assert ten_over(2) == 5.0

    def test_floordiv(self):
        """fn.floordiv(n) creates floor division function."""
        half = fn.floordiv(2)
        assert half(10) == 5
        assert half(11) == 5

    def test_mod(self):
        """fn.mod(n) creates modulo function."""
        mod_three = fn.mod(3)
        assert mod_three(10) == 1

    def test_pow(self):
        """fn.pow(n) creates power function."""
        squared = fn.pow(2)
        assert squared(5) == 25

    def test_neg(self):
        """fn.neg() creates negation function."""
        negate = fn.neg()
        assert negate(5) == -5
        assert negate(-3) == 3

    def test_pos(self):
        """fn.pos() creates positive function."""
        pos = fn.pos()
        assert pos(5) == 5
        assert pos(-3) == -3

    def test_abs(self):
        """fn.abs_() creates absolute value function."""
        absolute = fn.abs_()
        assert absolute(5) == 5
        assert absolute(-5) == 5


class TestFnBitwise:
    """Tests for bitwise operators."""

    def test_and(self):
        """fn.and_(n) creates bitwise AND function."""
        mask = fn.and_(0xFF)
        assert mask(0x1234) == 0x34

    def test_or(self):
        """fn.or_(n) creates bitwise OR function."""
        set_bit = fn.or_(0x80)
        assert set_bit(0x01) == 0x81

    def test_xor(self):
        """fn.xor(n) creates bitwise XOR function."""
        flip = fn.xor(0xFF)
        assert flip(0x0F) == 0xF0

    def test_lshift(self):
        """fn.lshift(n) creates left shift function."""
        shift = fn.lshift(2)
        assert shift(1) == 4

    def test_rshift(self):
        """fn.rshift(n) creates right shift function."""
        shift = fn.rshift(2)
        assert shift(16) == 4

    def test_invert(self):
        """fn.invert() creates bitwise invert function."""
        invert = fn.invert()
        assert invert(0) == -1
        assert invert(-1) == 0


class TestFnComparison:
    """Tests for comparison operators."""

    def test_lt(self):
        """fn.lt(n) creates less-than function."""
        less_than_5 = fn.lt(5)
        assert less_than_5(3) is True
        assert less_than_5(5) is False
        assert less_than_5(7) is False

    def test_le(self):
        """fn.le(n) creates less-or-equal function."""
        at_most_5 = fn.le(5)
        assert at_most_5(3) is True
        assert at_most_5(5) is True
        assert at_most_5(7) is False

    def test_gt(self):
        """fn.gt(n) creates greater-than function."""
        greater_than_5 = fn.gt(5)
        assert greater_than_5(7) is True
        assert greater_than_5(5) is False
        assert greater_than_5(3) is False

    def test_ge(self):
        """fn.ge(n) creates greater-or-equal function."""
        at_least_5 = fn.ge(5)
        assert at_least_5(7) is True
        assert at_least_5(5) is True
        assert at_least_5(3) is False

    def test_eq(self):
        """fn.eq(n) creates equality function."""
        is_five = fn.eq(5)
        assert is_five(5) is True
        assert is_five(3) is False

    def test_ne(self):
        """fn.ne(n) creates inequality function."""
        not_five = fn.ne(5)
        assert not_five(3) is True
        assert not_five(5) is False


class TestFnAccess:
    """Tests for attribute and item access."""

    def test_item_dict(self):
        """fn.item('key') creates dict access function."""
        get_name = fn.item('name')
        assert get_name({'name': 'Alice', 'age': 30}) == 'Alice'

    def test_item_list(self):
        """fn.item(index) creates list access function."""
        get_first = fn.item(0)
        assert get_first([1, 2, 3]) == 1

    def test_item_negative(self):
        """fn.item(-1) creates negative index access."""
        get_last = fn.item(-1)
        assert get_last([1, 2, 3]) == 3

    def test_attr(self):
        """fn.attr('name') creates attribute access function."""

        class Point:
            def __init__(self, x: int, y: int):
                self.x = x
                self.y = y

        get_x = fn.attr('x')
        assert get_x(Point(3, 4)) == 3

    def test_attr_nested(self):
        """fn.attr('a.b') creates nested attribute access."""

        class Inner:
            value = 42

        class Outer:
            inner = Inner()

        get_value = fn.attr('inner.value')
        assert get_value(Outer()) == 42

    def test_method(self):
        """fn.method('name') creates method caller."""
        upper = fn.method('upper')
        assert upper('hello') == 'HELLO'

    def test_method_with_args(self):
        """fn.method('name', *args) passes arguments."""
        split = fn.method('split', ',')
        assert split('a,b,c') == ['a', 'b', 'c']


class TestFnBoolean:
    """Tests for boolean/logic operators."""

    def test_not(self):
        """fn.not_() creates logical not function."""
        negate = fn.not_()
        assert negate(True) is False
        assert negate(False) is True
        assert negate(0) is True
        assert negate(1) is False

    def test_truth(self):
        """fn.truth() creates truthiness function."""
        truth = fn.truth()
        assert truth(1) is True
        assert truth(0) is False
        assert truth([]) is False
        assert truth([1]) is True

    def test_is(self):
        """fn.is_(value) creates identity check."""
        is_none = fn.is_(None)
        assert is_none(None) is True
        assert is_none(0) is False

    def test_is_not(self):
        """fn.is_not(value) creates non-identity check."""
        is_not_none = fn.is_not(None)
        assert is_not_none(None) is False
        assert is_not_none(0) is True

    def test_contains(self):
        """fn.contains(item) checks if container contains item."""
        has_one = fn.contains(1)
        assert has_one([1, 2, 3]) is True
        assert has_one([2, 3, 4]) is False

    def test_in(self):
        """fn.in_(container) checks if item is in container."""
        in_range = fn.in_([1, 2, 3])
        assert in_range(1) is True
        assert in_range(4) is False

    def test_not_in(self):
        """fn.not_in(container) checks if item is not in container."""
        not_in_range = fn.not_in([1, 2, 3])
        assert not_in_range(4) is True
        assert not_in_range(1) is False


class TestFnConversions:
    """Tests for type conversion functions."""

    def test_int(self):
        """fn.int_() creates int conversion function."""
        to_int = fn.int_()
        assert to_int('42') == 42
        assert to_int(3.7) == 3

    def test_float(self):
        """fn.float_() creates float conversion function."""
        to_float = fn.float_()
        assert to_float('3.14') == math.pi
        assert to_float(3) == 3.0

    def test_str(self):
        """fn.str_() creates string conversion function."""
        to_str = fn.str_()
        assert to_str(42) == '42'

    def test_bool(self):
        """fn.bool_() creates bool conversion function."""
        to_bool = fn.bool_()
        assert to_bool(1) is True
        assert to_bool(0) is False

    def test_list(self):
        """fn.list_() creates list conversion function."""
        to_list = fn.list_()
        assert to_list((1, 2, 3)) == [1, 2, 3]
        assert to_list('abc') == ['a', 'b', 'c']

    def test_tuple(self):
        """fn.tuple_() creates tuple conversion function."""
        to_tuple = fn.tuple_()
        assert to_tuple([1, 2, 3]) == (1, 2, 3)

    def test_set(self):
        """fn.set_() creates set conversion function."""
        to_set = fn.set_()
        assert to_set([1, 2, 2, 3]) == {1, 2, 3}


class TestFnBuiltins:
    """Tests for builtin function wrappers."""

    def test_len(self):
        """fn.len_() creates len function."""
        length = fn.len_()
        assert length([1, 2, 3]) == 3
        assert length('hello') == 5

    def test_repr(self):
        """fn.repr_() creates repr function."""
        repr_fn = fn.repr_()
        assert repr_fn('hello') == "'hello'"

    def test_hash(self):
        """fn.hash_() creates hash function."""
        hash_fn = fn.hash_()
        assert hash_fn('hello') == hash('hello')

    def test_type(self):
        """fn.type_() creates type function."""
        type_fn = fn.type_()
        assert type_fn(42) is int
        assert type_fn('hello') is str

    def test_callable(self):
        """fn.callable_() creates callable check."""
        is_callable = fn.callable_()
        assert is_callable(len) is True
        assert is_callable(42) is False

    def test_sorted(self):
        """fn.sorted_() creates sorted function."""
        sort = fn.sorted_()
        assert sort([3, 1, 2]) == [1, 2, 3]

    def test_sorted_reverse(self):
        """fn.sorted_(reverse=True) sorts descending."""
        sort_desc = fn.sorted_(reverse=True)
        assert sort_desc([1, 2, 3]) == [3, 2, 1]

    def test_reversed(self):
        """fn.reversed_() creates reversed function."""
        rev = fn.reversed_()
        assert list(rev([1, 2, 3])) == [3, 2, 1]

    def test_min(self):
        """fn.min_() creates min function."""
        minimum = fn.min_()
        assert minimum([3, 1, 2]) == 1

    def test_max(self):
        """fn.max_() creates max function."""
        maximum = fn.max_()
        assert maximum([3, 1, 2]) == 3

    def test_sum(self):
        """fn.sum_() creates sum function."""
        total = fn.sum_()
        assert total([1, 2, 3]) == 6

    def test_all(self):
        """fn.all_() creates all function."""
        check_all = fn.all_()
        assert check_all([True, True, True]) is True
        assert check_all([True, False, True]) is False

    def test_any(self):
        """fn.any_() creates any function."""
        check_any = fn.any_()
        assert check_any([False, True, False]) is True
        assert check_any([False, False, False]) is False

    def test_enumerate(self):
        """fn.enumerate_() creates enumerate function."""
        enum = fn.enumerate_()
        assert list(enum(['a', 'b'])) == [(0, 'a'), (1, 'b')]

    def test_enumerate_start(self):
        """fn.enumerate_(start=1) starts from custom index."""
        enum = fn.enumerate_(1)
        assert list(enum(['a', 'b'])) == [(1, 'a'), (2, 'b')]


class TestFnIdentity:
    """Tests for identity and composition."""

    def test_identity(self):
        """fn.identity() returns input unchanged."""
        identity = fn.identity()
        assert identity(42) == 42
        assert identity('hello') == 'hello'

    def test_const(self):
        """fn.const(value) always returns value."""
        always_42 = fn.const(42)
        assert always_42(1) == 42
        assert always_42('anything') == 42

    def test_call(self):
        """fn.call(*args) calls callable with args."""
        call = fn.call(3, 4)
        assert call(pow) == 81  # pow(3, 4) = 81


class TestFnWithMap:
    """Tests for using fn with map/filter."""

    def test_map_mul(self):
        """fn.mul(2) works with map."""
        result = list(map(fn.mul(2), [1, 2, 3]))
        assert result == [2, 4, 6]

    def test_filter_gt(self):
        """fn.gt(0) works with filter."""
        result = list(filter(fn.gt(0), [-1, 0, 1, 2, -3]))
        assert result == [1, 2]

    def test_map_item(self):
        """fn.item('key') works with map."""
        data = [{'name': 'Alice'}, {'name': 'Bob'}]
        result = list(map(fn.item('name'), data))
        assert result == ['Alice', 'Bob']

    def test_map_upper(self):
        """fn.upper() works with map."""
        result = list(map(fn.upper(), ['hello', 'world']))
        assert result == ['HELLO', 'WORLD']


class TestFnWithPipe:
    """Tests for using fn with pipe operator."""

    def test_pipe_with_fn(self):
        """Fn methods work with | operator."""
        from klaw_core import Ok

        result = Ok(5) | fn.mul(2)
        assert result == Ok(10)

    def test_pipe_chain(self):
        """Multiple fn methods can be piped."""
        from klaw_core import Ok

        result = Ok('  hello  ') | fn.strip() | fn.upper()
        assert result == Ok('HELLO')


class TestFnPropertyBased:
    """Property-based tests for fn."""

    @given(st.integers(), st.integers())
    def test_add_correct(self, a: int, b: int):
        """fn.add(b)(a) == a + b."""
        add_b = fn.add(b)
        assert add_b(a) == a + b

    @given(st.integers())
    def test_identity_is_identity(self, n: int):
        """fn.identity()(n) == n."""
        assert fn.identity()(n) == n

    @given(st.integers(min_value=1, max_value=100))
    def test_double_half(self, n: int):
        """fn.mul(2) then fn.floordiv(2) == identity for positive ints."""
        doubled = fn.mul(2)(n)
        halved = fn.floordiv(2)(doubled)
        assert halved == n

    @given(st.text(alphabet=st.characters(max_codepoint=127), min_size=1))
    def test_upper_lower_preserves_casefold(self, s: str):
        """Upper then lower produces same casefold as original (ASCII only).

        Note: This property doesn't hold for all Unicode (e.g., Turkish ı).
        """
        result = fn.lower()(fn.upper()(s))
        assert result.casefold() == s.casefold()


class TestStream:
    """Tests for Stream fluent iterator."""

    def test_stream_basic(self):
        """Stream wraps iterable."""
        s = Stream([1, 2, 3])
        assert s.to_list() == [1, 2, 3]

    def test_stream_map(self):
        """Stream.map applies function."""
        result = Stream([1, 2, 3]).map(fn * 2).to_list()
        assert result == [2, 4, 6]

    def test_stream_filter(self):
        """Stream.filter keeps matching elements."""
        result = Stream([1, 2, 3, 4, 5]).filter(fn > 2).to_list()
        assert result == [3, 4, 5]

    def test_stream_chain_map_filter(self):
        """Stream.map().filter() chains correctly."""
        result = Stream([1, 2, 3]).map(fn * 2).filter(fn > 3).to_list()
        assert result == [4, 6]

    def test_stream_take(self):
        """Stream.take limits elements."""
        result = Stream(range(10)).take(3).to_list()
        assert result == [0, 1, 2]

    def test_stream_skip(self):
        """Stream.skip skips elements."""
        result = Stream(range(10)).skip(7).to_list()
        assert result == [7, 8, 9]

    def test_stream_take_while(self):
        """Stream.take_while stops at predicate."""
        result = Stream([1, 2, 3, 4, 5]).take_while(fn < 4).to_list()
        assert result == [1, 2, 3]

    def test_stream_drop_while(self):
        """Stream.drop_while skips until predicate fails."""
        result = Stream([1, 2, 3, 4, 5]).drop_while(fn < 3).to_list()
        assert result == [3, 4, 5]

    def test_stream_unique(self):
        """Stream.unique removes duplicates."""
        result = Stream([1, 2, 2, 3, 3, 3]).unique().to_list()
        assert result == [1, 2, 3]

    def test_stream_flatten(self):
        """Stream.flatten flattens one level."""
        result = Stream([[1, 2], [3, 4], [5]]).flatten().to_list()
        assert result == [1, 2, 3, 4, 5]

    def test_stream_batch(self):
        """Stream.batch splits into chunks."""
        result = Stream(range(7)).batch(3).to_list()
        assert result == [(0, 1, 2), (3, 4, 5), (6,)]

    def test_stream_sorted(self):
        """Stream.sorted sorts elements."""
        result = Stream([3, 1, 2]).sorted().to_list()
        assert result == [1, 2, 3]

    def test_stream_sorted_reverse(self):
        """Stream.sorted(reverse=True) sorts descending."""
        result = Stream([1, 2, 3]).sorted(reverse=True).to_list()
        assert result == [3, 2, 1]

    def test_stream_reversed(self):
        """Stream.reversed reverses elements."""
        result = Stream([1, 2, 3]).reversed().to_list()
        assert result == [3, 2, 1]

    def test_stream_enumerate(self):
        """Stream.enumerate adds indices."""
        result = Stream(['a', 'b']).enumerate().to_list()
        assert result == [(0, 'a'), (1, 'b')]

    def test_stream_zip(self):
        """Stream.zip zips with other iterables."""
        result = Stream([1, 2, 3]).zip(['a', 'b', 'c']).to_list()
        assert result == [(1, 'a'), (2, 'b'), (3, 'c')]

    def test_stream_chain(self):
        """Stream.chain concatenates iterables."""
        result = Stream([1, 2]).chain([3, 4]).to_list()
        assert result == [1, 2, 3, 4]

    def test_stream_sum(self):
        """Stream.sum sums elements."""
        assert Stream([1, 2, 3]).sum() == 6

    def test_stream_min(self):
        """Stream.min gets minimum."""
        assert Stream([3, 1, 2]).min() == 1

    def test_stream_max(self):
        """Stream.max gets maximum."""
        assert Stream([1, 3, 2]).max() == 3

    def test_stream_count(self):
        """Stream.count counts elements."""
        assert Stream([1, 2, 3, 4, 5]).count() == 5

    def test_stream_first(self):
        """Stream.first gets first element."""
        assert Stream([1, 2, 3]).first() == 1
        assert Stream([]).first() is None

    def test_stream_last(self):
        """Stream.last gets last element."""
        assert Stream([1, 2, 3]).last() == 3
        assert Stream([]).last() is None

    def test_stream_nth(self):
        """Stream.nth gets nth element."""
        assert Stream([1, 2, 3]).nth(1) == 2
        assert Stream([1, 2, 3]).nth(10) is None

    def test_stream_all(self):
        """Stream.all checks all truthy."""
        assert Stream([True, True]).all() is True
        assert Stream([True, False]).all() is False

    def test_stream_any(self):
        """Stream.any checks any truthy."""
        assert Stream([False, True]).any() is True
        assert Stream([False, False]).any() is False

    def test_stream_find(self):
        """Stream.find finds matching element."""
        assert Stream([1, 2, 3, 4]).find(fn > 2) == 3
        assert Stream([1, 2]).find(fn > 5) is None

    def test_stream_join(self):
        """Stream.join joins strings."""
        assert Stream(['a', 'b', 'c']).join(',') == 'a,b,c'

    def test_stream_reduce(self):
        """Stream.reduce reduces to single value."""
        result = Stream([1, 2, 3, 4]).reduce(lambda a, b: a + b)
        assert result == 10

    def test_stream_to_set(self):
        """Stream.to_set collects to set."""
        assert Stream([1, 2, 2, 3]).to_set() == {1, 2, 3}

    def test_stream_to_tuple(self):
        """Stream.to_tuple collects to tuple."""
        assert Stream([1, 2, 3]).to_tuple() == (1, 2, 3)

    def test_stream_to_dict(self):
        """Stream.to_dict collects pairs to dict."""
        assert Stream([('a', 1), ('b', 2)]).to_dict() == {'a': 1, 'b': 2}

    def test_stream_iterable(self):
        """Stream is iterable."""
        result = list(Stream([1, 2, 3]))
        assert result == [1, 2, 3]


class TestExprOver:
    """Tests for Expr.over() returning Stream."""

    def test_over_basic(self):
        """Expr.over() applies expr to iterable."""
        result = (fn * 2).over([1, 2, 3]).to_list()
        assert result == [2, 4, 6]

    def test_over_chain_filter(self):
        """Expr.over().filter() chains correctly."""
        result = (fn * 2).over([1, 2, 3]).filter(fn > 3).to_list()
        assert result == [4, 6]

    def test_over_chain_map(self):
        """Expr.over().map() chains correctly."""
        result = (fn + 1).over([1, 2, 3]).map(fn * 2).to_list()
        assert result == [4, 6, 8]

    def test_over_complex_chain(self):
        """Complex Expr.over() chain works."""
        result = (fn * 2).over([1, 2, 3, 4, 5]).filter(fn > 4).map(fn + 100).to_list()
        assert result == [106, 108, 110]

    def test_over_sum(self):
        """Expr.over().sum() works."""
        assert (fn * 2).over([1, 2, 3]).sum() == 12

    def test_over_find(self):
        """Expr.over().find() works."""
        assert (fn * 2).over([1, 2, 3, 4, 5]).find(fn > 5) == 6

    def test_identity_over(self):
        """fn.over() (identity) just wraps iterable."""
        result = fn.over([1, 2, 3]).to_list()
        assert result == [1, 2, 3]


class TestExprOptionResult:
    """Tests for Expr Option/Result integration."""

    def test_try_call_ok(self):
        """try_call returns Ok on success."""
        from klaw_core import Ok

        result = (fn / 2).try_call(10)
        assert result == Ok(5.0)

    def test_try_call_err(self):
        """try_call returns Err on exception."""
        result = (fn / 0).try_call(10)
        assert result.is_err()
        assert isinstance(result.error, ZeroDivisionError)

    def test_some(self):
        """Some wraps result in Some."""
        from klaw_core import Some

        result = (fn * 2).some(5)
        assert result == Some(10)

    def test_ok(self):
        """Ok wraps result in Ok."""
        from klaw_core import Ok

        result = (fn * 2).ok(5)
        assert result == Ok(10)

    def test_some_if_true(self):
        """some_if returns Some when predicate is True."""
        from klaw_core import Some

        positive = (fn * 2).some_if(fn > 0)
        assert positive(5) == Some(10)

    def test_some_if_false(self):
        """some_if returns Nothing when predicate is False."""
        from klaw_core import Nothing

        positive = (fn * 2).some_if(fn > 0)
        assert positive(-5) == Nothing


class TestStreamOptionResult:
    """Tests for Stream Option/Result integration."""

    def test_first_some(self):
        """first_some returns Some(first) or Nothing."""
        from klaw_core import Nothing, Some

        assert Stream([1, 2, 3]).first_some() == Some(1)
        assert Stream([]).first_some() == Nothing

    def test_last_some(self):
        """last_some returns Some(last) or Nothing."""
        from klaw_core import Nothing, Some

        assert Stream([1, 2, 3]).last_some() == Some(3)
        assert Stream([]).last_some() == Nothing

    def test_find_some(self):
        """find_some returns Some(match) or Nothing."""
        from klaw_core import Nothing, Some

        assert Stream([1, 2, 3, 4]).find_some(fn > 2) == Some(3)
        assert Stream([1, 2]).find_some(fn > 5) == Nothing

    def test_nth_some(self):
        """nth_some returns Some(nth) or Nothing."""
        from klaw_core import Nothing, Some

        assert Stream([1, 2, 3]).nth_some(1) == Some(2)
        assert Stream([1, 2]).nth_some(10) == Nothing

    def test_filter_some(self):
        """filter_some unwraps Some values, filters Nothing."""
        from klaw_core import Nothing, Some

        result = Stream([Some(1), Nothing, Some(2)]).filter_some().to_list()
        assert result == [1, 2]

    def test_filter_ok(self):
        """filter_ok unwraps Ok values, filters Err."""
        from klaw_core import Err, Ok

        result = Stream([Ok(1), Err('fail'), Ok(2)]).filter_ok().to_list()
        assert result == [1, 2]

    def test_collect_results_ok(self):
        """collect_results returns Ok(list) when all Ok."""
        from klaw_core import Ok

        result = Stream([Ok(1), Ok(2), Ok(3)]).collect_results()
        assert result == Ok([1, 2, 3])

    def test_collect_results_err(self):
        """collect_results returns first Err."""
        from klaw_core import Err, Ok

        result = Stream([Ok(1), Err('fail'), Ok(3)]).collect_results()
        assert result == Err('fail')

    def test_collect_options_some(self):
        """collect_options returns Some(list) when all Some."""
        from klaw_core import Some

        result = Stream([Some(1), Some(2)]).collect_options()
        assert result == Some([1, 2])

    def test_collect_options_nothing(self):
        """collect_options returns Nothing if any Nothing."""
        from klaw_core import Nothing, Some

        result = Stream([Some(1), Nothing]).collect_options()
        assert result == Nothing

    def test_try_reduce_ok(self):
        """try_reduce returns Ok on success."""
        from klaw_core import Ok

        result = Stream([1, 2, 3]).try_reduce(lambda a, b: a + b)
        assert result == Ok(6)

    def test_try_reduce_err(self):
        """try_reduce returns Err on exception."""
        result = Stream([]).try_reduce(lambda a, b: a + b)
        assert result.is_err()
        assert isinstance(result.error, TypeError)


class TestSelfReferentialExpr:
    """Tests for self-referential expressions (fn used multiple times)."""

    def test_fn_times_fn(self):
        """Fn * fn squares the input."""
        assert (fn * fn)(5) == 25
        assert (fn * fn)(3) == 9

    def test_fn_plus_fn(self):
        """Fn + fn doubles the input."""
        assert (fn + fn)(5) == 10
        assert (fn + fn)(7) == 14

    def test_fn_minus_divided_by_fn(self):
        """(fn - n) / fn works correctly."""
        expr = (fn - 10) / fn
        assert expr(20) == 0.5  # (20 - 10) / 20
        assert expr(50) == 0.8  # (50 - 10) / 50

    def test_fn_pow_fn(self):
        """Fn ** fn raises to self power."""
        assert (fn**fn)(2) == 4  # 2^2
        assert (fn**fn)(3) == 27  # 3^3

    def test_complex_self_ref(self):
        """Complex expressions with multiple fn refs."""
        expr = (fn * fn) + fn  # x^2 + x
        assert expr(3) == 12  # 9 + 3
        assert expr(5) == 30  # 25 + 5


class TestFnStreamFactories:
    """Tests for fn.iter(), fn.range(), etc."""

    def test_iter(self):
        """fn.iter() creates Stream from iterable."""
        result = fn.iter([1, 2, 3]).map(fn * 2).to_list()
        assert result == [2, 4, 6]

    def test_enumerate(self):
        """fn.enumerate() creates enumerated Stream."""
        assert fn.enumerate(['a', 'b', 'c']).to_list() == [(0, 'a'), (1, 'b'), (2, 'c')]
        assert fn.enumerate(['a', 'b'], start=1).to_list() == [(1, 'a'), (2, 'b')]

    def test_range(self):
        """fn.range() creates Stream from range."""
        assert fn.range(5).to_list() == [0, 1, 2, 3, 4]
        assert fn.range(1, 4).to_list() == [1, 2, 3]
        assert fn.range(0, 10, 2).to_list() == [0, 2, 4, 6, 8]

    def test_range_with_ops(self):
        """fn.range() with chained operations."""
        result = fn.range(1, 6).filter(fn % 2 == 0).to_list()
        assert result == [2, 4]

    def test_iterate(self):
        """fn.iterate() creates infinite stream by applying func."""
        result = fn.iterate(fn * 2, 1).take(5).to_list()
        assert result == [1, 2, 4, 8, 16]

    def test_repeat(self):
        """fn.repeat() repeats a value."""
        assert fn.repeat(42, 3).to_list() == [42, 42, 42]

    def test_counter(self):
        """fn.counter() creates counting stream."""
        assert fn.counter(10).take(5).to_list() == [10, 11, 12, 13, 14]
        assert fn.counter(0, 2).take(5).to_list() == [0, 2, 4, 6, 8]

    def test_cycle(self):
        """fn.cycle() cycles through iterable."""
        result = fn.cycle([1, 2, 3]).take(7).to_list()
        assert result == [1, 2, 3, 1, 2, 3, 1]

    def test_zip(self):
        """fn.zip() zips iterables."""
        result = fn.zip([1, 2], ['a', 'b']).to_list()
        assert result == [(1, 'a'), (2, 'b')]

    def test_chain(self):
        """fn.chain() chains iterables."""
        result = fn.chain([1, 2], [3, 4]).to_list()
        assert result == [1, 2, 3, 4]
