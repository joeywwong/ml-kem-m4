/* Test harness only. Cryptography is provided by the unmodified upstream. */
#include <stdint.h>
#include <string.h>
#include "mlkem_native.h"
#include "test_coins.h"
#ifdef HOST_VERIFY
#include <stdio.h>
#else
#include "expected_secrets.h"
#endif

static uint8_t pk[MLKEM768_PUBLICKEYBYTES], sk[MLKEM768_SECRETKEYBYTES];
static uint8_t ct[MLKEM768_CIPHERTEXTBYTES];
static uint8_t sender[32], receiver[32], rejected[32], repeated[32];

#ifndef HOST_VERIFY
#define REG32(a) (*(volatile uint32_t *)(a))
struct report {
    uint32_t magic, version, status, completed, failure, level, samples, stack_bytes;
    uint32_t rcc_cr, rcc_cfgr, flash_acr, cpuid, dwt_ctrl, clock_hz, reserved[2];
    uint32_t cycles[SAMPLE_COUNT][3];
};
volatile struct report results __attribute__((section(".results"), used));
extern uint32_t _stack_bottom, _stack_top;
static uint32_t ticks(void) {
    __asm__ volatile ("dsb\nisb" ::: "memory");
    return REG32(0xE0001004);
}
#else
static uint32_t ticks(void) { return 0; }
static void hex(const uint8_t *p, unsigned n) {
    unsigned i;
    for (i = 0; i < n; ++i) printf("%02x", p[i]);
}
#endif

static int one_case(unsigned i, uint32_t cycles[3]) {
    uint32_t before;
    int rc;
    uint8_t saved0, saved1;
    before = ticks();
    rc = mlkem_keypair_derand(pk, sk, test_coins[i]);
    cycles[0] = ticks() - before;
    if (rc != 0) return 1;
    before = ticks();
    rc = mlkem_enc_derand(ct, sender, pk, test_coins[i] + 64);
    cycles[1] = ticks() - before;
    if (rc != 0) return 2;
    before = ticks();
    rc = mlkem_dec(receiver, ct, sk);
    cycles[2] = ticks() - before;
    if (rc != 0 || memcmp(sender, receiver, 32)) return 3;
    /* Full-length ciphertext mutation: success + deterministic fallback secret. */
    ct[i % sizeof(ct)] ^= 1;
    if (mlkem_dec(rejected, ct, sk) != 0) return 4;
    if (mlkem_dec(repeated, ct, sk) != 0) return 5;
    if (!memcmp(sender, rejected, 32) || memcmp(rejected, repeated, 32)) return 6;
#ifdef HOST_VERIFY
    printf("{\"sample\":%u,\"shared\":\"", i); hex(sender, 32);
    printf("\",\"rejected\":\""); hex(rejected, 32);
    printf("\",\"mutated_ct\":\""); hex(ct, sizeof(ct)); puts("\"}");
#else
    if (memcmp(sender, expected_secrets[i], 32) ||
        memcmp(rejected, expected_secrets[i] + 32, 32)) return 7;
#endif
    /* A public-key coefficient 4095 fails the modulus check. */
    saved0 = pk[0]; saved1 = pk[1]; pk[0] = 255; pk[1] |= 15;
    rc = mlkem_enc_derand(ct, receiver, pk, test_coins[i] + 64);
    pk[0] = saved0; pk[1] = saved1;
    if (rc != MLK_ERR_INVALID_PK) return 8;
    /* Corrupt the embedded public-key hash, not merely private-key noise. */
    sk[sizeof(sk) - 64] ^= 1;
    if (mlkem_dec(receiver, ct, sk) != MLK_ERR_INVALID_SK) return 9;
    return 0;
}

int main(void) {
    unsigned i;
    uint32_t cycles[3];
    int rc;
#ifndef HOST_VERIFY
    uint32_t *p;
    REG32(0xE000ED08) = 0x08000000; /* VTOR */
    REG32(0xE000EDFC) |= 1u << 24; /* trace enable */
    REG32(0xE0001004) = 0;
    REG32(0xE0001000) |= 1; /* DWT CYCCNT */
    /* .results is NOLOAD and is not cleared with BSS on reset. */
    results.reserved[0] = 0;
    results.reserved[1] = 0;
    results.magic = 0x4D4C4B45;
    results.version = 1; results.status = 1; results.completed = 0;
    results.failure = 0; results.level = 768; results.samples = SAMPLE_COUNT;
    results.rcc_cr = REG32(0x40023800); results.rcc_cfgr = REG32(0x40023808);
    results.flash_acr = REG32(0x40023C00); results.cpuid = REG32(0xE000ED00);
    results.dwt_ctrl = REG32(0xE0001000); results.clock_hz = 16000000;
    /* Require reset clock tree: HSI16, AHB /1, PLL off, zero flash wait states. */
    if ((results.rcc_cfgr & 0xFC) || (results.rcc_cr & (1u << 24)) ||
        (results.flash_acr & 7) || ticks() == 0) {
        results.failure = 10; results.status = 3; for (;;) {}
    }
#endif
    for (i = 0; i < SAMPLE_COUNT; ++i) {
        cycles[0] = cycles[1] = cycles[2] = 0;
        rc = one_case(i, cycles);
#ifdef HOST_VERIFY
        if (rc) { fprintf(stderr, "FAIL sample=%u code=%d\n", i, rc); return rc; }
#else
        results.cycles[i][0] = cycles[0]; results.cycles[i][1] = cycles[1];
        results.cycles[i][2] = cycles[2];
        if (rc) { results.failure = (uint32_t)rc; results.status = 3; for (;;) {} }
        results.completed = i + 1;
#endif
    }
#ifdef HOST_VERIFY
    return 0;
#else
    p = &_stack_bottom;
    while (p < &_stack_top && *p == 0xA5A5A5A5) ++p;
    results.stack_bytes = (uint32_t)((uintptr_t)&_stack_top - (uintptr_t)p);
    __asm__ volatile ("dsb" ::: "memory");
    results.status = 2;
    for (;;) { __asm__ volatile ("nop"); }
#endif
}
