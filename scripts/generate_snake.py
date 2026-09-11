"""
Generates a smooth, looping SVG animation of a fixed-length snake roaming
the empty (non-contribution) cells of a GitHub contribution calendar.

Rules:
- Contribution cells (count > 0) are walls the snake may never enter.
- Empty cells (count == 0) form the walkable arena.
- The snake may never move onto its own body (except the tail cell it is
  about to vacate).
- A single "snack" (GitHub mark) spawns on a random walkable cell; the
  snake takes the shortest path to it that does not cross its own body.
- Eating a snack never grows the snake -- it stays a fixed length forever,
  so the loop can repeat indefinitely.

Usage:
  python generate_snake.py <contrib.json> <out.svg> [--theme dark|light]
"""
import json
import random
import sys
from collections import deque

CELL = 11
GAP = 3
STEP = CELL + GAP
RADIUS = 3
SNAKE_LENGTH = 6
STEPS = 220
STEP_DURATION = 0.32  # seconds per grid cell, smoothly interpolated

GITHUB_MARK = (
    "M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 "
    "0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 "
    "0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-"
    "1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 "
    "1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-"
    ".44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-"
    ".27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 "
    "1.49 0 .21-.15.45-.55.38A8.013 8.013 0 0 1 0 8c0-4.42 3.58-8 8-8Z"
)

THEMES = {
    "dark": dict(
        bg="none",
        free="#161b22",
        free_stroke="#21262d",
        wall="#2ea043",
        wall_stroke="#3fb950",
        head=(88, 166, 255),   # #58a6ff
        tail=(20, 40, 70),
        eye="#0d1117",
        snack="#e3b341",
        glow="#e3b341",
    ),
    "light": dict(
        bg="none",
        free="#eef0f2",
        free_stroke="#d8dbdf",
        wall="#40c463",
        wall_stroke="#2ea44f",
        head=(9, 105, 218),    # #0969da
        tail=(179, 210, 255),
        eye="#ffffff",
        snack="#9a6700",
        glow="#9a6700",
    ),
}


