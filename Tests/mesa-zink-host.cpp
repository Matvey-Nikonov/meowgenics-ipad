// Host fixture for actual Mesa functions inserted by test-mesa-zink.py.
// The shims below describe data and record calls; IO and pipeline decisions
// come exclusively from the supplied production source.
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#define BITFIELD_MASK(n) ((1u << (n)) - 1u)
#define BITFIELD_RANGE(frac, n) (BITFIELD_MASK(n) << (frac))
#define DIV_ROUND_UP(n, d) (((n) + (d) - 1) / (d))
#define MAX2(a, b) std::max((a), (b))
#define ASSERTED
#define u_foreach_bit64(slot, mask) \
    for (unsigned slot = 0; slot < 64; ++slot) if ((mask) & (UINT64_C(1) << slot))
enum gl_shader_stage {
    MESA_SHADER_VERTEX, MESA_SHADER_FRAGMENT, MESA_SHADER_GEOMETRY,
    MESA_SHADER_TESS_CTRL, MESA_SHADER_TESS_EVAL, MESA_SHADER_NONE
};
enum nir_variable_mode { nir_var_shader_in = 1, nir_var_shader_out = 2 };
using nir_alu_type = unsigned;
constexpr unsigned nir_type_float = 0x100, nir_type_int = 0x200,
    nir_type_uint = 0x400, nir_type_bool = 0x800;
constexpr unsigned VARYING_SLOT_POS = 0, VARYING_SLOT_PRIMITIVE_ID = 1,
    VARYING_SLOT_TESS_LEVEL_INNER = 2, VARYING_SLOT_TESS_LEVEL_OUTER = 3,
    VARYING_SLOT_VAR0 = 32, VARYING_SLOT_VAR31 = 63, VARYING_SLOT_PATCH0 = 64;
constexpr unsigned INTERP_MODE_FLAT = 1, nir_metadata_all = 0;
constexpr unsigned ZINK_DEBUG_NIR = 1, ZINK_DEBUG_SPIRV = 2;
static unsigned zink_debug = 0;
struct glsl_type {
    unsigned base, components, length = 0;
    const glsl_type *element = nullptr;
};
struct nir_variable {
    const glsl_type *type;
    struct {
        nir_variable_mode mode;
        unsigned location = 0, location_frac = 0, driver_location = 0;
        bool fb_fetch_output = false, index = false, compact = false;
        bool patch = false, precision = false;
        unsigned interpolation = 0;
    } data;
    bool arrayed = false;
};
struct nir_src { unsigned bit_size = 32; bool constant = true; };
struct nir_io_semantics {
    unsigned location = 0, num_slots = 1;
    bool medium_precision = false, fb_fetch_output = false;
    bool dual_source_blend_index = false;
};
struct nir_intrinsic_instr {
    unsigned num_components = 0, component = 0, write_mask = 0, base = 0;
    bool load = true, input = true, arrayed = false;
    const char *name = nullptr;
    nir_io_semantics sem;
    struct { unsigned bit_size = 32; } def;
    nir_src src[1], offset;
    nir_alu_type type = nir_type_float | 32;
};
struct nir_builder {};
struct nir_shader {
    struct { gl_shader_stage stage; struct { unsigned vertices_in = 3; } gs; } info;
    std::vector<nir_variable *> vars;
    std::vector<nir_intrinsic_instr> instructions;
};
#define nir_foreach_variable_with_modes(var, nir, modes) \
    for (auto *var : (nir)->vars) if ((var->data.mode & (modes)) != 0)
