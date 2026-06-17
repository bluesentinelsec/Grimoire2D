"""Embedded default shaders (vendored as Python string literals).

This is the Raylib-inspired approach the project chose for shader distribution:
the source lives in the .py module. When the package (or a game using the
engine) is frozen with PyInstaller, the shaders come along automatically
with no extra package_data, asset manifests, or VFS entries required for
the defaults.

User games can do exactly the same for their custom shaders (define a
triple-quoted string in their own Python code and pass it to the renderer)
or load text via the VFS (grimoire2d.assets.vfs) for artist-editable .vert/.frag files.

All shaders target OpenGL 3.30 core.
"""

from __future__ import annotations


# Basic 2D orthographic + per-draw offset/scale + solid color.
# Positions are supplied in virtual resolution space (e.g. 0..1280, 0..720).
VERTEX_SHADER = """#version 330 core

in vec2 in_pos;

uniform mat4 u_projection;
uniform vec2 u_offset;
uniform vec2 u_scale;

void main() {
    vec2 p = in_pos * u_scale + u_offset;
    gl_Position = u_projection * vec4(p, 0.0, 1.0);
}
"""

FRAGMENT_SHADER = """#version 330 core

uniform vec4 u_color;

out vec4 frag_color;

void main() {
    frag_color = u_color;
}
"""


def get_default_vertex_shader() -> str:
    """Return the vendored 2D vertex shader source."""
    return VERTEX_SHADER


def get_default_fragment_shader() -> str:
    """Return the vendored solid-color fragment shader source."""
    return FRAGMENT_SHADER


# Textured quad shader for text (and future sprites/UI).
# Uses per-draw offset/scale in virtual space + tint color (for runtime color/alpha).
TEXTURED_VERTEX_SHADER = """#version 330 core

in vec2 in_pos;
in vec2 in_texcoord;

out vec2 v_texcoord;

uniform mat4 u_projection;
uniform vec2 u_offset;
uniform vec2 u_scale;

void main() {
    vec2 p = in_pos * u_scale + u_offset;
    gl_Position = u_projection * vec4(p, 0.0, 1.0);
    v_texcoord = in_texcoord;
}
"""

TEXTURED_FRAGMENT_SHADER = """#version 330 core

in vec2 v_texcoord;

uniform sampler2D u_texture;
uniform vec4 u_color;

out vec4 frag_color;

void main() {
    vec4 tex = texture(u_texture, v_texcoord);
    frag_color = tex * u_color;
}
"""


def get_textured_vertex_shader() -> str:
    """Return the vendored textured vertex shader (for text and sprites)."""
    return TEXTURED_VERTEX_SHADER


def get_textured_fragment_shader() -> str:
    """Return the vendored textured fragment shader (tints texture by u_color for runtime color/alpha/scale)."""
    return TEXTURED_FRAGMENT_SHADER


# SDF shape batch shader.
# Vertex layout: 14 floats per vertex — '2f 2f 2f 4f 4f'
#   in_pos       (vec2): virtual-space position
#   in_local_p   (vec2): position relative to shape centre (interpolated)
#   in_half_size (vec2): half-dimensions in virtual pixels (constant per quad)
#   in_color     (vec4): RGBA 0..1
#   in_params    (vec4): [corner_radius, border_thickness, inner_radius, shape_type]
#
# Shape type encoding (params.w):
#   0 = filled rect
#   1 = filled rounded rect
#   2 = filled circle  (radius = min(half_size))
#   3 = ring / annulus (outer = half_size.x, inner = params.z)
#   4 = rect border    (stroke, thickness = params.y)
#   5 = rounded rect border
SHAPE_VERTEX_SHADER = """#version 330 core

in vec2 in_pos;
in vec2 in_local_p;
in vec2 in_half_size;
in vec4 in_color;
in vec4 in_params;

out vec2 v_local_p;
out vec2 v_half_size;
out vec4 v_color;
out vec4 v_params;

uniform mat4 u_projection;

void main() {
    gl_Position = u_projection * vec4(in_pos, 0.0, 1.0);
    v_local_p   = in_local_p;
    v_half_size = in_half_size;
    v_color     = in_color;
    v_params    = in_params;
}
"""

