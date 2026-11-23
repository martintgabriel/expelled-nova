# Spec 027 — Campus Security: the Segway guard

## Why
So far an examiner who is careful about distance and cooldowns can expel freely: nothing on
the campus itself ever catches them in the act. BRD roadmap F1 asks for exactly that risk: "a
Segway security guard patrols a fixed route; an examiner who expels inside his view cone is
caught." He adds a random factor nobody controls: students cannot shadow him to stay safe,
and examiners can never be sure where he is or whether he is watching, because his path
through a fixed network of waypoints is chosen fresh, and at random, every round. (BRD's
"fixed route" is read as "a fixed network of possible paths, walked in a random order" — the
map data is fixed, the round-to-round path is not; a literal fixed patrol loop would make him
exactly as predictable as the "students cannot simply follow him around" requirement forbids.)

He is a hazard, not a bodyguard: he never helps a student, never blocks anyone's movement and
plays no part in who wins. His only effect is the small chance that an expel happens to be
seen, which starts a meeting that names the examiner who did it — the one deliberate exception
to R2 in the whole game (AGENTS.md: "the server decides everything"; R2: "a player never
receives another player's role"). Builds on spec 003 (expel, ghosts, failed exams, win check),
spec 005 (vision radius, colours), spec 006/011 (meetings, the meeting table), spec 010 (line
of sight, `sight_clear`, and the browser's wall-clipped lit area, reused below for the guard's
own cone), spec 015 (vents, the beach, the handbook), specs 016/017 (the generated-sound
system) and spec 018 (the campus map overlay, which the guard must stay invisible to). The
campus map was redrawn since this spec was first written (specs 018 and 026: new area names,
room-centred labels, colours); the waypoint network below is built for that map, not the
older one. Nothing in specs 019, 021, 022, 024 or 025 (cooldowns, tasks, examiner count,
hats/colours, the gym skylight) changes anything here; see "Compatibility" below.

## What

### Server — map data (`server/campus.json`)
- A new top-level entry `"guard_route"`: `{"waypoints": [...]}`.
  - `"waypoints"`: a list of `{"id", "x", "y", "connections"}`, tile column/row like every
    other map place (vents, the meeting point). `"connections"` lists the ids of the
    waypoints this one connects to directly; a connection is listed on both ends.
  - 23 waypoints, spread over corridors and open areas so the whole campus is covered: every
    one of the campus's seven `areas` (Main Entrance, Student Services, Food Court, Library,
    Upper Courtyard, Lower Courtyard, Auditorium) has a waypoint inside its own rectangle, and
    the beach, all four vent quadrants and the big halls (Hall B, the CTT Student Hall, Hall D,
    Hall E, the Spine, EDP Plaza) are reached within a few tiles too.
  - Every waypoint sits on a floor tile. Every connection is a straight line the guard can
    drive without his square (the same 20×20 px collision as a player) touching a blocked
    tile anywhere along it — checked the same way `Game.blocked` checks a player, not with
    `sight_clear` (which only cares about *sight*, not walking: glass and the sea do not block
    the guard's sight, but they do block his wheels like anyone else's feet). The waypoint
    graph is connected (every waypoint reachable from every other).
  - Checked once, at server start, like the existing decor/label checks in `validate_campus`
    (`server/game.py`): a broken route fails fast with `ValueError`, not mid-game. The checks
    themselves (floor tile, drivable line, connected graph, listed on both ends) live in the
    new module below, so they can also be unit-tested directly.

  **The waypoints**, tile column/row (verified against the current `server/campus.json` grid:
  every tile below is floor, and every listed connection is a straight, undivided, drivable
  line for a 20×20 px square):

  | id                 | x  | y  | connects to                                 | near |
  |--------------------|----|----|----------------------------------------------|------|
  | `entrance`         | 27 |  4 | `services`, `spine-north`                     | Main Entrance |
  | `services`         | 39 |  4 | `entrance`, `services-vent`                   | Student Services |
  | `services-vent`    | 41 |  2 | `services`                                    | the Student Services vent (43, 1) |
  | `spine-north`      | 28 | 11 | `entrance`, `west-vent`, `foodcourt`, `spine-mid` | the Spine, row 11 |
  | `west-vent`        |  9 | 11 | `spine-north`, `beach-north`, `upper-courtyard` | the Lecture Hall B vent (7, 10); Hall B |
  | `foodcourt`        | 37 | 12 | `spine-north`                                 | Food Court, the Shop, the Cafeteria |
  | `beach-north`      |  3 | 11 | `west-vent`                                   | Carcavelos Beach (north end) |
  | `upper-courtyard`  |  9 | 15 | `west-vent`, `west-mid`                       | Upper Courtyard |
  | `west-mid`         |  9 | 19 | `upper-courtyard`, `lower-courtyard`          | the CTT Student Hall |
  | `lower-courtyard`  |  9 | 23 | `west-mid`, `west-south`, `beach-mid`         | Lower Courtyard |
  | `beach-mid`        |  3 | 23 | `lower-courtyard`, `beach-south`              | Carcavelos Beach (middle) |
  | `west-south`       |  9 | 27 | `lower-courtyard`, `beach-south`, `spine-south` | Hall D |
  | `beach-south`      |  3 | 27 | `beach-mid`, `west-south`, `beach-lawn`       | Carcavelos Beach (south end) |
  | `beach-lawn`       |  3 | 34 | `beach-south`, `south-lawn`                   | Carcavelos Beach meets the south lawn |
  | `spine-mid`        | 28 | 21 | `spine-north`, `spine-south`, `library`       | the Spine, by the meeting table |
  | `library`          | 37 | 22 | `spine-mid`                                   | the Library |
  | `spine-south`      | 28 | 27 | `spine-mid`, `spine-lawn`, `west-south`       | the Spine |
  | `south-lawn`       |  9 | 35 | `beach-lawn`, `spine-lawn`                    | the South Lawn vent (7, 36); Hall E |
  | `spine-lawn`       | 28 | 34 | `spine-south`, `south-lawn`, `edp-plaza`, `spine-auditorium` | the Spine, south end |
  | `edp-plaza`        | 37 | 34 | `spine-lawn`, `plaza-vent`                    | EDP Plaza |
  | `plaza-vent`       | 42 | 34 | `edp-plaza`                                   | the Plaza vent (44, 36) |
  | `spine-auditorium` | 28 | 39 | `spine-lawn`, `auditorium`                    | the corridor into the Auditorium |
  | `auditorium`       | 33 | 39 | `spine-auditorium`                            | the Auditorium |

  Six waypoints are dead ends with a single connection (`services-vent`, `foodcourt`,
  `beach-north`, `library`, `plaza-vent`, `auditorium`): each is a room or vent only reached
  from one side, so the guard backtracks there by design (see "Choosing the next waypoint"
  below). The rest form a loop through the Spine and the west corridor, so most of the route
  never needs to.