static bool nir_is_arrayed_io(nir_variable *v, gl_shader_stage) { return v->arrayed; }
static const glsl_type *glsl_get_array_element(const glsl_type *t) { return t->element; }
static unsigned glsl_array_size(const glsl_type *t) { return t->length; }
static const glsl_type *glsl_without_array(const glsl_type *t) {
    while (t->element) t = t->element;
    return t;
}
static unsigned glsl_count_attribute_slots(const glsl_type *t, bool) {
    return t->element ? t->length * glsl_count_attribute_slots(t->element, false) : 1;
}
static unsigned glsl_get_vector_elements(const glsl_type *t) { return t->components; }
static bool glsl_type_contains_64bit(const glsl_type *t) { return (t->base & 0xff) == 64; }
static unsigned nir_get_glsl_base_type_for_nir_type(nir_alu_type type) { return type; }
static unsigned glsl_get_explicit_stride(const glsl_type *) { return 0; }
static const glsl_type *glsl_vector_type(unsigned base, unsigned components) {
    return new glsl_type{base, components};
}
static const glsl_type *glsl_array_type(const glsl_type *t, unsigned n, unsigned) {
    return new glsl_type{t->base, t->components, n, t};
}
static nir_variable *nir_variable_create(nir_shader *s, nir_variable_mode mode,
                                         const glsl_type *t, const char *) {
    auto *v = new nir_variable{t, {.mode = mode}};
    s->vars.push_back(v);
    return v;
}
static bool nir_slot_is_sysval_output(unsigned slot, gl_shader_stage) {
    return slot < VARYING_SLOT_VAR0;
}
static const char *gl_vert_attrib_name(unsigned) { return "attribute"; }
static const char *gl_frag_result_name(unsigned) { return "result"; }
static const char *gl_varying_slot_name_for_stage(unsigned, gl_shader_stage) { return "builtin"; }
static bool is_clipcull_dist(unsigned) { return false; }
static char *ralloc_asprintf(void *, const char *, ...) { std::abort(); }
static char *ralloc_strdup(void *, const char *s) { return strdup(s); }
static bool filter_io_instr(nir_intrinsic_instr *i, bool *load, bool *input, bool *interp) {
    *load = i->load; *input = i->input; *interp = i->load && i->input;
    return true;
}
static bool io_instr_is_arrayed(nir_intrinsic_instr *i) { return i->arrayed; }
static nir_io_semantics nir_intrinsic_io_semantics(nir_intrinsic_instr *i) { return i->sem; }
static unsigned nir_intrinsic_component(nir_intrinsic_instr *i) { return i->component; }
static unsigned nir_intrinsic_write_mask(nir_intrinsic_instr *i) { return i->write_mask; }
static unsigned nir_intrinsic_base(nir_intrinsic_instr *i) { return i->base; }
static unsigned nir_src_bit_size(nir_src s) { return s.bit_size; }
static unsigned nir_intrinsic_dest_type(nir_intrinsic_instr *i) { return i->type; }
static unsigned nir_intrinsic_src_type(nir_intrinsic_instr *i) { return i->type; }
static nir_src *nir_get_io_offset_src(nir_intrinsic_instr *i) { return &i->offset; }
static bool nir_src_is_const(nir_src s) { return s.constant; }
static unsigned util_last_bit(unsigned n) { return n ? 32 - __builtin_clz(n) : 0; }
static void nir_shader_intrinsics_pass(nir_shader *s,
    bool (*callback)(nir_builder *, nir_intrinsic_instr *, void *), unsigned, void *data) {
    nir_builder b;
    for (auto &i : s->instructions) callback(&b, &i, data);
}

// INSERT_ACTUAL_IO_FUNCTIONS

enum zink_dynamic_state { ZINK_NO_DYNAMIC_STATE };
enum mesa_prim { MESA_PRIM_TRIANGLES };
using VkPipeline = uintptr_t;
using VkShaderStageFlagBits = unsigned;
constexpr VkPipeline VK_NULL_HANDLE = 0;
constexpr unsigned VK_PIPELINE_BIND_POINT_GRAPHICS = 0, VK_TRUE = 1;
constexpr unsigned VK_SHADER_STAGE_VERTEX_BIT = 1, VK_SHADER_STAGE_TESSELLATION_CONTROL_BIT = 2,
    VK_SHADER_STAGE_TESSELLATION_EVALUATION_BIT = 4, VK_SHADER_STAGE_GEOMETRY_BIT = 8,
    VK_SHADER_STAGE_FRAGMENT_BIT = 16, ZINK_GFX_SHADER_COUNT = 5;
