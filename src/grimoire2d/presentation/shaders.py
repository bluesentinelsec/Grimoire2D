"""Embedded default shaders (vendored as Python string literals).

This is the Raylib-inspired approach the project chose for shader distribution:
the source lives in the .py module. When the package (or a game using the
engine) is frozen with PyInstaller, the shaders come along automatically
with no extra package_data, asset manifests, or VFS entries required for
the defaults.

User games can do exactly the same for their custom shaders (define a
triple-quoted string in their own Python code and pass it to the renderer)
or load text via the future VFS for artist-editable .vert/.frag files.

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