- **A new module `server/guard.py`**, used by `server/game.py` like `server/minigames.py` is:
  plain Python, no network code.
  - Builds the waypoint lookup and adjacency lists from the map's `guard_route`, and validates
    it (see above).
  - Holds the guard's live state (`GuardState`: `x`, `y`, `facing`, `paused`, the current and
    target waypoint, the one he came from, his pause timer) and the pure movement math: step
    towards the target waypoint, arrive and decide whether to pause, pick the next waypoint,
    and the head-sweep while paused. None of it needs a live `Game`, so it is tested on its
    own with a seeded `random.Random`.
  - `server/game.py` only calls into it from `Game.start()` (place the guard), `Game.step()`
    (advance him one tick while `PLAYING`) and `Game.expel()` (the catch check).
- **`Game.__init__`** removes `"guard_route"` from the campus dict it keeps as `self.campus`
  — the same dict `server/main.py` sends verbatim as `welcome.map` — once it has built its own
  graph from it. The browser can therefore never receive the waypoints or the connections,
  whatever a player's role. (This is also why the campus map of spec 018/026 never needs any
  change: `web/campusmap.js` only ever reads `welcome.map`, which never carries a `guard`
  anything — see "Compatibility" below.)

### Server — movement and timing (`server/game.py` constants)
- `GUARD_SPEED = 1.6 * SPEED` (256 px/s): faster than any player, so nobody can simply outrun
  or escort him.
- `GUARD_VISION_TILES = 4` (128 px) and `GUARD_CONE_DEGREES = 70`: a smaller, narrower view
  than a player's own (`VISION_TILES = 6`, a full circle) — a glancing, not a searchlight.
