#include <assert.h>
#include <stdio.h>
#include "spirv_ios.h"

/* Run against the prepared runtime header; exercises the native adapter's
 * binary parsing without requiring a device or executing shader code. */
int main(void)
{
    uint32_t module[] = {
        0x07230203, 0x00010000, 0, 20, 0,
        0x00040005, 7, 0x706d6173, 0x0072656c, /* OpName %7 "sampler" */
        0x00050006, 8, 0, 0x706d6173, 0x0072656c, /* OpMemberName */
        0x00050005, 9, 0x706d6173, 0x3272656c, 0, /* "sampler2": retain */
        0x0005000f, 4, 10, 0x6e69616d, 0, /* OpEntryPoint Fragment %10 "main" */
        0x00040047, 7, 33, 2, /* OpDecorate %7 Binding 2 */
        0x00010000 /* OpNop */
    };
    uint32_t expected[] = {
        0x07230203, 0x00010000, 0, 20, 0,
        0x00050005, 9, 0x706d6173, 0x3272656c, 0,
        0x0005000f, 4, 10, 0x6e69616d, 0,
        0x00040047, 7, 33, 2,
        0x00010000
    };
    size_t n = madeira_spirv_sanitize_names(module, sizeof(module) / 4);
    assert(n == sizeof(expected) / 4);
    assert(!memcmp(module, expected, sizeof(expected)));
    assert(madeira_spirv_sanitize_names(module, n) == n);

    /* A malformed instruction after a removable name must reject the whole
     * input before mutation, so the original can reach Vulkan validation. */
    uint32_t malformed[] = {
        0x07230203, 0x00010000, 0, 20, 0,
        0x00040005, 7, 0x706d6173, 0x0072656c,
        0x00040005
    };
    uint32_t original[sizeof(malformed) / 4];
    memcpy(original, malformed, sizeof(original));
    assert(madeira_spirv_sanitize_names(malformed, sizeof(malformed) / 4) == 0);
    assert(!memcmp(malformed, original, sizeof(original)));
    malformed[9] = 0;
    assert(madeira_spirv_sanitize_names(malformed, sizeof(malformed) / 4) == 0);
    assert(madeira_spirv_sanitize_names(module, 4) == 0);
    module[0] = 0;
    assert(madeira_spirv_sanitize_names(module, n) == 0);
    puts("SPIR-V adapter checks passed");
}
