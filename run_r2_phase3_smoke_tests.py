#!/usr/bin/env python3
"""
R2 Phase 3 Smoke Test Suite
Executes all four smoke test suites against staging environment.
"""

import asyncio
import json
import time
from datetime import datetime
from uuid import uuid4

import httpx

# ============================================================================
# CONFIGURATION
# ============================================================================

STAGING_URL = "https://relay-production-f2a6.up.railway.app"
API_BASE = f"{STAGING_URL}/api/v1"

# Test user JWTs (7-day TTL)
JWT_A = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhbm9uXzA5ZmFmZmMyLWFmN2UtNDA1MS1iMjdmLTM3MTUxOTdiZjViMiIsInVzZXJfaWQiOiJhbm9uXzA5ZmFmZmMyLWFmN2UtNDA1MS1iMjdmLTM3MTUxOTdiZjViMiIsImFub24iOnRydWUsInNpZCI6IjA5ZmFmZmMyLWFmN2UtNDA1MS1iMjdmLTM3MTUxOTdiZjViMiIsImlhdCI6MTc2MTk5ODQwMywiZXhwIjoxNzYyNjAzMjAzfQ.SoVXwKIowJCO-Prvog9HtdNTK4k_3WLV_o8U8DpTMyo"
JWT_B = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhbm9uXzc1YTE1NmJlLWI0NTYtNDQ5ZS05YWNiLWRkMmI5N2Y2YTI5NCIsInVzZXJfaWQiOiJhbm9uXzc1YTE1NmJlLWI0NTYtNDQ5ZS05YWNiLWRkMmI5N2Y2YTI5NCIsImFub24iOnRydWUsInNpZCI6Ijc1YTE1NmJlLWI0NTYtNDQ5ZS05YWNiLWRkMmI5N2Y2YTI5NCIsImlhdCI6MTc2MTk5ODQwMywiZXhwIjoxNzYyNjAzMjAzfQ.lbSJpbH09CuvBoewjtI3hC-erbkp9WQtWGLT6DoAj60"

# ============================================================================
# RESULTS TRACKING
# ============================================================================