SHAPE_FRAGMENT_SHADER = """#version 330 core
#define PI 3.14159265359

in vec2 v_local_p;
in vec2 v_half_size;
in vec4 v_color;
in vec4 v_params;

out vec4 frag_color;

float sdf_rect(vec2 p, vec2 half_size) {
    vec2 q = abs(p) - half_size;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0);
}

float sdf_rounded_rect(vec2 p, vec2 half_size, float r) {
    r = min(r, min(half_size.x, half_size.y));
    vec2 q = abs(p) - half_size + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

float sdf_circle(vec2 p, float r) {
    return length(p) - r;
}

float sdf_ring(vec2 p, float outer_r, float inner_r) {
    return abs(length(p) - (outer_r + inner_r) * 0.5) - (outer_r - inner_r) * 0.5;
}

void main() {
    float corner_r  = v_params.x;
    float border_t  = v_params.y;
    float inner_r   = v_params.z;
    int   shape_type = int(v_params.w + 0.5);

    float d;
    if (shape_type == 0) {
        d = sdf_rect(v_local_p, v_half_size);
    } else if (shape_type == 1) {
        d = sdf_rounded_rect(v_local_p, v_half_size, corner_r);
    } else if (shape_type == 2) {
        float r = min(v_half_size.x, v_half_size.y);
        d = sdf_circle(v_local_p, r);
    } else if (shape_type == 3) {
        d = sdf_ring(v_local_p, v_half_size.x, inner_r);
    } else if (shape_type == 4) {
        float filled = sdf_rect(v_local_p, v_half_size);
        d = abs(filled) - border_t * 0.5;
    } else if (shape_type == 5) {
        float filled = sdf_rounded_rect(v_local_p, v_half_size, corner_r);
        d = abs(filled) - border_t * 0.5;
    } else if (shape_type == 6) {
        // ELLIPSE
        vec2 n = v_local_p / v_half_size;
        float d_norm = length(n) - 1.0;
        d = d_norm * min(v_half_size.x, v_half_size.y);
    } else if (shape_type == 7) {
        // ARC: corner_r=arc_thickness, border_t=angle_start, inner_r=angle_span
        float arc_t = corner_r;
        float a_start = border_t;
        float a_span = inner_r;
        float outer_r = min(v_half_size.x, v_half_size.y);
        float inner_rr = max(outer_r - arc_t, 0.0);
        d = sdf_ring(v_local_p, outer_r, inner_rr);
        if (length(v_local_p) > 0.001) {
            float a = atan(v_local_p.y, v_local_p.x);
            float da = mod(a - a_start + 6.28318 * 2.0, 6.28318);
            if (da > a_span) d = 1.0;
        }
    } else if (shape_type == 8) {
        // PIE: corner_r=angle_start, border_t=angle_span
        float a_start = corner_r;
        float a_span = border_t;
        d = sdf_circle(v_local_p, min(v_half_size.x, v_half_size.y));
        if (length(v_local_p) > 0.001) {
            float a = atan(v_local_p.y, v_local_p.x);
            float da = mod(a - a_start + 6.28318 * 2.0, 6.28318);
            if (da > a_span) d = 1.0;
        }
    } else if (shape_type == 9) {
        // CAPSULE
        float r = min(v_half_size.x, v_half_size.y);
        vec2 inner = v_half_size - r;
        vec2 q = abs(v_local_p) - inner;
        d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
    } else if (shape_type == 10) {
        // GLOW: corner_r=glow_radius, border_t=shape_radius
        float glow_r = corner_r;
        float shape_r = border_t;
        float shape_d = sdf_rounded_rect(v_local_p, v_half_size, shape_r);
        float alpha = smoothstep(glow_r, 0.0, shape_d) * v_color.a;
        if (alpha < 0.004) discard;
        frag_color = vec4(v_color.rgb, alpha);
        return;
    } else {
        float filled = sdf_rounded_rect(v_local_p, v_half_size, corner_r);
        d = abs(filled) - border_t * 0.5;
    }

    float alpha = smoothstep(1.0, 0.0, d);
    alpha *= v_color.a;
    if (alpha < 0.004) discard;
    frag_color = vec4(v_color.rgb, alpha);
}
"""


