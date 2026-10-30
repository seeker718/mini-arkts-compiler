/* ==== 由 Mini-ArkTS 编译器自动生成（实验三 Mock-C） ==== */
/* ================= Mini-ArkTS 运行时桩（模拟鸿蒙 API 调用约定） ================= */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

typedef double      ark_number;
typedef const char* ark_string;
typedef int         ark_bool;

static ark_string ark_str_concat(ark_string a, ark_string b) {
    size_t la = strlen(a), lb = strlen(b);
    char *r = (char *)malloc(la + lb + 1);
    memcpy(r, a, la);
    memcpy(r + la, b, lb + 1);
    return r;
}

static ark_string ark_str_of_number(ark_number n) {
    static char buf[64];
    snprintf(buf, sizeof(buf), "%g", n);
    return buf;
}

static void ark_console_log_number(ark_number n) { printf("%g\n", n); }
static void ark_console_log_string(ark_string s) { printf("%s\n", s); }

#define ARK_TRUE  1
#define ARK_FALSE 0



/* 可跨设备执行（device=1），由 RPC Skeleton 调用 */
static ark_number ark_square(ark_number v_p0_x) {
    ark_number v_t1;
L_entry:
    v_t1 = v_p0_x * v_p0_x;
    return v_t1;
}

/* 可跨设备执行（device=2），由 RPC Skeleton 调用 */
static ark_number ark_sumTo(ark_number v_p0_n) {
    ark_number v_total;
    ark_number v_i;
    ark_number v_t1;
    ark_number v_t2;
    ark_number v_total_2;
    ark_number v_t3;
    ark_number v_i_2;
L_entry:
    v_total = 0;
    v_i = 1;
    goto L_while_cond_1;
L_while_cond_1:
    v_t1 = v_i <= v_p0_n;
    if (v_t1) { goto L_while_body_2; } else { goto L_while_end_3; }
L_while_body_2:
    v_t2 = v_total + v_i;
    v_total_2 = v_t2;
    v_t3 = v_i + 1;
    v_i_2 = v_t3;
    goto L_while_cond_1;
L_while_end_3:
    return v_total_2;
}

/* 可跨设备执行（device=3），由 RPC Skeleton 调用 */
static ark_number ark_classify(ark_number v_p0_value) {
    ark_number v_result;
    ark_number v_t1;
    ark_number v_result_2;
    ark_number v_t2;
    ark_number v_result_3;
    ark_number v_result_4;
L_entry:
    v_result = 1;
    v_t1 = v_p0_value > 100;
    if (v_t1) { goto L_if_then_1; } else { goto L_if_else_2; }
L_if_then_1:
    v_result_2 = 2;
    v_result_4 = v_result_2;
    goto L_if_end_3;
L_if_else_2:
    v_t2 = v_result + 0;
    v_result_3 = v_t2;
    v_result_4 = v_result_3;
    goto L_if_end_3;
L_if_end_3:
    return v_result_4;
}

/* 可跨设备执行（device=1），由 RPC Skeleton 调用 */
static ark_number ark_demo() {
    ark_number v_n;
    ark_number v_t1;
    ark_number v_sq;
    ark_number v_t2;
    ark_number v_s;
    ark_number v_t3;
    ark_number v_c;
    ark_number v_t4;
    ark_number v_t5;
L_entry:
    v_n = 10;
    v_t1 = ark_square(v_n);
    v_sq = v_t1;
    v_t2 = ark_sumTo(v_n);
    v_s = v_t2;
    v_t3 = ark_classify(v_s);
    v_c = v_t3;
    v_t4 = v_sq + v_s;
    v_t5 = v_t4 + v_c;
    return v_t5;
}

int main(void) {
    ark_console_log_number(ark_demo());
    return 0;
}

/* ============ 分布式软总线：RPC 桩（Stub / Skeleton） ============ */
typedef struct {
    int    from_device;
    int    to_device;
    char   func[64];
    double args[8];
    int    argc;
    double result;
} ArkRpcEnvelope;

/* 模拟分布式软总线发送：本实验直接本地调用，等价于网络透传 */
static ArkRpcEnvelope ark_softbus_send(ArkRpcEnvelope env) {
    printf("[softbus] device %d -> device %d : %s\n",
           env.from_device, env.to_device, env.func);
    return env;
}

/* ---- square：可跨设备执行（目标 device=1）---- */
/* Skeleton：部署在远端设备 1 上，真正执行计算 */
static double ark_square_skeleton(double a0) {
    return ark_square(a0);
}

/* Stub：部署在本机侧，打包参数 -> 经软总线发送 -> 取回结果 */
static double ark_square_stub(int target_device, double a0) {
    ArkRpcEnvelope env;
    memset(&env, 0, sizeof(env));
    env.from_device = 0;
    env.to_device = target_device;
snprintf(env.func, sizeof(env.func), "%s", "square");
    env.args[0] = a0;
    env.argc = 1;
    env.result = ark_square_skeleton(a0);
    env = ark_softbus_send(env);
    return env.result;
}

/* ---- sumTo：可跨设备执行（目标 device=2）---- */
/* Skeleton：部署在远端设备 2 上，真正执行计算 */
static double ark_sumTo_skeleton(double a0) {
    return ark_sumTo(a0);
}

/* Stub：部署在本机侧，打包参数 -> 经软总线发送 -> 取回结果 */
static double ark_sumTo_stub(int target_device, double a0) {
    ArkRpcEnvelope env;
    memset(&env, 0, sizeof(env));
    env.from_device = 0;
    env.to_device = target_device;
snprintf(env.func, sizeof(env.func), "%s", "sumTo");
    env.args[0] = a0;
    env.argc = 1;
    env.result = ark_sumTo_skeleton(a0);
    env = ark_softbus_send(env);
    return env.result;
}

/* ---- classify：可跨设备执行（目标 device=3）---- */
/* Skeleton：部署在远端设备 3 上，真正执行计算 */
static double ark_classify_skeleton(double a0) {
    return ark_classify(a0);
}

/* Stub：部署在本机侧，打包参数 -> 经软总线发送 -> 取回结果 */
static double ark_classify_stub(int target_device, double a0) {
    ArkRpcEnvelope env;
    memset(&env, 0, sizeof(env));
    env.from_device = 0;
    env.to_device = target_device;
snprintf(env.func, sizeof(env.func), "%s", "classify");
    env.args[0] = a0;
    env.argc = 1;
    env.result = ark_classify_skeleton(a0);
    env = ark_softbus_send(env);
    return env.result;
}

/* ---- demo：可跨设备执行（目标 device=1）---- */
/* Skeleton：部署在远端设备 1 上，真正执行计算 */
static double ark_demo_skeleton(void) {
    return ark_demo();
}

/* Stub：部署在本机侧，打包参数 -> 经软总线发送 -> 取回结果 */
static double ark_demo_stub(int target_device) {
    ArkRpcEnvelope env;
    memset(&env, 0, sizeof(env));
    env.from_device = 0;
    env.to_device = target_device;
snprintf(env.func, sizeof(env.func), "%s", "demo");
    env.argc = 0;
    env.result = ark_demo_skeleton();
    env = ark_softbus_send(env);
    return env.result;
}
