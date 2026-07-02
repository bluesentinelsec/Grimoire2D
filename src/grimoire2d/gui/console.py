"""Quake-style in-game developer console.

Toggle with the ``~`` key.  Slides down from the top of the viewport with a
smooth animation, renders a subtle particle background, and provides a fully
featured readline-like input line (history, tab completion, reverse search,
clipboard integration).

Typical usage::

    console = InGameConsole(virtual_width=1920, virtual_height=1080)

    # Register commands
    console.register_command("fog", lambda args: toggle_fog(args),
                             description="fog [on|off]")

    # Per-frame integration
    for event in win.poll():
        if console.handle_event(event):
            continue          # event was consumed by the console
        handle_game_event(event)

    dt = win.begin_frame()
    console.update(dt)

    # ... game drawing ...

    console.draw(win.renderer)
    win.end_frame()

Release builds
--------------
Pass ``enabled=False`` to the constructor (or set ``console.enabled = False``)
to make the console completely inert — ``~`` is not intercepted,
``handle_event()`` always returns ``False``, and ``draw()`` is a no-op.
"""

from __future__ import annotations

import collections
import math
import random
import string
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from grimoire2d.presentation.renderer import Renderer


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

@dataclass
class _Command:
    name:        str
    handler:     Callable[[list[str]], str | None]
    description: str = ""
    aliases:     list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Output line
# ---------------------------------------------------------------------------

@dataclass
class _Line:
    text: str
    kind: str = "output"   # "output" | "input" | "error" | "info"


# ---------------------------------------------------------------------------
# Particle
# ---------------------------------------------------------------------------

@dataclass
class _Particle:
    x:        float
    y:        float
    vx:       float
    vy:       float
    life:     float   # remaining lifetime in seconds
    max_life: float
    radius:   float
    hue:      float   # 0–1 colour interpolation along cyan→purple


# ---------------------------------------------------------------------------
# InGameConsole
# ---------------------------------------------------------------------------