def get_shape_vertex_shader() -> str:
    """Return the SDF shape batch vertex shader source."""
    return SHAPE_VERTEX_SHADER


def get_shape_fragment_shader() -> str:
    """Return the SDF shape batch fragment shader source."""
    return SHAPE_FRAGMENT_SHADER


# Sprite batch shader for textured quads with per-vertex tint.
# Vertex layout: 8 floats per vertex — '2f 2f 4f'
#   in_pos      (vec2): virtual-space position
#   in_texcoord (vec2): normalised UV coordinates
#   in_tint     (vec4): RGBA multiplier (1,1,1,1 = no tint)
SPRITE_VERTEX_SHADER = """#version 330 core

in vec2 in_pos;
in vec2 in_texcoord;
in vec4 in_tint;

out vec2 v_texcoord;
out vec4 v_tint;

uniform mat4 u_projection;

void main() {
    gl_Position = u_projection * vec4(in_pos, 0.0, 1.0);
    v_texcoord  = in_texcoord;
    v_tint      = in_tint;
}
"""

SPRITE_FRAGMENT_SHADER = """#version 330 core

in vec2 v_texcoord;
in vec4 v_tint;

uniform sampler2D u_texture;

out vec4 frag_color;

void main() {
    frag_color = texture(u_texture, v_texcoord) * v_tint;
    if (frag_color.a < 0.004) discard;
}
"""


def get_sprite_vertex_shader() -> str:
    """Return the sprite batch vertex shader source."""
    return SPRITE_VERTEX_SHADER


def get_sprite_fragment_shader() -> str:
    """Return the sprite batch fragment shader source."""
    return SPRITE_FRAGMENT_SHADER


# Pixel-buffer shader for rendering a PixelBuffer texture as a nearest-
# neighbour quad.  Filtering is NEAREST (set on the texture, not here).
# Vertex layout: same as SPRITE_SHADER (8 floats, '2f 2f 4f') — tint is
# accepted but ignored in the fragment shader for simplicity.
# Uniforms u_offset / u_scale position the quad in virtual space.
PIXEL_BUFFER_VERTEX_SHADER = """#version 330 core

in vec2 in_pos;
in vec2 in_texcoord;

out vec2 v_texcoord;

uniform mat4 u_projection;
uniform vec2 u_offset;
uniform vec2 u_scale;

void main() {
    vec2 p = in_pos * u_scale + u_offset;
    gl_Position = u_projection * vec4(p, 0.0, 1.0);
    v_texcoord  = in_texcoord;
}
"""

PIXEL_BUFFER_FRAGMENT_SHADER = """#version 330 core

in vec2 v_texcoord;

uniform sampler2D u_texture;

out vec4 frag_color;

void main() {
    frag_color = texture(u_texture, v_texcoord);
}
"""


def get_pixel_buffer_vertex_shader() -> str:
    """Return the pixel-buffer quad vertex shader source."""
    return PIXEL_BUFFER_VERTEX_SHADER


def get_pixel_buffer_fragment_shader() -> str:
    """Return the pixel-buffer quad fragment shader source."""
    return PIXEL_BUFFER_FRAGMENT_SHADER


# Polygon batch shader for flat-coloured / gradient triangles.
# Vertex layout: 6 floats per vertex — '2f 4f'
#   in_pos   (vec2): virtual-space position
#   in_color (vec4): RGBA 0..1 (per-vertex for gradients)
POLYGON_VERTEX_SHADER = """#version 330 core
in vec2 in_pos;
in vec4 in_color;
out vec4 v_color;
uniform mat4 u_projection;
void main() {
    gl_Position = u_projection * vec4(in_pos, 0.0, 1.0);
    v_color = in_color;
}
"""

POLYGON_FRAGMENT_SHADER = """#version 330 core
in vec4 v_color;
out vec4 frag_color;
void main() {
    if (v_color.a < 0.004) discard;
    frag_color = v_color;
}
"""


def get_polygon_vertex_shader() -> str:
    """Return the polygon batch vertex shader source."""
    return POLYGON_VERTEX_SHADER


def get_polygon_fragment_shader() -> str:
    """Return the polygon batch fragment shader source."""
    return POLYGON_FRAGMENT_SHADER
