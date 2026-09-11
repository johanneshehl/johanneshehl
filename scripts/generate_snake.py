"""
Generates an animated SVG of a fixed-length snake roaming the empty
(non-contribution) cells of a GitHub contribution calendar.

Rules:
- Contribution cells (count > 0) are shown as dots and act as walls; the
  snake may never move onto them.
- Empty cells (count == 0) form the walkable arena.
- A single "snack" (GitHub mark) spawns on a random walkable cell.
- The snake always takes the shortest path (BFS) to the current snack.
- Eating a snack never grows the snake -- it stays a fixed length forever
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
SNAKE_LENGTH = 6
STEPS = 240
STEP_DURATION = 0.22  # seconds per grid step

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
    "dark": dict(bg_free="#161b22", dot="#39d353", head="#58a6ff", tail="#1f3f66", snack="#f0f6fc"),
    "light": dict(bg_free="#ebedf0", dot="#216e39", head="#0969da", tail="#a6d1ff", snack="#24292f"),
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


def free_cells(blocked, cols, rows, exclude=()):
    return [
        (x, y)
        for y in range(rows)
        for x in range(cols)
        if not blocked[y][x] and (x, y) not in exclude
    ]


def bfs_path(blocked, cols, rows, start, goal):
    if start == goal:
        return [start]
    q = deque([start])
    came = {start: None}
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        cx, cy = cur
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (cx + dx, cy + dy)
            nx, ny = nxt
            if not (0 <= nx < cols and 0 <= ny < rows):
                continue
            if blocked[ny][nx]:
                continue
            if nxt in came:
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


def connected_component(blocked, cols, rows, start):
    """Flood fill of free cells reachable from start, ignoring the snake body."""
    seen = {start}
    q = deque([start])
    while q:
        cx, cy = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < cols and 0 <= ny < rows and not blocked[ny][nx] and (nx, ny) not in seen:
                seen.add((nx, ny))
                q.append((nx, ny))
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


def simulate(blocked, cols, rows, seed):
    rnd = random.Random(seed)
    arena = largest_component(blocked, cols, rows)
    start = rnd.choice(sorted(arena))
    body = deque([start] * SNAKE_LENGTH)
    positions = [start]
    snack_at_step = []
    snack = None

    arena_sorted = sorted(arena)
    while len(positions) < STEPS:
        if snack is None or snack == body[0]:
            candidates = [c for c in arena_sorted if c not in body] or [body[0]]
            snack = rnd.choice(candidates)

        path = bfs_path(blocked, cols, rows, body[0], snack)
        if not path or len(path) < 2:
            # snack sits on the current head with nowhere to step -- respawn
            snack = None
            continue

        snack_at_step.append(snack)
        next_cell = path[1]
        body.appendleft(next_cell)
        body.pop()
        positions.append(next_cell)

    snack_at_step.append(snack if snack is not None else snack_at_step[-1])
    return positions, snack_at_step


def fmt(values):
    return ";".join(f"{v:.2f}" for v in values)


def build_svg(blocked, cols, rows, positions, snack_at_step, theme_name):
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
        f'width="100%" role="img" aria-label="animated snake roaming the contribution graph">'
    ]

    # arena: free cells as soft squares, contribution cells as dots (walls)
    for y in range(rows):
        for x in range(cols):
            cx, cy = px((x, y))
            if blocked[y][x]:
                out.append(
                    f'<circle cx="{cx + CELL / 2:.1f}" cy="{cy + CELL / 2:.1f}" '
                    f'r="{CELL * 0.17:.1f}" fill="{theme["dot"]}" />'
                )
            else:
                out.append(
                    f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" rx="2" '
                    f'fill="{theme["bg_free"]}" />'
                )

    # snack: github mark that jumps between spawn cells
    translate_values = ";".join(
        f"{px(c)[0] + CELL / 2 - 5.5:.2f},{px(c)[1] + CELL / 2 - 5.5:.2f}"
        for c in snack_at_step
    )
    out.append(
        f'<g fill="{theme["snack"]}">'
        f'<animateTransform attributeName="transform" attributeType="XML" type="translate" '
        f'values="{translate_values}" calcMode="discrete" keyTimes="{key_times}" '
        f'dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
        f'<g transform="scale(0.7)"><path d="{GITHUB_MARK}"/></g>'
        f'</g>'
    )

    # snake segments (head first, drawn last so it's on top)
    for i in reversed(range(SNAKE_LENGTH)):
        xs, ys = [], []
        for t in range(steps):
            cell = positions[max(0, t - i)]
            cx, cy = px(cell)
            xs.append(cx)
            ys.append(cy)
        fade = 1 - (i / SNAKE_LENGTH) * 0.65
        color = theme["head"] if i == 0 else theme["tail"]
        out.append(
            f'<rect width="{CELL}" height="{CELL}" rx="3" fill="{color}" opacity="{fade:.2f}">'
            f'<animate attributeName="x" values="{fmt(xs)}" calcMode="discrete" '
            f'keyTimes="{key_times}" dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
            f'<animate attributeName="y" values="{fmt(ys)}" calcMode="discrete" '
            f'keyTimes="{key_times}" dur="{total_dur:.2f}s" repeatCount="indefinite"/>'
            f'</rect>'
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
    positions, snack_at_step = simulate(blocked, cols, rows, seed=7)
    svg = build_svg(blocked, cols, rows, positions, snack_at_step, theme)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {out_path}: cols={cols} rows={rows} steps={len(positions)}")


if __name__ == "__main__":
    main()
