#!/bin/bash
set -e

echo "=========================================="
echo "  MemX Ollama 工业级测试脚本"
echo "  测试时间：$(date)"
echo "=========================================="

API_URL="${API_URL:-http://localhost:8000}"
PASSED=0
FAILED=0

check_service() {
    local name=$1
    local url=$2
    echo -n "检查${name}服务... "
    if curl -sf "${url}" > /dev/null 2>&1; then
        echo "✓ 通过"
        PASSED=$((PASSED + 1))
        return 0
    else
        echo "✗ 失败"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

run_test() {
    local name=$1
    local expected_code=$2
    local data=$3
    echo -n "测试${name}... "
    response=$(curl -sf -X POST "${API_URL}${data}" -H "Content-Type: application/json" 2>&1)
    if [ $? -eq 0 ]; then
        code=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('code', 'error'))" 2>/dev/null || echo "error")
        if [ "$code" = "$expected_code" ]; then
            echo "✓ 通过 (code=$code)"
            PASSED=$((PASSED + 1))
            return 0
        else
            echo "✗ 失败 (期望code=$expected_code, 实际code=$code)"
            FAILED=$((FAILED + 1))
            return 1
        fi
    else
        echo "✗ 失败 (请求错误)"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

echo ""
echo ">>> 第一阶段：服务健康检查"
echo "-------------------------------------------"
check_service "API健康检查" "${API_URL}/health"
check_service "API根路径" "${API_URL}/"
echo ""

echo ">>> 第二阶段：功能测试"
echo "-------------------------------------------"
run_test "聊天接口-正常请求" "0" "/chat" "-d '{\"user_id\":\"test_user\",\"prompt\":\"你好，测试对话\"}'"
run_test "聊天接口-空prompt" "400" "/chat" "-d '{\"user_id\":\"test_user\",\"prompt\":\"\"}'"
run_test "聊天接口-空user_id" "400" "/chat" "-d '{\"user_id\":\"\",\"prompt\":\"测试\"}'"
echo ""

echo ">>> 第三阶段：记忆功能测试"
echo "-------------------------------------------"
run_test "记忆搜索" "0" "/memory/search" "-d '{\"query\":\"测试\"}'"
run_test "会话列表" "0" "/memory/sessions/default"
echo ""

echo ">>> 第四阶段：性能测试"
echo "-------------------------------------------"
echo -n "并发测试 (10个请求)... "
start_time=$(date +%s%N)
for i in {1..10}; do
    curl -sf -X POST "${API_URL}/chat" -H "Content-Type: application/json" \
        -d "{\"user_id\":\"perf_user_${i}\",\"prompt\":\"性能测试${i}\"}" > /dev/null 2>&1 &
done
wait
end_time=$(date +%s%N)
duration=$(( (end_time - start_time) / 1000000 ))
echo "完成 (耗时: ${duration}ms)"
echo ""

echo "=========================================="
echo "  测试结果汇总"
echo "=========================================="
echo "通过: ${PASSED}"
echo "失败: ${FAILED}"
echo "总计: $((PASSED + FAILED))"

if [ $FAILED -eq 0 ]; then
    echo ""
    echo "🎉 所有测试通过！系统可以上线。"
    exit 0
else
    echo ""
    echo "⚠️  有测试失败，请检查日志。"
    exit 1
fi