- `GUARD_PAUSE_CHANCE = 0.25`: the chance, checked once with `self.rng` each time he arrives
  at a waypoint, that he stops there instead of moving straight on.
- A pause lasts a whole number of seconds drawn with `self.rng` between 1 and 3 (inclusive),
  during which he does not move but slowly sweeps his facing left and right around the
  heading he arrived with, then departs as usual.
- `GUARD_MIN_START_TILES = 10`: how far from every Main Entrance spawn his starting waypoint
  must be (see "Start" below). 19 of the 23 waypoints above qualify; only `entrance`,
  `services`, `services-vent` and `spine-north` are too close.

### Server — driving the route
- **Choosing the next waypoint:** on arrival, among the waypoints this one connects to, every
  one except the waypoint he just came from is a candidate; if that is the only connection
  (a dead end), it is the one candidate. `self.rng.choice` picks among the candidates, so
  a route never immediately backtracks unless it has no other way, and it is different every
  round and with every seed.
- **Driving:** each tick he moves `GUARD_STEP` (`GUARD_SPEED / TICK_RATE`) straight towards
  his target waypoint's centre and faces the direction he is moving; reaching the target
  within one step snaps him exactly onto it instead of overshooting.
- **No pathfinding per tick:** he only ever walks the straight line of a precomputed
  connection, so advancing him costs the same no matter how big the map's waypoint graph gets.
- **Start:** when `Game.start()` deals the roles, the guard is placed at a random waypoint
  that lies at least `GUARD_MIN_START_TILES` from every spawn point, and picks a first target
  the same way as any other arrival (nothing to exclude yet, since he has not come from
  anywhere). He exists and moves only while the phase is `PLAYING`; in `LOBBY` and `ENDED` he
  does not exist (`self.guard` is `None`); `Game.step()` does not advance him during a
  `MEETING` (the same early return that already stops every player moving then), so he stands
  exactly where he was and continues untouched once play resumes.
- **Not a player:** `self.guard` is a `GuardState`, never a `Player`. He is never in
  `self.players`, in anyone's player count, in a vote, in `fellow_examiners`, in a win check,
  and he cannot be expelled, reported or voted for. He does not block movement: a player can
  walk straight through his square. He has no hat and no colour (spec 022 does not touch him).

### Server — the vision cone and the catch rule
- A point (a player's centre) is seen by the guard when it is within `GUARD_VISION_TILES`,
  within `GUARD_CONE_DEGREES` of his facing, and `Game.sight_clear` finds a clear line from
  his centre to it — the same rule as a player's own sight (spec 010), just centre-to-centre
  (no corner check) and never shrunk by the lights: `sabotage`'s darkness is for students only,
  because the guard carries his own light.
- **After an expel succeeds** (`Game.expel`, after the existing win check): if the examiner's
  centre or the expelled student's centre (whichever the lights were or were not, both still
  stand where the expel left them) is seen by the guard at that tick:
  - if the expel just ended the game (an examiner win), the game ends exactly as it already
    does; the end screen additionally shows that security saw it (`security_witnessed`);
  - otherwise a meeting starts at once, with the new reason `"security"`, and the meeting
    carries `caught`: the caught examiner's id. Nothing else about the meeting changes: it is
    paused, timed and voted on exactly like a report or a button meeting.
  - **R7 (first processed wins):** this check runs after the expel it belongs to, in the same
    tick, so whichever expel the server processes first is the one judged; a second expel
    in the same tick is rejected before it ever reaches this check, as today.
  - An expel in a vent is impossible already (`Game.expel` rejects an examiner inside one), so
    the guard never has to be checked against a vent.
  - **Only this one examiner is revealed.** A fellow examiner's role, and everyone else's,
    stays exactly as secret as it always was. This is a deliberate, one-off exception to R2,
    made only for the one player the security guard actually saw commit the act.

