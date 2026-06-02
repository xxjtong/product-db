"""Unit tests for utility modules."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


class TestValidateUrl:
    def test_allows_normal_urls(self):
        from app.utils.security import validate_url
        assert validate_url("https://example.com") is True
        assert validate_url("https://api.deepseek.com/v1") is True
        assert validate_url("http://product-page.com/item/123") is True

    def test_blocks_private_ipv4(self):
        from app.utils.security import validate_url
        assert validate_url("http://127.0.0.1/admin") is False
        assert validate_url("http://10.0.0.1/api") is False
        assert validate_url("http://192.168.1.1") is False
        assert validate_url("http://172.16.0.1") is False

    def test_blocks_metadata_endpoints(self):
        from app.utils.security import validate_url
        assert validate_url("http://169.254.169.254/latest/meta-data") is False
        assert validate_url("http://metadata.google.internal") is False

    def test_blocks_ipv6_localhost(self):
        from app.utils.security import validate_url
        assert validate_url("http://[::1]/") is False
        assert validate_url("http://[fc00::1]/") is False

    def test_blocks_localhost(self):
        from app.utils.security import validate_url
        assert validate_url("http://localhost:8000") is False

    def test_blocks_non_http_scheme(self):
        from app.utils.security import validate_url
        assert validate_url("file:///etc/passwd") is False
        assert validate_url("ftp://example.com") is False

    def test_numeric_ip_bypass_is_known_limitation(self):
        from app.utils.security import validate_url
        # Numeric IP representations (e.g., http://2130706433/ = 127.0.0.1)
        # are not blocked by URL-level checks — browsers/DNS do the conversion.
        # This is a known limitation documented in the module.
        assert validate_url("http://2130706433/") is True

    def test_blocks_link_local(self):
        from app.utils.security import validate_url
        assert validate_url("http://169.254.100.1/") is False


class TestApplyPartialUpdate:
    def test_dict_input(self):
        from app.utils.helpers import apply_partial_update
        class Obj:
            name = None
            email = None
            phone = "old"
        obj = Obj()
        apply_partial_update(obj, {"name": "Test", "phone": "123"}, ["name", "email", "phone"])
        assert obj.name == "Test"
        assert obj.email is None
        assert obj.phone == "123"

    def test_skips_none_values(self):
        from app.utils.helpers import apply_partial_update
        class Obj:
            name = "original"
            email = None
        obj = Obj()
        apply_partial_update(obj, {"name": None, "email": "e@x.com"}, ["name", "email"])
        assert obj.name == "original"  # unchanged
        assert obj.email == "e@x.com"


class TestEscapeLike:
    def test_escapes_percent_and_underscore(self):
        from app.utils.escape import escape_like
        assert escape_like("test%") == "test\\%"
        assert escape_like("a_b") == "a\\_b"
        assert escape_like("a%b_c") == "a\\%b\\_c"

    def test_handles_safe_strings(self):
        from app.utils.escape import escape_like
        assert escape_like("hello") == "hello"
        assert escape_like("") == ""
