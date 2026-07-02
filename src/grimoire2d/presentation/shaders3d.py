"""Embedded GLSL shaders for the 3D renderer.

All shaders target GLSL 3.30 core (matching the OpenGL 3.30 core profile
required throughout Grimoire2D).

Programs:

PHONG  — full Phong lighting: ambient + directional + up to 24 point lights
         + up to 4 spot lights, with optional specular, fog, shadow mapping,
         and texture sampling.

WIRE   — single solid color, no lighting.  Wireframe draw calls.

SHADOW — depth-only pass from the directional light's POV (shadow map).

SKY    — procedural gradient sky rendered before scene geometry.
         Covers the screen via a single covering triangle (gl_VertexID);
         reconstructs world-space ray directions from the inverse VP matrices
         to blend zenith / horizon / ground colours.

BLIT   — final post-processing blit from the intermediate scene FBO to the
         screen.  Applies gamma correction and brightness in a single pass.
         Additional post-processing passes (bloom, FXAA, …) are composited
         before or after this pass as separate programs.
"""

# ---------------------------------------------------------------------------
# Phong — vertex
# ---------------------------------------------------------------------------

PHONG_VERT = """
#version 330 core

in vec3 in_pos;
in vec3 in_normal;
in vec2 in_uv;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
// Inverse-transpose of the model matrix for correct normal transformation
// under non-uniform scaling.  Passed as mat4; shader casts to mat3.
uniform mat4 u_model_inv_t;

out vec3 v_world_pos;
out vec3 v_normal;
out vec2 v_uv;

void main() {
    vec4 world = u_model * vec4(in_pos, 1.0);
    v_world_pos = world.xyz;
    v_normal    = normalize(mat3(u_model_inv_t) * in_normal);
    v_uv        = in_uv;
    gl_Position = u_proj * u_view * world;
}
"""

# ---------------------------------------------------------------------------
# Phong — fragment
# ---------------------------------------------------------------------------