constexpr unsigned VK_TESSELLATION_DOMAIN_ORIGIN_LOWER_LEFT = 0;
struct zink_screen {
    bool optimal_keys = false;
    struct { bool have_EXT_graphics_pipeline_library = false; } info;
};
struct zink_program { struct { bool uses_shobj = false; } base; unsigned objects[5]{}; };
struct zink_pipeline_state { VkPipeline pipeline = 0; bool sample_locations_enabled = false; };
struct zink_context {
    struct { struct zink_screen *screen; } base;
    zink_pipeline_state gfx_pipeline_state;
    zink_program *curr_program;
    bool gfx_dirty = false, dirty_gfx_stages = false, is_generated_gs_bound = false;
    bool shobj_draw = false, vp_state_changed = false;
};
struct zink_batch_state { unsigned cmdbuf = 0; };
static struct zink_screen *zink_screen(struct zink_screen *s) { return s; }
static void zink_gfx_program_update_optimal(zink_context *) {}
static void zink_gfx_program_update(zink_context *) {}
static VkPipeline next_pipeline;
static unsigned bind_pipeline_calls, bind_shaders_calls, draw_calls;
template <zink_dynamic_state, bool>
static VkPipeline zink_get_gfx_pipeline(zink_context *, zink_program *,
                                       zink_pipeline_state *state, mesa_prim) {
    // On failure leave stale state behind: the production guard must clear it.
    if (next_pipeline) state->pipeline = next_pipeline;
    return next_pipeline;
}
#define VKCTX(name) fake_##name
static void fake_CmdBindPipeline(unsigned, unsigned, VkPipeline p) {
    assert(p != VK_NULL_HANDLE); ++bind_pipeline_calls;
}
static void fake_CmdBindShadersEXT(unsigned, unsigned, VkShaderStageFlagBits *, unsigned *) {
    ++bind_shaders_calls;
}
static void fake_CmdSetDepthBiasEnable(unsigned, unsigned) {}
static void fake_CmdSetTessellationDomainOriginEXT(unsigned, unsigned) {}
static void fake_CmdSetSampleLocationsEnableEXT(unsigned, bool) {}
static void fake_CmdSetRasterizationStreamEXT(unsigned, unsigned) {}

// INSERT_ACTUAL_PIPELINE_FUNCTION

template <zink_dynamic_state DYNAMIC_STATE, bool BATCH_CHANGED>
static void draw_with_actual_guard(zink_context *ctx, zink_batch_state *bs, mesa_prim mode) {
// INSERT_ACTUAL_DRAW_GUARD
    ++draw_calls;
}

