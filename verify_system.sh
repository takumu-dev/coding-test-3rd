#!/bin/bash

# System Verification Script
# Runs 13 manual tests to verify all functionality

echo "=================================="
echo "Fund Performance System Verification"
echo "=================================="
echo ""

PASSED=0
FAILED=0

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test function
test_endpoint() {
    local test_name="$1"
    local command="$2"
    local expected="$3"
    
    echo -n "Test $((PASSED + FAILED + 1)): $test_name... "
    
    result=$(eval "$command" 2>&1)
    
    if echo "$result" | grep -q "$expected"; then
        echo -e "${GREEN}PASS${NC}"
        ((PASSED++))
    else
        echo -e "${RED}FAIL${NC}"
        echo "  Expected: $expected"
        echo "  Got: $result"
        ((FAILED++))
    fi
}

echo "Starting tests..."
echo ""

# Test 1: Backend Health Check
test_endpoint "Backend Health Check" \
    "curl -s http://localhost:8000/health" \
    "healthy"

# Test 2: List All Funds
test_endpoint "List All Funds" \
    "curl -s http://localhost:8000/api/funds/" \
    "Sample Venture Fund I"

# Test 3: Get Specific Fund
test_endpoint "Get Specific Fund" \
    "curl -s http://localhost:8000/api/funds/1" \
    "Sample Venture Fund I"

# Test 4: Get Fund Metrics
test_endpoint "Get Fund Metrics" \
    "curl -s http://localhost:8000/api/funds/1/metrics" \
    "dpi"

# Test 5: Get Capital Calls
test_endpoint "Get Capital Calls" \
    "curl -s 'http://localhost:8000/api/funds/1/transactions?transaction_type=capital_calls&limit=3'" \
    "call_date"

# Test 6: Get Distributions
test_endpoint "Get Distributions" \
    "curl -s 'http://localhost:8000/api/funds/1/transactions?transaction_type=distributions&limit=3'" \
    "distribution_date"

# Test 7: Check Document Status
test_endpoint "Check Document Status" \
    "curl -s http://localhost:8000/api/documents/7/status" \
    "completed"

# Test 8: Verify Database Tables
test_endpoint "Verify Database Tables" \
    "docker compose exec -T postgres psql -U funduser -d funddb -c '\dt' 2>/dev/null | grep -c 'document_embeddings'" \
    "1"

# Test 9: Check Vector Embeddings Count
test_endpoint "Check Vector Embeddings" \
    "docker compose exec -T postgres psql -U funduser -d funddb -c 'SELECT COUNT(*) FROM document_embeddings WHERE fund_id = 1;' 2>/dev/null | grep -oP '\d+' | head -1" \
    "3"

# Test 10: Verify Capital Calls Count
test_endpoint "Verify Capital Calls Count" \
    "docker compose exec -T postgres psql -U funduser -d funddb -c 'SELECT COUNT(*) FROM capital_calls WHERE fund_id = 1;' 2>/dev/null | grep -oP '\d+' | head -1" \
    "1"

# Test 11: Verify Distributions Count
test_endpoint "Verify Distributions Count" \
    "docker compose exec -T postgres psql -U funduser -d funddb -c 'SELECT COUNT(*) FROM distributions WHERE fund_id = 1;' 2>/dev/null | grep -oP '\d+' | head -1" \
    "4"

# Test 12: Check Docker Services
test_endpoint "Check Docker Services" \
    "docker compose ps 2>/dev/null | grep -c 'Up'" \
    "4"

# Test 13: API Root Endpoint
test_endpoint "API Root Endpoint" \
    "curl -s http://localhost:8000/" \
    "Fund Performance Analysis System API"

echo ""
echo "=================================="
echo "Test Results:"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo "Total: $((PASSED + FAILED))"
echo "=================================="

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed${NC}"
    exit 1
fi