PHONG_FRAG = """
#version 330 core

in vec3 v_world_pos;
in vec3 v_normal;
in vec2 v_uv;

// Surface
uniform vec4      u_color;
uniform bool      u_use_texture;
uniform sampler2D u_albedo;       // bound to texture unit 0

// Camera
uniform vec3 u_cam_pos;

// Ambient
uniform vec3 u_ambient_color;

// Directional light (single sun/moon)
uniform bool  u_dir_light_on;
uniform vec3  u_dir_light_dir;    // direction light *travels* (toward surfaces)
uniform vec3  u_dir_light_color;

// Point lights — parallel arrays, max 24
// Array uniforms must be uploaded to the base name (not "u_pl_pos[0]") on
// macOS/Metal.  The `if (i < count)` guard (not `break`) keeps all slots
// nominally reachable so the driver does not prune them at link time.
uniform int   u_num_point_lights;
uniform vec3  u_pl_pos[24];
uniform vec3  u_pl_color[24];
uniform float u_pl_radius[24];
uniform float u_pl_intensity[24];

// Spot lights — parallel arrays, max 4
uniform int   u_num_spot_lights;
uniform vec3  u_sl_pos[4];
uniform vec3  u_sl_dir[4];        // direction cone points (world space)
uniform vec3  u_sl_color[4];
uniform float u_sl_intensity[4];
uniform float u_sl_radius[4];
uniform float u_sl_inner_cos[4];  // cos(inner_angle) — full brightness inside
uniform float u_sl_outer_cos[4];  // cos(outer_angle) — zero brightness outside

// Runtime effect toggles
uniform bool  u_specular_on;
uniform bool  u_fog_on;
uniform vec3  u_fog_color;
uniform float u_fog_near;
uniform float u_fog_far;

// Shadow map (directional light only)
uniform sampler2D u_shadow_map;   // bound to texture unit 1
uniform mat4      u_light_space;  // light_proj * light_view
uniform bool      u_shadows_on;

out vec4 frag_color;

float spec_blinn(vec3 N, vec3 L, vec3 V, float shininess) {
    vec3 H = normalize(L + V);
    return pow(max(dot(N, H), 0.0), shininess);
}

// PCF 3x3 shadow lookup.  Returns 1.0 = fully lit, 0.0 = fully shadowed.
float compute_shadow(vec3 world_pos, float NdL) {
    vec4 lspos = u_light_space * vec4(world_pos, 1.0);
    vec3 proj  = lspos.xyz / lspos.w * 0.5 + 0.5;
    // Fragment outside the shadow frustum — treat as lit
    if (proj.x < 0.0 || proj.x > 1.0 ||
        proj.y < 0.0 || proj.y > 1.0 || proj.z > 1.0)
        return 1.0;
    // Slope-scaled bias: steeper surfaces get more bias to avoid acne
    float bias  = max(0.003 * (1.0 - NdL), 0.0005);
    vec2  texel = 1.0 / vec2(textureSize(u_shadow_map, 0));
    float s = 0.0;
    for (int x = -1; x <= 1; x++) {
        for (int y = -1; y <= 1; y++) {
            float d = texture(u_shadow_map, proj.xy + vec2(x, y) * texel).r;
            s += (proj.z - bias) > d ? 1.0 : 0.0;
        }
    }
    return 1.0 - s / 9.0;
}

void main() {
    vec4 base = u_use_texture ? texture(u_albedo, v_uv) : u_color;
    if (base.a < 0.01) discard;

    vec3 N = normalize(v_normal);
    vec3 V = normalize(u_cam_pos - v_world_pos);

    vec3 light_acc = u_ambient_color;

    // Directional light — shadow only attenuates this term
    if (u_dir_light_on) {
        vec3  L      = normalize(-u_dir_light_dir);
        float NdL    = max(dot(N, L), 0.0);
        float shadow = u_shadows_on ? compute_shadow(v_world_pos, NdL) : 1.0;
        light_acc += shadow * u_dir_light_color * NdL;
        if (u_specular_on)
            light_acc += shadow * u_dir_light_color * spec_blinn(N, L, V, 64.0) * 0.35;
    }

    // Point lights
    for (int i = 0; i < 24; i++) {
        if (i < u_num_point_lights) {
            vec3  to_light = u_pl_pos[i] - v_world_pos;
            float dist     = length(to_light);
            vec3  L        = normalize(to_light);
            float atten    = clamp(1.0 - (dist / u_pl_radius[i]), 0.0, 1.0);
            atten          = atten * atten;
            float NdL      = max(dot(N, L), 0.0);
            light_acc += u_pl_color[i] * u_pl_intensity[i] * NdL * atten;
            if (u_specular_on)
                light_acc += u_pl_color[i] * spec_blinn(N, L, V, 128.0) * atten * 0.5;
        }
    }

    // Spot lights — cone falloff with smooth inner/outer transition
    for (int i = 0; i < 4; i++) {
        if (i < u_num_spot_lights) {
            vec3  to_light  = u_sl_pos[i] - v_world_pos;
            float dist      = length(to_light);
            if (dist < u_sl_radius[i]) {
                vec3  L         = normalize(to_light);
                float cos_theta = dot(-L, normalize(u_sl_dir[i]));
                float cone = smoothstep(u_sl_outer_cos[i], u_sl_inner_cos[i], cos_theta);
                if (cone > 0.0) {
                    float atten = clamp(1.0 - dist / u_sl_radius[i], 0.0, 1.0);
                    atten       = atten * atten;
                    float NdL   = max(dot(N, L), 0.0);
                    light_acc  += u_sl_color[i] * u_sl_intensity[i] * NdL * atten * cone;
                    if (u_specular_on)
                        light_acc += u_sl_color[i] * u_sl_intensity[i]
                                   * spec_blinn(N, L, V, 64.0) * atten * cone * 0.5;
                }
            }
        }
    }

    vec3 result = light_acc * base.rgb;

    if (u_fog_on) {
        float cam_dist = length(u_cam_pos - v_world_pos);
        float fog_f    = clamp((cam_dist - u_fog_near) / (u_fog_far - u_fog_near), 0.0, 1.0);
        result         = mix(result, u_fog_color, fog_f);
    }

    frag_color = vec4(result, base.a);
}
"""