class InGameConsole:
    """Quake-style slide-down developer console.

    Parameters
    ----------
    virtual_width, virtual_height:
        Virtual coordinate space of the host window.
    height_frac:
        Fraction of the virtual height the open console occupies (default 0.45).
    history_max:
        Maximum number of commands stored in the history buffer.
    enabled:
        When ``False`` the console is completely inert — no events are
        consumed and ``draw()`` is a no-op.  Suitable for release builds.
    """

    # Visual constants
    _FONT_SIZE    = 20
    _LINE_H       = 24       # virtual pixels per output line
    _PAD_X        = 14
    _PAD_Y        = 10
    _CURSOR_RATE  = 0.53     # seconds per blink phase
    _SLIDE_SPEED  = 10.0     # open-fraction units per second
    _MAX_PARTICLES = 60
    _PARTICLE_SPAWN_RATE = 18   # per second

    # Colour palette (RGBA floats)
    _BG          = (0.04, 0.04, 0.07, 0.92)
    _BG_BORDER   = (0.15, 0.55, 0.85, 0.70)
    _INPUT_BG    = (0.07, 0.07, 0.12, 1.00)
    _COL = {
        "output": (0.75, 0.85, 0.78, 1.0),
        "input":  (0.55, 0.80, 1.00, 1.0),
        "error":  (1.00, 0.38, 0.35, 1.0),
        "info":   (0.85, 0.75, 1.00, 1.0),
    }
    _CURSOR_COL  = (0.40, 0.85, 1.00, 1.0)
    _PROMPT      = "> "
    _SEARCH_PROMPT = "(reverse-i-search)`{query}': "

    def __init__(
        self,
        virtual_width:  int,
        virtual_height: int,
        *,
        height_frac:  float = 0.45,
        history_max:  int   = 200,
        enabled:      bool  = True,
    ) -> None:
        self.enabled       = enabled
        self._vw           = virtual_width
        self._vh           = virtual_height
        self._panel_h      = int(virtual_height * height_frac)

        # Animation
        self._open        = False
        self._open_frac   = 0.0    # 0 = closed, 1 = fully open

        # Input state
        self._input:      str  = ""
        self._cursor:     int  = 0    # insertion point within _input
        self._cursor_t:   float = 0.0

        # History
        self._history:    collections.deque[str] = collections.deque(maxlen=history_max)
        self._hist_idx:   int  = -1   # -1 = not navigating
        self._hist_draft: str  = ""   # saved draft before navigating

        # Reverse search
        self._search_mode:  bool = False
        self._search_query: str  = ""
        self._search_idx:   int  = -1   # index into history for current match

        # Tab completion
        self._completions:     list[str] = []
        self._completion_idx:  int       = -1

        # Output buffer
        self._lines:  list[_Line] = []
        self._scroll: int         = 0   # lines scrolled up from the bottom

        # Particles
        self._particles:      list[_Particle] = []
        self._spawn_accum:    float = 0.0

        # Command registry
        self._commands: dict[str, _Command] = {}
        self._aliases:  dict[str, str]      = {}
        self._register_builtins()

    # ------------------------------------------------------------------
    # Public API — command registration
    # ------------------------------------------------------------------

    def register_command(
        self,
        name:        str,
        handler:     Callable[[list[str]], str | None],
        *,
        description: str       = "",
        aliases:     list[str] | None = None,
    ) -> None:
        """Register a console command.

        ``handler`` receives a list of string arguments (not including the
        command name) and may return an optional string to print as output.
        """
        cmd = _Command(name=name, handler=handler,
                       description=description, aliases=aliases or [])
        self._commands[name.lower()] = cmd
        for alias in (aliases or []):
            self._aliases[alias.lower()] = name.lower()

    def print(self, text: str, kind: str = "output") -> None:
        """Append one or more lines to the output buffer."""
        for line in str(text).splitlines() or [""]:
            self._lines.append(_Line(line, kind))
        self._scroll = 0   # snap to bottom on new output

    def execute(self, command_str: str) -> None:
        """Parse and execute a command string programmatically."""
        self._run(command_str.strip())

    # ------------------------------------------------------------------
    # Public API — frame lifecycle
    # ------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Process a pygame event; returns True if the console consumed it."""
        if not self.enabled:
            return False

        if event.type == pygame.KEYDOWN:
            # Toggle key — always checked even when closed
            if event.key == pygame.K_BACKQUOTE:
                self._toggle()
                return True

            if not self._open:
                return False

            return self._handle_keydown(event)

        # Swallow all keyboard events while open (prevents game from reacting)
        if not self._open:
            return False
        if event.type in (pygame.KEYDOWN, pygame.KEYUP, pygame.TEXTINPUT):
            return True
        return False

    def update(self, dt: float) -> None:
        """Advance animation and particles.  Call once per frame."""
        if not self.enabled:
            return

        # Slide animation
        target = 1.0 if self._open else 0.0
        delta  = self._SLIDE_SPEED * dt
        if self._open_frac < target:
            self._open_frac = min(target, self._open_frac + delta)
        else:
            self._open_frac = max(target, self._open_frac - delta)

        if self._open_frac <= 0.0:
            return   # fully closed; skip particle work

        # Cursor blink
        self._cursor_t += dt

        # Spawn particles
        self._spawn_accum += self._PARTICLE_SPAWN_RATE * dt
        while self._spawn_accum >= 1.0 and len(self._particles) < self._MAX_PARTICLES:
            self._spawn_accum -= 1.0
            self._spawn_particle()

        # Update particles
        keep: list[_Particle] = []
        for p in self._particles:
            p.life -= dt
            if p.life <= 0:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            keep.append(p)
        self._particles = keep

    def draw(self, renderer: "Renderer") -> None:
        """Draw the console overlay.  Call after game drawing, before end_frame."""
        if not self.enabled or self._open_frac <= 0.0:
            return

        frac = _ease_out(self._open_frac)
        panel_y = -self._panel_h + int(self._panel_h * frac)

        self._draw_background(renderer, panel_y)
        self._draw_particles(renderer, panel_y)
        self._draw_output(renderer, panel_y)
        self._draw_input(renderer, panel_y)
        self._draw_completions(renderer, panel_y)

    # ------------------------------------------------------------------
    # Built-in commands
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        self.register_command("help",    self._cmd_help,    description="help [command] — list commands or show help for one")
        self.register_command("clear",   self._cmd_clear,   description="clear — clear the output buffer")
        self.register_command("echo",    self._cmd_echo,    description="echo <text> — print text to the console")
        self.register_command("history", self._cmd_history, description="history — print command history")
        self.register_command("quit",    self._cmd_quit,    description="quit — signal the application to exit", aliases=["exit"])

    def _cmd_help(self, args: list[str]) -> str | None:
        if args:
            name = args[0].lower()
            cmd = self._commands.get(self._aliases.get(name, name))
            if cmd:
                return cmd.description or f"{cmd.name}: no description"
            return f"Unknown command: {args[0]}"
        lines = sorted(
            f"  {c.name:<16} {c.description}" for c in self._commands.values()
        )
        return "Commands:\n" + "\n".join(lines)

    def _cmd_clear(self, _args: list[str]) -> str | None:
        self._lines.clear()
        self._scroll = 0
        return None

    def _cmd_echo(self, args: list[str]) -> str | None:
        return " ".join(args)

    def _cmd_history(self, _args: list[str]) -> str | None:
        if not self._history:
            return "(empty)"
        lines = [f"  {i+1:3}  {cmd}" for i, cmd in enumerate(self._history)]
        return "\n".join(lines)

    def _cmd_quit(self, _args: list[str]) -> str | None:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        return "Goodbye."

    # ------------------------------------------------------------------
    # Event handling internals
    # ------------------------------------------------------------------

    def _toggle(self) -> None:
        self._open = not self._open
        if self._open:
            self._cursor_t = 0.0
            self._cancel_search()

    def _handle_keydown(self, event: pygame.event.Event) -> bool:
        key  = event.key
        mod  = event.mod
        ctrl = bool(mod & pygame.KMOD_CTRL)
        shift= bool(mod & pygame.KMOD_SHIFT)

        # --- Ctrl combos ---
        if ctrl:
            if key == pygame.K_r:
                self._start_or_advance_search()
                return True
            if key == pygame.K_c:
                self._clipboard_copy()
                return True
            if key == pygame.K_v:
                self._clipboard_paste()
                return True
            if key == pygame.K_a:
                self._cursor = 0
                return True
            if key == pygame.K_u:
                self._input  = self._input[self._cursor:]
                self._cursor = 0
                self._cancel_search(); self._reset_completions()
                return True
            if key == pygame.K_k:
                self._input = self._input[:self._cursor]
                self._cancel_search(); self._reset_completions()
                return True

        # --- Navigation ---
        if key == pygame.K_ESCAPE:
            if self._search_mode:
                self._cancel_search()
            else:
                self._open = False
            return True

        if key == pygame.K_RETURN or key == pygame.K_KP_ENTER:
            self._submit()
            return True

        if key == pygame.K_UP:
            self._history_back()
            return True
        if key == pygame.K_DOWN:
            self._history_forward()
            return True

        if key == pygame.K_LEFT:
            self._cursor = max(0, self._cursor - 1)
            self._reset_completions()
            return True
        if key == pygame.K_RIGHT:
            self._cursor = min(len(self._input), self._cursor + 1)
            self._reset_completions()
            return True
        if key == pygame.K_HOME:
            self._cursor = 0
            return True
        if key == pygame.K_END:
            self._cursor = len(self._input)
            return True

        if key == pygame.K_TAB:
            self._tab_complete()
            return True

        if key == pygame.K_PAGEUP:
            self._scroll_output(+1)
            return True
        if key == pygame.K_PAGEDOWN:
            self._scroll_output(-1)
            return True

        # --- Deletion ---
        if key == pygame.K_BACKSPACE:
            if self._search_mode:
                self._search_query = self._search_query[:-1]
                self._do_search(reverse=False)
            elif self._cursor > 0:
                self._input = self._input[:self._cursor-1] + self._input[self._cursor:]
                self._cursor -= 1
                self._reset_completions()
            return True
        if key == pygame.K_DELETE:
            if self._cursor < len(self._input):
                self._input = self._input[:self._cursor] + self._input[self._cursor+1:]
                self._reset_completions()
            return True

        # --- Printable character ---
        char = event.unicode
        if char and char.isprintable():
            if self._search_mode:
                self._search_query += char
                self._do_search(reverse=False)
            else:
                self._input = self._input[:self._cursor] + char + self._input[self._cursor:]
                self._cursor += 1
                self._hist_idx = -1
                self._reset_completions()
            return True

        return True   # swallow all keys while open

    # ------------------------------------------------------------------
    # Input submission
    # ------------------------------------------------------------------

    def _submit(self) -> None:
        if self._search_mode:
            # Accept the found history entry
            found = self._search_result()
            self._cancel_search()
            if found is not None:
                self._input  = found
                self._cursor = len(found)
            return

        cmd = self._input.strip()
        self._input  = ""
        self._cursor = 0
        self._hist_idx = -1
        self._reset_completions()

        if not cmd:
            return

        # Store in history (avoid consecutive duplicates)
        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)

        self.print(self._PROMPT + cmd, kind="input")
        self._run(cmd)

    def _run(self, cmd_str: str) -> None:
        parts = cmd_str.split()
        if not parts:
            return
        name = parts[0].lower()
        name = self._aliases.get(name, name)
        cmd  = self._commands.get(name)
        if cmd is None:
            self.print(f"Unknown command: {parts[0]!r}  (type 'help' for a list)", kind="error")
            return
        try:
            result = cmd.handler(parts[1:])
            if result is not None:
                self.print(str(result))
        except Exception as exc:
            self.print(f"Error: {exc}", kind="error")

    # ------------------------------------------------------------------
    # History navigation
    # ------------------------------------------------------------------

    def _history_back(self) -> None:
        self._cancel_search()
        if not self._history:
            return
        if self._hist_idx == -1:
            self._hist_draft = self._input
            self._hist_idx   = len(self._history) - 1
        elif self._hist_idx > 0:
            self._hist_idx -= 1
        self._input  = self._history[self._hist_idx]
        self._cursor = len(self._input)
        self._reset_completions()

    def _history_forward(self) -> None:
        if self._hist_idx == -1:
            return
        self._hist_idx += 1
        if self._hist_idx >= len(self._history):
            self._hist_idx = -1
            self._input    = self._hist_draft
        else:
            self._input = self._history[self._hist_idx]
        self._cursor = len(self._input)
        self._reset_completions()

    # ------------------------------------------------------------------
    # Reverse search
    # ------------------------------------------------------------------

    def _start_or_advance_search(self) -> None:
        if not self._search_mode:
            self._search_mode  = True
            self._search_query = ""
            self._search_idx   = len(self._history)
        self._do_search(reverse=True)

    def _do_search(self, *, reverse: bool) -> None:
        h = list(self._history)
        start = self._search_idx - 1 if reverse else self._search_idx
        for i in range(start, -1, -1):
            if self._search_query.lower() in h[i].lower():
                self._search_idx = i
                return
        # No (further) match — keep current

    def _search_result(self) -> str | None:
        h = list(self._history)
        if 0 <= self._search_idx < len(h):
            return h[self._search_idx]
        return None

    def _cancel_search(self) -> None:
        self._search_mode  = False
        self._search_query = ""
        self._search_idx   = -1

    # ------------------------------------------------------------------
    # Tab completion
    # ------------------------------------------------------------------

    def _tab_complete(self) -> None:
        token = self._input[:self._cursor].split()
        prefix = token[-1].lower() if token else ""

        if self._completions and self._completion_idx >= 0:
            # Already showing completions — cycle
            self._completion_idx = (self._completion_idx + 1) % len(self._completions)
            chosen = self._completions[self._completion_idx]
        else:
            # Fresh completion
            candidates = sorted(
                name for name in self._commands
                if name.startswith(prefix)
            )
            if not candidates:
                return
            self._completions    = candidates
            self._completion_idx = 0
            chosen = candidates[0]

        # Replace last token with chosen completion
        before = self._input[:self._cursor]
        after  = self._input[self._cursor:]
        if " " in before:
            before = before[:before.rfind(" ")+1]
        else:
            before = ""
        self._input  = before + chosen + after
        self._cursor = len(before) + len(chosen)

    def _reset_completions(self) -> None:
        self._completions    = []
        self._completion_idx = -1

    # ------------------------------------------------------------------
    # Scroll
    # ------------------------------------------------------------------

    def _scroll_output(self, direction: int) -> None:
        max_scroll = max(0, len(self._lines) - self._visible_line_count())
        self._scroll = max(0, min(max_scroll, self._scroll + direction * 4))

    def _visible_line_count(self) -> int:
        usable = self._panel_h - self._PAD_Y * 2 - self._LINE_H * 2  # minus input row
        return max(1, usable // self._LINE_H)

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def _clipboard_copy(self) -> None:
        try:
            pygame.display.set_clipboard(self._input)
        except Exception:
            pass

    def _clipboard_paste(self) -> None:
        try:
            text = pygame.display.get_clipboard() or ""
        except Exception:
            text = ""
        # Strip non-printable characters
        text = "".join(c for c in text if c.isprintable())
        if text:
            self._input  = self._input[:self._cursor] + text + self._input[self._cursor:]
            self._cursor += len(text)
            self._hist_idx = -1
            self._reset_completions()

    # ------------------------------------------------------------------
    # Particles
    # ------------------------------------------------------------------

    def _spawn_particle(self) -> None:
        p = _Particle(
            x        = random.uniform(0, self._vw),
            y        = self._panel_h - random.uniform(0, self._panel_h * 0.3),
            vx       = random.uniform(-12, 12),
            vy       = random.uniform(-28, -8),
            life     = random.uniform(1.2, 3.8),
            max_life = 0.0,
            radius   = random.uniform(1.0, 2.5),
            hue      = random.random(),
        )
        p.max_life = p.life
        self._particles.append(p)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_background(self, r: "Renderer", panel_y: int) -> None:
        # Main panel
        r.draw_rect(0, panel_y, self._vw, self._panel_h, self._BG)
        # Bottom accent border
        border_h = 3
        r.draw_rect(0, panel_y + self._panel_h - border_h,
                    self._vw, border_h, self._BG_BORDER)

    def _draw_particles(self, r: "Renderer", panel_y: int) -> None:
        for p in self._particles:
            t = p.life / p.max_life          # 1 = fresh, 0 = dead
            # Fade in for first 15% of life, out for last 40%
            if t > 0.85:
                alpha = (1.0 - t) / 0.15
            elif t < 0.40:
                alpha = t / 0.40
            else:
                alpha = 1.0
            alpha *= 0.55   # cap max opacity so particles stay subtle

            # Cyan (#1AF0C8) → purple (#8060FF) by hue
            rc = 0.10 + p.hue * 0.40
            gc = 0.94 - p.hue * 0.60
            bc = 0.78 + p.hue * 0.38
            bc = min(1.0, bc)

            r.draw_circle(p.x, panel_y + p.y,
                          p.radius, (rc, gc, bc, alpha))

    def _draw_output(self, r: "Renderer", panel_y: int) -> None:
        n     = self._visible_line_count()
        total = len(self._lines)
        # Which lines to show (newest at bottom)
        end   = max(0, total - self._scroll)
        start = max(0, end - n)
        visible = self._lines[start:end]

        y = panel_y + self._PAD_Y
        for line in visible:
            col = self._COL.get(line.kind, self._COL["output"])
            r.draw_text(line.text, self._PAD_X, y,
                        font_size=self._FONT_SIZE, color=col)
            y += self._LINE_H

    def _draw_input(self, r: "Renderer", panel_y: int) -> None:
        input_y  = panel_y + self._panel_h - self._LINE_H - self._PAD_Y
        input_h  = self._LINE_H + 4

        # Input row background
        r.draw_rect(0, input_y - 2, self._vw, input_h, self._INPUT_BG)

        # Build prompt string
        if self._search_mode:
            found = self._search_result()
            display_text = found or ""
            prompt = self._SEARCH_PROMPT.format(query=self._search_query)
        else:
            display_text = self._input
            prompt = self._PROMPT

        full_text = prompt + display_text
        r.draw_text(full_text, self._PAD_X, input_y,
                    font_size=self._FONT_SIZE, color=self._COL["input"])

        # Blinking cursor
        if int(self._cursor_t / self._CURSOR_RATE) % 2 == 0:
            cursor_in_input = self._cursor if not self._search_mode else len(display_text)
            pre = prompt + display_text[:cursor_in_input]
            cx, _cy = r.measure_text(pre, font_size=self._FONT_SIZE)
            r.draw_rect(self._PAD_X + cx, input_y,
                        2, self._LINE_H - 2, self._CURSOR_COL)

    def _draw_completions(self, r: "Renderer", panel_y: int) -> None:
        if len(self._completions) <= 1:
            return
        # Show candidates in a dim row just above the input line
        comp_y = panel_y + self._panel_h - self._LINE_H * 2 - self._PAD_Y - 4
        text   = "  ".join(
            f"[{c}]" if i == self._completion_idx else c
            for i, c in enumerate(self._completions)
        )
        r.draw_text(text, self._PAD_X, comp_y,
                    font_size=self._FONT_SIZE - 2,
                    color=(0.55, 0.65, 0.55, 0.85))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ease_out(t: float) -> float:
    """Cubic ease-out: fast open, gentle finish."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3