### Server — what each player receives
- `snapshot()` (shared by every `snapshot_for` call) gains a `"guard"` entry — `{"x", "y",
  "facing", "paused"}` — under the same visibility rule it already applies to `players` and
  `failed_exams`: with no viewer (ghosts; lobby; a meeting; after the end) it is sent whenever
  `self.guard` exists; with a viewer (a living player while `PLAYING`) it is sent only when
  that player's own sight — their own radius, their own line of sight, shrunk by the lights if
  they are a student and the lights are off — reaches the guard. Nothing new has to be written
  for ghosts, the lobby or the end screen: they already receive everything through the same
  code path.
  - A living player therefore sees the guard exactly when they could plausibly have noticed
    him walking past — and an examiner sees him exactly as any other player would, with no
    special warning.
  - If `self.guard` does not exist (`LOBBY`, `ENDED`, or a map with no `guard_route`) there is
    no `"guard"` key at all.
- `Meeting` gains `caught: str | None`, carried into `_meeting_for` as `"caught"`, `None` for
  `"report"` and `"button"`.
- `ENDED` state gains `"security_witnessed"`: `True` only when the expel that ended the game
  (an examiner win) was itself seen by the guard.
- The route, the waypoint graph, the current target, the pause timer and `self.rng`'s state
  are never sent to any browser, in any message, at any phase.
- `welcome.map` is completely unaffected: it is `self.campus` with `guard_route` already
  stripped (see above), so `web/campusmap.js` (spec 018/026) cannot show the guard even by
  mistake — it never receives him, in the lobby, during a meeting or at any zoom level.

### Browser (`web/render.js`, `web/main.js`, `web/index.html`, `web/sound.js`)
- **`welcome`** gains `guard_vision_radius` (px) and `guard_cone_degrees`, so the browser
  draws the cone at the size the server actually uses.