static nir_intrinsic_instr io(unsigned location, unsigned start, unsigned count,
                             bool load = true) {
    nir_intrinsic_instr i;
    i.sem.location = location;
    i.component = start;
    i.num_components = count;
    i.write_mask = BITFIELD_MASK(count);
    i.load = i.input = load;
    return i;
}
static unsigned cases;
static void check(bool value, const char *what) {
    if (!value) { std::fprintf(stderr, "FAIL: %s\n", what); std::exit(1); }
    ++cases;
}
static void reconstruct(nir_shader &s, nir_variable_mode mode, unsigned location,
                        bool moltenvk) {
    loop_io_var_mask(&s, mode, false, false, UINT64_C(1) << location, moltenvk);
}
static void test_io() {
    for (unsigned location : {VARYING_SLOT_VAR0 + 2, VARYING_SLOT_VAR0 + 3}) {
        nir_shader fs{.info = {.stage = MESA_SHADER_FRAGMENT}};
        fs.instructions = {io(location, 0, 2), io(location, 3, 1)};
        auto scan = scan_io_var_slot(&fs, nir_var_shader_in, location, false, true);
        check(scan.component_mask == 0xb && scan.ignored_component_mask == 0,
              "Scan merges both disjoint loads");
        reconstruct(fs, nir_var_shader_in, location, true);
        check(fs.vars.size() == 1, "MoltenVK merges split .xy/.w fragment input");
        check(fs.vars[0]->data.location_frac == 0 && fs.vars[0]->type->components == 4,
              "Merged fragment input is vec4 at component zero");
        nir_shader vs{.info = {.stage = MESA_SHADER_VERTEX}};
        vs.instructions = {io(location, 0, 4, false)};
        reconstruct(vs, nir_var_shader_out, location, true);
        check(vs.vars.size() == 1 && vs.vars[0]->type->components == fs.vars[0]->type->components &&
              vs.vars[0]->data.location_frac == fs.vars[0]->data.location_frac,
              "Vertex and fragment reconstructed interfaces match");
        nir_shader other{.info = {.stage = MESA_SHADER_FRAGMENT}};
        other.instructions = fs.instructions;
        reconstruct(other, nir_var_shader_in, location, false);
        check(other.vars.size() == 2 && other.vars[0]->type->components == 2 &&
              other.vars[1]->type->components == 1 && other.vars[1]->data.location_frac == 3,
              "Other Vulkan drivers preserve split varying behavior");
        nir_shader reversed{.info = {.stage = MESA_SHADER_FRAGMENT}};
        reversed.instructions = {io(location, 3, 1), io(location, 0, 2)};
        reconstruct(reversed, nir_var_shader_in, location, true);
        check(reversed.vars.size() == 1 && reversed.vars[0]->type->components == 4 &&
              reversed.vars[0]->data.location_frac == 0,
              "Varying interface is independent of intrinsic order");
    }
    const unsigned location = VARYING_SLOT_VAR0 + 4;
    nir_shader lone{.info = {.stage = MESA_SHADER_FRAGMENT}};
    lone.instructions = {io(location, 3, 1)};
    reconstruct(lone, nir_var_shader_in, location, true);
    check(lone.vars.size() == 1 && lone.vars[0]->data.location_frac == 0 &&
          lone.vars[0]->type->components == 4, "Single .w fragment read receives full vec4 interface");
    nir_shader vertex{.info = {.stage = MESA_SHADER_VERTEX}};
    vertex.instructions = {io(location, 0, 2, false)};
    reconstruct(vertex, nir_var_shader_out, location, true);
    check(vertex.vars[0]->type->components == 4, "Partial vertex outputs expand to vec4");

    for (unsigned scenario = 0; scenario < 7; ++scenario) {
        nir_shader s{.info = {.stage = MESA_SHADER_FRAGMENT}};
        s.instructions = {io(location, 0, 2), io(location, 3, 1)};
        unsigned slot = location;
        auto mode = nir_var_shader_in;
        if (scenario == 0) {
            slot = VARYING_SLOT_PRIMITIVE_ID;
            for (auto &i : s.instructions) i.sem.location = slot;
        } else if (scenario == 1) {
            for (auto &i : s.instructions) {
                i.def.bit_size = 16;
                i.type = nir_type_float | 16;
            }
        } else if (scenario == 2) {
            for (auto &i : s.instructions) i.sem.num_slots = 2;
        } else if (scenario == 3) {
            for (auto &i : s.instructions) i.arrayed = true;
        } else if (scenario == 4) {
            for (auto &i : s.instructions) i.sem.fb_fetch_output = true;
        } else if (scenario == 5) {
            s.info.stage = MESA_SHADER_VERTEX;
        } else {
            mode = nir_var_shader_out;
            for (auto &i : s.instructions) i.load = i.input = false;
        }
        reconstruct(s, mode, slot, true);
        check(s.vars.size() == 2 && glsl_without_array(s.vars[0]->type)->components == 2 &&
              s.vars[1]->data.location_frac == 3,
              "Builtins, narrow types, arrays, framebuffer fetch and other stages stay unchanged");
    }
}
static void test_pipeline() {
    struct zink_screen screen;
    zink_program program;
    zink_context ctx{.base = {.screen = &screen}, .curr_program = &program};
    zink_batch_state bs;
    for (bool gpl : {false, true}) {
        screen.info.have_EXT_graphics_pipeline_library = gpl;
        ctx.gfx_pipeline_state.pipeline = 17;
        next_pipeline = 0;
        bind_shaders_calls = bind_pipeline_calls = draw_calls = 0;
        draw_with_actual_guard<ZINK_NO_DYNAMIC_STATE, true>(&ctx, &bs, MESA_PRIM_TRIANGLES);
        check(bind_shaders_calls == 0, "Pipeline failure cannot call unsupported shader-object entry point");
        check(bind_pipeline_calls == 0 && draw_calls == 0,
              "Pipeline failure cannot bind NULL or submit with a stale pipeline");
        next_pipeline = 29;
        draw_with_actual_guard<ZINK_NO_DYNAMIC_STATE, true>(&ctx, &bs, MESA_PRIM_TRIANGLES);
        check(bind_pipeline_calls == 1 && bind_shaders_calls == 0 && draw_calls == 1,
              "A valid subsequent pipeline recovers and draws normally");
    }
    program.base.uses_shobj = true;
    ctx.gfx_pipeline_state.pipeline = 0;
    bind_shaders_calls = bind_pipeline_calls = draw_calls = 0;
    draw_with_actual_guard<ZINK_NO_DYNAMIC_STATE, true>(&ctx, &bs, MESA_PRIM_TRIANGLES);
    check(bind_shaders_calls == 1 && bind_pipeline_calls == 0 && draw_calls == 1,
          "Supported shader-object path is not accidentally disabled");
}
int main() {
    test_io();
    test_pipeline();
    std::printf("PASS: %u assertions using extracted production Mesa functions\n", cases);
}
