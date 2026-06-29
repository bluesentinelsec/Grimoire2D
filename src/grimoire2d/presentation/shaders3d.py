"""Embedded GLSL shaders for the 3D renderer.

All shaders target GLSL 3.30 core (matching the OpenGL 3.30 core profile
required throughout Grimoire2D).

Two programs are provided:

PHONG  — full Phong lighting with runtime effect toggles (specular, fog).
         Used for solid primitive and mesh rendering.

WIRE   — single solid color, no lighting. Used for wireframe draw calls.
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
uniform sampler2D u_albedo;

// Camera
uniform vec3 u_cam_pos;

// Ambient
uniform vec3 u_ambient_color;

// Directional light (single sun/moon)
uniform bool  u_dir_light_on;
uniform vec3  u_dir_light_dir;    // direction light *travels* (toward surfaces)
uniform vec3  u_dir_light_color;

// Point lights — parallel arrays, max 8
uniform int   u_num_point_lights;
uniform vec3  u_pl_pos[8];
uniform vec3  u_pl_color[8];
uniform float u_pl_radius[8];
uniform float u_pl_intensity[8];

// Runtime effect toggles
uniform bool  u_specular_on;
uniform bool  u_fog_on;
uniform vec3  u_fog_color;
uniform float u_fog_near;
uniform float u_fog_far;

out vec4 frag_color;

// Blinn-Phong specular term
float spec_blinn(vec3 N, vec3 L, vec3 V, float shininess) {
    vec3 H = normalize(L + V);
    return pow(max(dot(N, H), 0.0), shininess);
}

void main() {
    vec4 base = u_use_texture ? texture(u_albedo, v_uv) : u_color;
    if (base.a < 0.01) discard;

    vec3 N = normalize(v_normal);
    vec3 V = normalize(u_cam_pos - v_world_pos);

    vec3 light_acc = u_ambient_color;

    // Directional light
    if (u_dir_light_on) {
        vec3 L    = normalize(-u_dir_light_dir);
        float NdL = max(dot(N, L), 0.0);
        light_acc += u_dir_light_color * NdL;
        if (u_specular_on) {
            light_acc += u_dir_light_color * spec_blinn(N, L, V, 64.0) * 0.35;
        }
    }

    // Point lights
    for (int i = 0; i < u_num_point_lights; i++) {
        vec3  to_light = u_pl_pos[i] - v_world_pos;
        float dist     = length(to_light);
        vec3  L        = normalize(to_light);

        // Inverse-square falloff clamped to radius
        float atten = clamp(1.0 - (dist / u_pl_radius[i]), 0.0, 1.0);
        atten = atten * atten;

        float NdL = max(dot(N, L), 0.0);
        light_acc += u_pl_color[i] * u_pl_intensity[i] * NdL * atten;
        if (u_specular_on) {
            light_acc += u_pl_color[i] * spec_blinn(N, L, V, 128.0) * atten * 0.5;
        }
    }

    vec3 result = light_acc * base.rgb;

    // Distance fog
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
in vec3 in_normal;
in vec2 in_uv;

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