def load_grid(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    cols = len(weeks)
    rows = 7
    blocked = [[False] * cols for _ in range(rows)]
    for x, week in enumerate(weeks):
        for y, day in enumerate(week["contributionDays"]):
            if day["contributionCount"] > 0:
                blocked[y][x] = True
    return blocked, cols, rows


def in_bounds(cols, rows, x, y):
    return 0 <= x < cols and 0 <= y < rows


def neighbors(blocked, cols, rows, cell):
    x, y = cell
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if in_bounds(cols, rows, nx, ny) and not blocked[ny][nx]:
            yield (nx, ny)


def free_cells(blocked, cols, rows):
    return [(x, y) for y in range(rows) for x in range(cols) if not blocked[y][x]]


def connected_component(blocked, cols, rows, start):
    seen = {start}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in neighbors(blocked, cols, rows, cur):
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    return seen


def largest_component(blocked, cols, rows):
    seen_global = set()
    best = set()
    for cell in free_cells(blocked, cols, rows):
        if cell in seen_global:
            continue
        comp = connected_component(blocked, cols, rows, cell)
        seen_global |= comp
        if len(comp) > len(best):
            best = comp
    return best


def bfs_path(blocked, cols, rows, start, goal, obstacles):
    """Shortest path from start to goal, never entering `obstacles` (the
    snake's own body, tail excluded) or contribution-blocked cells."""
    if start == goal:
        return [start]
    q = deque([start])
    came = {start: None}
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for nxt in neighbors(blocked, cols, rows, cur):
            if nxt in came:
                continue
            if nxt in obstacles and nxt != goal:
                continue
            came[nxt] = cur
            q.append(nxt)
    if goal not in came:
        return None
    path = [goal]
    while came[path[-1]] is not None:
        path.append(came[path[-1]])
    path.reverse()
    return path


def simulate(blocked, cols, rows, seed):
    rnd = random.Random(seed)
    arena = sorted(largest_component(blocked, cols, rows))
    start = rnd.choice(arena)
    body = deque([start] * SNAKE_LENGTH)
    positions = [start]
    snack_history = []
    snack = None

    for _ in range(STEPS - 1):
        body_minus_tail = set(list(body)[:-1])

        if snack is None or snack == body[0]:
            candidates = [c for c in arena if c not in body]
            snack = rnd.choice(candidates) if candidates else body[0]

        path = bfs_path(blocked, cols, rows, body[0], snack, body_minus_tail)
        if path and len(path) >= 2:
            next_cell = path[1]
        else:
            # snack currently unreachable without crossing the body -- take
            # the safest step that gets us closest, never crossing the body
            legal = [n for n in neighbors(blocked, cols, rows, body[0]) if n not in body_minus_tail]
            if legal:
                next_cell = min(legal, key=lambda n: abs(n[0] - snack[0]) + abs(n[1] - snack[1]))
            else:
                next_cell = body[0]  # fully boxed in by its own body (very rare); wait a tick

        snack_history.append(snack)
        body.appendleft(next_cell)
        body.pop()
        positions.append(next_cell)

    snack_history.append(snack if snack is not None else positions[-1])
    return positions, snack_history


def fmt(values):
    return ";".join(f"{v:.2f}" for v in values)


def lerp_color(c1, c2, t):
    return tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def to_hex(c):
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def build_svg(blocked, cols, rows, positions, snack_history, theme_name):
    theme = THEMES[theme_name]
    width = cols * STEP - GAP
    height = rows * STEP - GAP
    steps = len(positions)
    total_dur = steps * STEP_DURATION
    key_times = fmt([i / (steps - 1) for i in range(steps)])

    def px(cell):
        x, y = cell
        return x * STEP, y * STEP

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" role="img" aria-label="a snake roaming the empty cells of the '
        f'contribution graph, chasing a github icon">',
        "<defs>",
        f'<filter id="glow" x="-60%" y="-60%" width="220%" height="220%">'
        f'<feGaussianBlur stdDeviation="1.6" result="blur"/>'
        f'<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f"</filter>",
        "</defs>",
    ]

    # arena: free cells as soft rounded tiles, contribution cells as filled walls
    for y in range(rows):
        for x in range(cols):
            cx, cy = px((x, y))
            if blocked[y][x]:
                out.append(
                    f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" rx="{RADIUS}" '
                    f'fill="{theme["wall"]}" stroke="{theme["wall_stroke"]}" stroke-width="0.6"/>'
                )
            else:
                out.append(
                    f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" rx="{RADIUS}" '
                    f'fill="{theme["free"]}" stroke="{theme["free_stroke"]}" stroke-width="0.6"/>'
                )

    # snack: pulsing glow + github mark, jumping between spawn cells
    translate_values = ";".join(
        f"{px(c)[0] + CELL / 2:.2f},{px(c)[1] + CELL / 2:.2f}" for c in snack_history
    )
    out.append(
        f'<g filter="url(#glow)">'
        f'<animateTransform attributeName="transform" attributeType="XML" type="translate" '
        f'values="{translate_values}" calcMode="discrete" keyTimes="{key_times}" '
        f'dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
        f'<circle r="3.6" fill="{theme["glow"]}" opacity="0.35">'
        f'<animate attributeName="r" values="3.2;4.4;3.2" dur="1.4s" repeatCount="indefinite"/>'
        f"</circle>"
        f'<g transform="translate(-5.5,-5.5) scale(0.7)" fill="{theme["snack"]}">'
        f'<path d="{GITHUB_MARK}"/>'
        f"</g></g>"
    )

    # snake segments, tail first so the head renders on top
    for i in reversed(range(SNAKE_LENGTH)):
        xs, ys = [], []
        for t in range(steps):
            cell = positions[max(0, t - i)]
            cx, cy = px(cell)
            xs.append(cx + CELL / 2)
            ys.append(cy + CELL / 2)
        t_fade = i / (SNAKE_LENGTH - 1) if SNAKE_LENGTH > 1 else 0
        color = to_hex(lerp_color(theme["head"], theme["tail"], t_fade))
        scale = 1.0 if i == 0 else max(0.68, 1 - t_fade * 0.35)
        half = CELL * scale / 2

        segment_body = (
            f'<rect x="{-half:.2f}" y="{-half:.2f}" width="{half * 2:.2f}" height="{half * 2:.2f}" '
            f'rx="{RADIUS}" fill="{color}"/>'
        )
        if i == 0:
            eye_offset = half * 0.45
            segment_body += (
                f'<circle cx="{-eye_offset:.2f}" cy="{-eye_offset:.2f}" r="0.9" fill="{theme["eye"]}"/>'
                f'<circle cx="{eye_offset:.2f}" cy="{-eye_offset:.2f}" r="0.9" fill="{theme["eye"]}"/>'
            )

        wrapper_filter = ' filter="url(#glow)"' if i == 0 else ""
        out.append(
            f"<g{wrapper_filter}>"
            f'<animateTransform attributeName="transform" attributeType="XML" type="translate" '
            f'values="{";".join(f"{x:.2f},{y:.2f}" for x, y in zip(xs, ys))}" '
            f'calcMode="linear" keyTimes="{key_times}" dur="{total_dur:.2f}s" '
            f'repeatCount="indefinite"/>'
            f"{segment_body}</g>"
        )

    out.append("</svg>")
    return "\n".join(out)


def main():
    grid_path = sys.argv[1]
    out_path = sys.argv[2]
    theme = "dark"
    if "--theme" in sys.argv:
        theme = sys.argv[sys.argv.index("--theme") + 1]

    blocked, cols, rows = load_grid(grid_path)
    positions, snack_history = simulate(blocked, cols, rows, seed=7)
    svg = build_svg(blocked, cols, rows, positions, snack_history, theme)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out_path}: cols={cols} rows={rows} steps={len(positions)}")


if __name__ == "__main__":
    main()
