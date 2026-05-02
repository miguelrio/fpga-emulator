import pytest
from sim.fib import ForwardingTable


def test_ipv4_default_route(fib):
    result = fib.lookup("203.0.114.1")  # not in any specific route
    assert result is not None  # should hit default 0.0.0.0/0


def test_ipv4_specific_route_preferred(fib):
    result = fib.lookup("192.168.1.5")
    assert result is not None
    # Should prefer /24 over /16
    assert result.prefix_len == 24


def test_ipv4_exact_network(fib):
    result = fib.lookup("10.0.0.50")
    assert result is not None
    assert "10.0.0.0" in result.network or result.prefix_len <= 8


def test_ipv6_default_route(fib):
    result = fib.lookup("2c00::1")  # not in any specific route
    assert result is not None  # default ::/0


def test_ipv6_specific(fib):
    result = fib.lookup("2001:db8::1")
    assert result is not None
    assert result.prefix_len >= 32


def test_lookup_invalid_ip(fib):
    result = fib.lookup("not_an_ip")
    assert result is None


def test_add_route_and_lookup(fib):
    fib.add_route("99.0.0.0/8", "99.0.0.1", "eth9")
    result = fib.lookup("99.1.2.3")
    assert result is not None
    assert result.next_hop == "99.0.0.1"
    assert result.interface == "eth9"


def test_lpm_more_specific_wins(fib):
    fib.add_route("172.16.5.0/24", "172.16.5.1", "eth_specific")
    result = fib.lookup("172.16.5.10")
    assert result is not None
    assert result.prefix_len == 24


def test_loopback_ipv6(fib):
    result = fib.lookup("::1")
    assert result is not None
    assert result.interface == "lo"