test_results = {
    "timestamp": datetime.utcnow().isoformat() + "Z",
    "staging_url": STAGING_URL,
    "environment": "STAGING",
    "tests": {
        "health": {},
        "cross_tenant_isolation": {},
        "per_user_rate_limiting": {},
        "jwt_enforcement": {},
        "security_headers": {},
    },
    "metrics": {
        "query_latency_p95_ms": 0,
        "index_operation_total": 0,
        "security_rls_missing_total": 0,
    },
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def check_health() -> bool:
    """Check if staging endpoint is responding."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{STAGING_URL}/ready")
            if response.status_code == 200:
                data = response.json()
                test_results["tests"]["health"]["status"] = "PASS"
                test_results["tests"]["health"]["checks"] = data.get("checks", {})
                return True
            else:
                test_results["tests"]["health"]["status"] = "FAIL"
                test_results["tests"]["health"]["error"] = f"Status {response.status_code}"
                return False
    except Exception as e:
        test_results["tests"]["health"]["status"] = "FAIL"
        test_results["tests"]["health"]["error"] = str(e)
        return False


def add_request_id_header(headers: dict) -> dict:
    """Add X-Request-ID header for tracing."""
    headers["X-Request-ID"] = str(uuid4())
    return headers


def validate_rate_limit_headers(headers: dict) -> dict:
    """Validate and return rate limit headers."""
    return {
        "x_ratelimit_limit": headers.get("x-ratelimit-limit"),
        "x_ratelimit_remaining": headers.get("x-ratelimit-remaining"),
        "x_ratelimit_reset": headers.get("x-ratelimit-reset"),
        "retry_after": headers.get("retry-after"),
        "x_request_id": headers.get("x-request-id"),
    }


# ============================================================================
# TEST SUITE 1: CROSS-TENANT ISOLATION
# ============================================================================


async def test_cross_tenant_isolation():
    """
    User A uploads file.
    User B searches - should get 0 results.
    Result: RLS working - cross-tenant access blocked.
    """
    print("\n=== TEST 1: Cross-Tenant Isolation ===")

    test_data = {
        "user_a_upload": None,
        "user_b_search_empty": False,
        "rls_working": False,
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # User A uploads test file
            print("  Step 1: User A uploads file...")
            headers = {"Authorization": f"Bearer {JWT_A}"}
            headers = add_request_id_header(headers)

            # Create a simple test file
            file_content = b"Test document for User A - confidential data"
            files = {"file": ("test_user_a.txt", file_content, "text/plain")}

            response = await client.post(
                f"{API_BASE}/knowledge/upload",
                headers=headers,
                files=files,
            )

            if response.status_code in (200, 202):
                test_data["user_a_upload"] = response.status_code
                print(f"    OK: Status {response.status_code}")
                # Store response time for latency metric
                start_time = time.time()
            else:
                test_data["errors"].append(f"User A upload failed: {response.status_code} {response.text[:100]}")
                print(f"    FAIL: {response.status_code}")

            # User B searches (should get no results)
            print("  Step 2: User B searches for User A's file...")
            headers_b = {"Authorization": f"Bearer {JWT_B}"}
            headers_b = add_request_id_header(headers_b)

            search_payload = {"query": "test_user_a", "top_k": 10}

            response = await client.post(
                f"{API_BASE}/knowledge/search",
                json=search_payload,
                headers=headers_b,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                data = response.json()
                results_count = len(data.get("results", []))
                if results_count == 0:
                    test_data["user_b_search_empty"] = True
                    test_data["rls_working"] = True
                    print("    OK: User B got 0 results (RLS enforced)")
                else:
                    test_data["errors"].append(
                        f"SECURITY VIOLATION: User B saw {results_count} results from User A's file"
                    )
                    print(f"    FAIL: User B got {results_count} results (RLS NOT enforced)")
            else:
                test_data["errors"].append(f"User B search failed: {response.status_code}")
                print(f"    FAIL: {response.status_code}")

            # Store latency
            test_results["metrics"]["query_latency_p95_ms"] = latency_ms

        except Exception as e:
            test_data["errors"].append(f"Exception: {str(e)}")
            print(f"    ERROR: {e}")

    test_results["tests"]["cross_tenant_isolation"] = test_data
    verdict = "PASS" if test_data["rls_working"] else "FAIL"
    print(f"  VERDICT: {verdict}")
    return test_data["rls_working"]


# ============================================================================
# TEST SUITE 2: PER-USER RATE LIMITING
# ============================================================================


async def test_per_user_rate_limiting():
    """
    User A makes 101 rapid requests (limit = 100/hour).
    Requests 1-100: Should all return 200 OK
    Request 101: Should return 429 Too Many Requests
    User B makes 1 request - should succeed (User A's limit doesn't affect B).
    """
    print("\n=== TEST 2: Per-User Rate Limiting ===")

    test_data = {
        "user_a_requests_1_to_100": 0,
        "user_a_request_101_status": None,
        "user_a_request_101_headers": {},
        "user_b_request_status": None,
        "per_user_isolation": False,
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # User A makes rapid requests
            print("  Step 1: User A makes 101 rapid requests...")
            headers_a = {"Authorization": f"Bearer {JWT_A}"}

            success_count = 0
            for i in range(101):
                headers_a = add_request_id_header(headers_a)
                search_payload = {"query": f"test_query_{i}", "top_k": 5}

                response = await client.post(
                    f"{API_BASE}/knowledge/search",
                    json=search_payload,
                    headers=headers_a,
                    timeout=5.0,
                )

                if i < 100:
                    if response.status_code == 200:
                        success_count += 1
                    else:
                        test_data["errors"].append(f"Request {i+1} failed unexpectedly: {response.status_code}")
                else:
                    # Request 101 - should be 429
                    test_data["user_a_request_101_status"] = response.status_code
                    test_data["user_a_request_101_headers"] = validate_rate_limit_headers(response.headers)

                    if response.status_code == 429:
                        print(f"    Request 1-100: {success_count}/100 OK")
                        print(f"    Request 101: Status {response.status_code} (rate limited as expected)")
                        rl_headers = response.headers
                        print(
                            f"    Headers: Remaining={rl_headers.get('x-ratelimit-remaining')}, "
                            f"Retry-After={rl_headers.get('retry-after')}s"
                        )
                    else:
                        test_data["errors"].append(f"Request 101 was NOT rate limited: {response.status_code}")
                        print(f"    FAIL: Request 101 should be 429, got {response.status_code}")

            test_data["user_a_requests_1_to_100"] = success_count

            # User B makes 1 request
            print("  Step 2: User B makes 1 request (should NOT be affected by User A's limit)...")
            headers_b = {"Authorization": f"Bearer {JWT_B}"}
            headers_b = add_request_id_header(headers_b)

            search_payload = {"query": "user_b_test", "top_k": 5}
            response = await client.post(
                f"{API_BASE}/knowledge/search",
                json=search_payload,
                headers=headers_b,
                timeout=5.0,
            )

            test_data["user_b_request_status"] = response.status_code
            if response.status_code == 200:
                print(f"    OK: User B got {response.status_code} (not affected by User A's limit)")
                test_data["per_user_isolation"] = True
            else:
                test_data["errors"].append(f"User B request failed: {response.status_code}")
                print(f"    FAIL: User B got {response.status_code}")

        except Exception as e:
            test_data["errors"].append(f"Exception: {str(e)}")
            print(f"    ERROR: {e}")

    test_results["tests"]["per_user_rate_limiting"] = test_data
    verdict = (
        "PASS"
        if (
            test_data["user_a_requests_1_to_100"] >= 95
            and test_data["user_a_request_101_status"] == 429
            and test_data["per_user_isolation"]
        )
        else "FAIL"
    )
    print(f"  VERDICT: {verdict}")
    return verdict == "PASS"


# ============================================================================
# TEST SUITE 3: JWT ENFORCEMENT
# ============================================================================


async def test_jwt_enforcement():
    """
    Request WITHOUT JWT token: Expected 401
    Request with INVALID JWT token: Expected 401
    Request with JWT_A (valid): Expected 200 OK
    """
    print("\n=== TEST 3: JWT Enforcement ===")

    test_data = {
        "no_jwt_status": None,
        "invalid_jwt_status": None,
        "valid_jwt_status": None,
        "jwt_enforced": False,
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            search_payload = {"query": "test", "top_k": 5}

            # Test 1: No JWT
            print("  Step 1: Request WITHOUT JWT...")
            response = await client.post(
                f"{API_BASE}/knowledge/search",
                json=search_payload,
                timeout=5.0,
            )
            test_data["no_jwt_status"] = response.status_code
            if response.status_code == 401:
                print("    OK: Got 401 (JWT required)")
            else:
                test_data["errors"].append(f"No JWT should return 401, got {response.status_code}")
                print(f"    FAIL: Expected 401, got {response.status_code}")

            # Test 2: Invalid JWT
            print("  Step 2: Request with INVALID JWT...")
            headers = {"Authorization": "Bearer invalid.jwt.token"}
            response = await client.post(
                f"{API_BASE}/knowledge/search",
                json=search_payload,
                headers=headers,
                timeout=5.0,
            )
            test_data["invalid_jwt_status"] = response.status_code
            if response.status_code == 401:
                print("    OK: Got 401 (invalid JWT rejected)")
            else:
                test_data["errors"].append(f"Invalid JWT should return 401, got {response.status_code}")
                print(f"    FAIL: Expected 401, got {response.status_code}")

            # Test 3: Valid JWT
            print("  Step 3: Request with VALID JWT...")
            headers = {"Authorization": f"Bearer {JWT_A}"}
            headers = add_request_id_header(headers)
            response = await client.post(
                f"{API_BASE}/knowledge/search",
                json=search_payload,
                headers=headers,
                timeout=5.0,
            )
            test_data["valid_jwt_status"] = response.status_code
            if response.status_code == 200:
                print("    OK: Got 200 (JWT accepted)")
                test_data["jwt_enforced"] = True
            else:
                test_data["errors"].append(f"Valid JWT should return 200, got {response.status_code}")
                print(f"    FAIL: Expected 200, got {response.status_code}")

        except Exception as e:
            test_data["errors"].append(f"Exception: {str(e)}")
            print(f"    ERROR: {e}")

    test_results["tests"]["jwt_enforcement"] = test_data
    verdict = (
        "PASS"
        if (test_data["no_jwt_status"] == 401 and test_data["invalid_jwt_status"] == 401 and test_data["jwt_enforced"])
        else "FAIL"
    )
    print(f"  VERDICT: {verdict}")
    return verdict == "PASS"


# ============================================================================
# TEST SUITE 4: SECURITY HEADERS
# ============================================================================


async def test_security_headers():
    """
    All successful responses from User A and User B MUST include:
    - X-Request-ID header (unique per request)
    - X-RateLimit-* headers (per-user keyed)
    """
    print("\n=== TEST 4: Security Headers ===")

    test_data = {
        "user_a_headers": {},
        "user_b_headers": {},
        "all_headers_present": False,
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # User A request with X-Request-ID
            print("  Step 1: User A request headers...")
            headers_a = {"Authorization": f"Bearer {JWT_A}"}
            request_id_a = str(uuid4())
            headers_a["X-Request-ID"] = request_id_a

            search_payload = {"query": "header_test", "top_k": 5}
            response = await client.post(
                f"{API_BASE}/knowledge/search",
                json=search_payload,
                headers=headers_a,
                timeout=5.0,
            )

            if response.status_code == 200:
                response_headers = response.headers
                headers_present = {
                    "x_request_id": "x-request-id" in response_headers,
                    "x_ratelimit_limit": "x-ratelimit-limit" in response_headers,
                    "x_ratelimit_remaining": "x-ratelimit-remaining" in response_headers,
                    "x_ratelimit_reset": "x-ratelimit-reset" in response_headers,
                    "retry_after": "retry-after" in response_headers,
                }
                test_data["user_a_headers"] = {
                    "present": headers_present,
                    "values": validate_rate_limit_headers(response_headers),
                }
                print(f"    X-Request-ID: {'OK' if headers_present['x_request_id'] else 'MISSING'}")
                print(f"    X-RateLimit-Limit: {'OK' if headers_present['x_ratelimit_limit'] else 'MISSING'}")
                print(f"    X-RateLimit-Remaining: {'OK' if headers_present['x_ratelimit_remaining'] else 'MISSING'}")
                print(f"    X-RateLimit-Reset: {'OK' if headers_present['x_ratelimit_reset'] else 'MISSING'}")
            else:
                test_data["errors"].append(f"User A request failed: {response.status_code}")
                print(f"    FAIL: {response.status_code}")

            # User B request
            print("  Step 2: User B request headers...")
            headers_b = {"Authorization": f"Bearer {JWT_B}"}
            request_id_b = str(uuid4())
            headers_b["X-Request-ID"] = request_id_b

            response = await client.post(
                f"{API_BASE}/knowledge/search",
                json=search_payload,
                headers=headers_b,
                timeout=5.0,
            )

            if response.status_code == 200:
                response_headers = response.headers
                headers_present = {
                    "x_request_id": "x-request-id" in response_headers,
                    "x_ratelimit_limit": "x-ratelimit-limit" in response_headers,
                    "x_ratelimit_remaining": "x-ratelimit-remaining" in response_headers,
                    "x_ratelimit_reset": "x-ratelimit-reset" in response_headers,
                    "retry_after": "retry-after" in response_headers,
                }
                test_data["user_b_headers"] = {
                    "present": headers_present,
                    "values": validate_rate_limit_headers(response_headers),
                }
                print(f"    X-Request-ID: {'OK' if headers_present['x_request_id'] else 'MISSING'}")
                print(f"    X-RateLimit-Limit: {'OK' if headers_present['x_ratelimit_limit'] else 'MISSING'}")
                print(f"    X-RateLimit-Remaining: {'OK' if headers_present['x_ratelimit_remaining'] else 'MISSING'}")

                # Verify per-user keying
                if (
                    test_data["user_a_headers"]["values"]["x_ratelimit_remaining"]
                    != test_data["user_b_headers"]["values"]["x_ratelimit_remaining"]
                ):
                    print("    Per-user rate limit state: OK (different remaining counts)")
                    test_data["all_headers_present"] = all(
                        [
                            headers_present["x_request_id"],
                            headers_present["x_ratelimit_limit"],
                            headers_present["x_ratelimit_remaining"],
                            headers_present["x_ratelimit_reset"],
                        ]
                    )
            else:
                test_data["errors"].append(f"User B request failed: {response.status_code}")
                print(f"    FAIL: {response.status_code}")

        except Exception as e:
            test_data["errors"].append(f"Exception: {str(e)}")
            print(f"    ERROR: {e}")

    test_results["tests"]["security_headers"] = test_data
    verdict = "PASS" if test_data["all_headers_present"] else "FAIL"
    print(f"  VERDICT: {verdict}")
    return verdict == "PASS"


# ============================================================================
# MAIN EXECUTION
# ============================================================================


async def main():
    """Run all smoke tests."""
    print("\n" + "=" * 80)
    print("R2 Phase 3 - Knowledge API Smoke Tests")
    print("=" * 80)
    print(f"Staging URL: {STAGING_URL}")
    print(f"Timestamp: {test_results['timestamp']}")

    # Check health first
    print("\n=== HEALTH CHECK ===")
    health_ok = await check_health()
    if not health_ok:
        print("ERROR: Staging environment not healthy. Cannot proceed with tests.")
        print(json.dumps(test_results, indent=2))
        return False

    print("OK: Staging environment is healthy")

    # Run test suites
    results = [
        await test_cross_tenant_isolation(),
        await test_per_user_rate_limiting(),
        await test_jwt_enforcement(),
        await test_security_headers(),
    ]

    # Final verdict
    print("\n" + "=" * 80)
    print("SMOKE TEST SUMMARY")
    print("=" * 80)

    all_pass = all(results)
    print(f"\n  Cross-Tenant Isolation:   {'PASS' if results[0] else 'FAIL'}")
    print(f"  Per-User Rate Limiting:   {'PASS' if results[1] else 'FAIL'}")
    print(f"  JWT Enforcement:          {'PASS' if results[2] else 'FAIL'}")
    print(f"  Security Headers:         {'PASS' if results[3] else 'FAIL'}")

    print(f"\n  OVERALL: {'✅ ALL TESTS PASS' if all_pass else '❌ SOME TESTS FAILED'}")
    print("=" * 80)

    # Save results
    print("\nTest results JSON:")
    print(json.dumps(test_results, indent=2))

    return all_pass


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