- **Drawing the guard** (`Render.makeGuard` / a similar pair of functions in `render.js`): an
  original character, our own shapes only — a helmet or cap, a "SECURITY" vest, standing on a
  two-wheeled board with a handle he leans on — created once `state.guard` first appears and
  destroyed when it is absent, exactly like `syncSprites` already does for other players'
  characters.
  - **The cone is wall-clipped, the same way the player's own vision is (spec 010).** The
    darkness code already builds the player's own lit area as a fan of triangles: rays cast
    from the viewer's centre (`castRays`, over `sightEdges` built once per map), each cut
    short by the first sight-blocking wall it meets, with three rays nudged around every
    nearby wall corner so the shadow's edge stays straight, then masked with a Phaser geometry
    mask. The guard's cone is built the exact same way, over the exact same `sightEdges`/wall
    data (no new per-map pre-computation), with only two differences from the player's own
    full-circle fan:
    - the rays are spread only across `facing - guard_cone_degrees / 2` to
      `facing + guard_cone_degrees / 2` (plus the two rays at exactly those edges), not all
      the way round, so the shape is a wedge, not a circle;
    - each ray's reach is capped at `guard_vision_radius`, not the player's own vision radius.

    The fan of triangles from the guard's centre to each pair of neighbouring ray ends is
    filled with a soft, semi-transparent colour and drawn as the cone — so it stops exactly at
    a wall's face and never shows through one, exactly like the player's own lit area already
    does, and needs no new raycasting code, only a narrower, shorter call into the existing
    one. It is visually distinct from the player's own vision rim (a different colour, a
    hard-edged wedge instead of the rim's soft circular fog edge), so the two are never
    mistaken for each other. The wedge is recomputed only when the guard's position or facing
    has moved enough to matter, the same throttle `updateDarkness` already applies to the
    player's own lit area.
    - **Still only the look.** As before, the server's own `sight_clear` check is what
      actually decides a catch; the browser's cone is a visibility-polygon approximation with
      a fixed, finite number of rays (like the player's own), so an extremely thin sliver
      right at a wall's corner could in principle be drawn a hair differently from the
      server's exact yes/no on that one pixel. That is the same limit the player's own vision
      rim already has, not a new one.
  - **Movement:** interpolated between snapshots the same way other players' positions
    already are (`updateOthers`), including snapping instead of gliding on a jump bigger than
    a tick could cover. While driving the whole figure has a small wobble (a Segway leaning
    into its turns); while paused it stands still and only the cone (and a small head/visor
    part of the figure) sweeps with `facing`.
- **Caught:** the instant the phase becomes `meeting` with `reason === "security"` (the same
  place `main.js` already plays `meetingChime` and, for a report, `reportAlarm`):
  - a short new generated alarm sound (`sound.js`, one more entry in `EFFECTS`, no audio
    file, built the same way as the rest);
  - the meeting screen's reason line (which already reads "X found a failed exam on the
    floor." or "X pressed the emergency button.") instead reads "Campus Security caught
    `<name>` handing out a failing exam!", naming the caught player exactly as `called_by`'s
    name is read today — appended as text, never as HTML;
  - the caught player's card in the meeting's player grid (`buildPlayerCard`) gets a
    "Caught by security" stamp, alongside the existing "VOTED" stamp if they have also voted.
  - **An expel that ends the game while seen:** the end screen shows one added short note
    ("Campus Security caught it happening.") when `security_witnessed` is true; nothing else
    about the end screen changes.
- **"How to play"** gains two short lines (a new section, between "Sabotage" and "How each
  side wins"): that a security guard on a Segway patrols the campus on an unpredictable route
  with his own small light, and that an examiner he sees expel inside it is caught and named
  to everyone on the spot.

### Compatibility with specs 018–026
The guard was designed against the campus map before specs 018–026 reshaped it; nothing in
his own rules needed to change, only the data and these notes:
- **Spec 018/026 (the campus map overlay):** unaffected both ways. `web/campusmap.js` reads
  only `welcome.map`'s `tile_size`, `grid`, `decor`, `areas`, `labels`, `meeting_point` and
  `light_switch` — never the live snapshot the guard lives in, and `guard_route` is stripped
  from `welcome.map` itself (see above). The guard never appears on the paper map, in the
  lobby or anywhere else; the own-position marker and own-task markers of specs 018/026 are
  untouched.
- **Spec 019 (playtest fixes):** the longer expel cooldown, `tasks_per_player`, the examiner
  count setting and `ballots` are independent of the guard; none of them change the catch
  check or who can see the guard. A `"security"` meeting uses the same `Meeting.votes`/
  `ballots` machinery as a report or button meeting, so it gets `ballots` for free once voting
  closes.
- **Spec 021 (the Cafeteria and Beach tasks):** both new task stations sit well inside the
  guard's reach — `tray` (41, 12) is 4 tiles from `foodcourt`, `surf` (3, 19) is 4 tiles from
  `beach-mid` — so a guard on patrol can plausibly see either, same as any older task.
- **Spec 022 (hats and colours):** the guard is never a `Player`, so he has no hat and no
  `color`; `"hats"`/`"colors"` in a snapshot never mention him.
- **Spec 024 (print/helpdesk tasks):** no map or area change; nothing to update.
- **Spec 025 (the gym skylight):** purely decorative, drawn below players; the guard can walk
  and be seen past it like any other roofed room, with no interaction.

## Out of scope
- Any control a player has over the guard: no message, no button, no key. He is entirely
  autonomous.
- Any effect of the guard beyond the catch rule above: he cannot be talked to, blocked,
  expelled, voted for, reported, or counted in the player list, the player count or any win
  condition.
- A separate shadow-casting implementation for the cone: it reuses the player's own
  `sightEdges`/`castRays` machinery (spec 010) with a narrower angle and a shorter reach, not
  a new raycaster. A pixel-perfect match with the server's own `sight_clear` is still not
  promised (see "Still only the look" above) — only that the drawing stops at a wall's face
  like the player's own vision does, instead of showing through one.
- Any new sabotage of or by the guard (he is unaffected by the lights in both directions); a
  cooldown, a second guard, or a host setting to turn him off.
- Any change to existing rules (movement, roles, expel, meetings, vision, vents, tasks, the
  lights, colours, win conditions, the campus map overlay) beyond adding the one new check in
  `Game.expel` and the one new, optional key in every snapshot.
- Maps without a `"guard_route"`: the small test maps of earlier specs keep working with no
  guard at all (`self.guard` stays `None` forever); this is accepted, not a bug.

## Done when
- **Tests, written first and shown red before the implementation**, in a new file
  `tests/test_spec027.py`, using a seeded `random.Random` wherever a result depends on it.
  - **Map data:**
    - every waypoint of the campus's `guard_route` lies on a floor tile;
    - every one of its connections is drivable (no tile blocked for a player-sized square
      anywhere along the straight line between the two waypoints);
    - the graph is connected (a breadth-first walk from any waypoint reaches every other);
    - every one of the seven `campus["areas"]` has a waypoint inside its own rectangle (the
      table above gives one for each);
    - a `guard_route` with a waypoint off the floor, an undrivable connection, a connection
      listed on only one end, or a disconnected waypoint is rejected by `validate_campus`
      with a `ValueError`, like the existing decor and label checks.
  - **Movement:**
    - over many ticks the guard's position advances by exactly `GUARD_STEP` per tick while
      driving (`GUARD_SPEED` per second) and never leaves a waypoint-to-waypoint straight line;
    - he is always on a drivable position (never on a blocked tile, never outside the map);
    - at a waypoint with more than one connection he never immediately returns to the one he
      just came from; at a dead end (one connection, e.g. `library` or `auditorium` on the
      real map) he does;
    - with two different seeded `random.Random` instances, the first 10 waypoints chosen
      differ between the two runs;
    - a pause lasts a whole number of seconds between 1 and 3, during which his position does
      not change and his facing sweeps;
    - he does not exist in `LOBBY` or `ENDED`; `Game.step()` does not move him during a
      `MEETING`, and he is exactly where he was once play resumes.
  - **Vision:**
    - a point within `GUARD_VISION_TILES`, within `GUARD_CONE_DEGREES` of his facing and with
      a clear `sight_clear` line to his centre is seen; the same point directly behind him,
      outside the cone's angle, beyond the radius, or behind a wall is not;
    - turning the lights off changes nothing about what the guard sees.
  - **Catch:**
    - an expel with the examiner inside the guard's cone starts a `"security"` meeting whose
      `caught` is that examiner's id;
    - an expel with only the expelled student inside the cone (the examiner outside it) does
      the same;
    - an expel with neither inside the cone proceeds exactly as it does today: no new meeting,
      no `caught`;
    - an expel that itself ends the game (an examiner win), seen by the guard, ends the game
      as usual with `security_witnessed` true on the `ENDED` state; the same expel unseen
      leaves it false;
    - a fellow examiner's role is never part of any state sent because of a catch — only
      `caught`'s one id, and only while that id's role was already due to become public
      anyway (`ENDED`) or through the one explicit `caught` field.
  - **Secrecy:**
    - a living player's snapshot has no `"guard"` key whenever the guard is outside their own
      sight (the same radius, line of sight and lights-out rule as for other players and
      failed exams);
    - a ghost's, a lobby's, a meeting's and the end screen's snapshot includes `"guard"`
      whenever `self.guard` exists, at any distance;
    - no snapshot, at any phase, for any player, ever contains the waypoint graph, the
      guard's current or next waypoint, his pause timer or `self.rng`'s state;
    - player entries stay exactly `{id, name, x, y}` (the guard is never one of them, and
      never counted towards `MAX_PLAYERS` or the player count);
    - `welcome.map` (what `web/campusmap.js` reads) never contains `guard_route` or anything
      else guard-related, on any map.
  - **Cone drawing (structural, like the spec 010/018 identifier checks):** `render.js`'s
    guard-cone function calls the same `castRays` helper the player's own lit area uses
    (not a second, independent raycaster), with an angle span and a reach it computes from
    `guard_cone_degrees`/`guard_vision_radius` rather than the player's own constants.
  - **One WebSocket test:** four clients join and start a round; once a living player's own
    position places the guard in their sight, their own `state` message carries a `"guard"`
    key with the position the server is using at that tick.
  - `uv run pytest` passes. Existing tests stay unchanged: nothing above changes a rule that
    any test before this spec depended on.
- **Manual check with 4 browser windows locally:**
  - the guard drives around the campus on a different-looking route every round, visibly
    faster than a player, stopping here and there to sweep his view before moving on;
  - his cone is drawn, soft and clearly different from a player's own vision, only in a
    window where he is actually in sight, and it visibly stops at a wall instead of bleeding
    through it (stand him facing a corridor corner and confirm the wedge is cut off there);
  - an examiner who expels while the guard's cone covers them, or the student they just
    expelled, is interrupted at once by the "security" meeting: the alarm sounds, the reason
    line names them, and their card carries the "Caught by security" stamp in every window;
  - the same expel just outside the cone changes nothing beyond the ordinary expel;
  - the campus map (C) opened during this never shows the guard, in the lobby or mid-round;
  - the "How to play" handbook mentions him in two lines.