# ---------------------------------------------------------------------------
# Wireframe — vertex  (no lighting, position only)
# ---------------------------------------------------------------------------

WIRE_VERT = """
#version 330 core

in vec3 in_pos;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;

void main() {
    gl_Position = u_proj * u_view * u_model * vec4(in_pos, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Wireframe — fragment
# ---------------------------------------------------------------------------

WIRE_FRAG = """
#version 330 core

uniform vec4 u_color;
out vec4 frag_color;

void main() {
    frag_color = u_color;
}
"""

# ---------------------------------------------------------------------------
# Shadow map — depth-only pass from directional light's POV
# ---------------------------------------------------------------------------

SHADOW_VERT = """
#version 330 core

in vec3 in_pos;

uniform mat4 u_model;
uniform mat4 u_light_view;
uniform mat4 u_light_proj;

void main() {
    gl_Position = u_light_proj * u_light_view * u_model * vec4(in_pos, 1.0);
}
"""

SHADOW_FRAG = """
#version 330 core
void main() {}
"""

# ---------------------------------------------------------------------------
# Sky — procedural gradient, rendered before scene geometry
# ---------------------------------------------------------------------------

SKY_VERT = """
#version 330 core

out vec2 v_ndc;

void main() {
    // Emit a large triangle that covers the entire NDC space without any VBO.
    // gl_VertexID selects from three hardcoded positions:
    //   0 → (-1, -1)    1 → (3, -1)    2 → (-1, 3)
    vec2 pos = vec2(
        float((gl_VertexID & 1) * 2) * 2.0 - 1.0,
        float((gl_VertexID >> 1) * 2) * 2.0 - 1.0
    );
    v_ndc       = pos;
    gl_Position = vec4(pos, 0.9999, 1.0);
}
"""

SKY_FRAG = """
#version 330 core

in vec2 v_ndc;

uniform mat4 u_inv_proj;
uniform mat4 u_inv_view;
uniform vec3 u_sky_zenith;
uniform vec3 u_sky_horizon;
uniform vec3 u_sky_ground;

out vec4 frag_color;

void main() {
    // Unproject NDC → view-space direction → world-space direction
    vec4 clip     = vec4(v_ndc, -1.0, 1.0);
    vec4 view_dir = u_inv_proj * clip;
    view_dir      = vec4(view_dir.xy, -1.0, 0.0);   // treat as direction
    vec3 world    = normalize((u_inv_view * view_dir).xyz);

    // world.y: +1 = straight up (zenith), 0 = horizon, -1 = straight down
    float t = clamp(world.y, -1.0, 1.0);
    vec3 color;
    if (t >= 0.0) {
        // horizon → zenith: gentle power curve for more sky blue at top
        color = mix(u_sky_horizon, u_sky_zenith, pow(t, 0.6));
    } else {
        // horizon → ground: linear, compressed to bottom quarter of view
        color = mix(u_sky_horizon, u_sky_ground, clamp(-t * 3.0, 0.0, 1.0));
    }
    frag_color = vec4(color, 1.0);
}
"""

# ---------------------------------------------------------------------------
# Post-processing blit — gamma correction + brightness
# ---------------------------------------------------------------------------
# Covering triangle via gl_VertexID (no VBO).  UVs map [−1,1] NDC to [0,1].
# Additional post-processing passes plug in before this final blit.

BLIT_VERT = """
#version 330 core

out vec2 v_uv;

void main() {
    vec2 pos = vec2(
        float((gl_VertexID & 1) * 2) * 2.0 - 1.0,
        float((gl_VertexID >> 1) * 2) * 2.0 - 1.0
    );
    v_uv        = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

BLIT_FRAG = """
#version 330 core

in vec2 v_uv;

uniform sampler2D u_scene;
uniform float     u_brightness;
uniform float     u_gamma;

out vec4 frag_color;

void main() {
    vec3 color = texture(u_scene, v_uv).rgb;
    color      = clamp(color * u_brightness, 0.0, 1.0);
    // Gamma correction: linearise display output
    color      = pow(color, vec3(1.0 / max(u_gamma, 0.01)));
    frag_color = vec4(color, 1.0);
}
"""
