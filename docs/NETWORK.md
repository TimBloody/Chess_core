# Network play (LAN host/guest)

Chess Core plays over the local network with an **authoritative host**. One client
opens a TCP port; the second client connects. The host’s `GameServer` decides
whether a turn is legal. Clients only highlight moves locally; a move is not
committed until `STATE_SYNC` arrives from the server.

Protocol version **1** must match, and both programs must be the same package
version (`chess_core.__version__`, currently `0.0.1`). A mismatch is rejected
at handshake (`version_mismatch` / `protocol_mismatch`).

## How to play on a LAN (Windows)

1. Install the same Chess Core build on both devices.
2. Put both devices on the same subnet (disable Wi‑Fi guest/AP isolation).
3. On the host: pick the mode in the sidebar, open **Сеть**, set port `8765`
   (default), click **Создать партию**. The window shows LAN IPv4 addresses.
4. Allow inbound TCP on that port in Windows Firewall (or allow Python).
   Example (PowerShell as Administrator, port 8765):

   ```powershell
   New-NetFirewallRule -DisplayName "Chess Core LAN" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow
   ```

5. On the guest: **Сеть**, enter the host IP, same port, **Подключиться**.
6. The host sits as White, the guest as Black. Wait until the host status
   says the opponent is connected before moving.

## What the server rejects

The session id is taken from the TCP connection after `HELLO`, never from a
client-supplied field on `SUBMIT_TURN`.

Each submitted turn is dropped unless all of the following hold:

- the connection completed `HELLO` / `HELLO_OK`
- `protocol == 1` and `package` equals the host’s package version
- `turn.side` is the seated colour of that connection
- it is that colour’s turn (`side_to_move`)
- `client_revision` equals the server revision (stale packets are rejected)
- the **complete** `Turn` is in the legal set for the current mode (not just
  the first `MoveAction`) — duck chess requires move + duck, drops must be
  legal, and you cannot move the opponent’s pieces
- no undo request is waiting for an answer
- the room has two seats; a third client gets `game_full`

Oversized or invalid JSON lines close the socket.

## Protocol

JSON lines (`{"kind":"...","payload":{...}}\n`) on TCP, default bind
`0.0.0.0:8765`, max frame 1 MiB.

| Kind | Direction | Role |
| --- | --- | --- |
| `HELLO` | guest → host | `protocol`, `package` |
| `HELLO_OK` | host → guest | `session_id`, `side`, `mode_id`, `game_id` |
| `HELLO_REJECTED` | host → guest | `version_mismatch`, `protocol_mismatch`, `game_full`, `bad_hello` |
| `STATE_SYNC` | host → both | position, revision, optional clock, last committed turn |
| `SUBMIT_TURN` | client → host | `turn` + `client_revision` |
| `TURN_REJECTED` | host → client | reason + expected revision |
| `UNDO_REQUEST` / `UNDO_PENDING` / `UNDO_DECISION` / `UNDO_RESOLVED` | both | opponent must confirm; clocks keep running |
| `OPPONENT_LEFT` | host → remaining | peer disconnected |

The host UI uses the same `GameServer` in-process (White). It cannot bypass
legality: host clicks also go through `apply_remote_turn`.

Undo (`Ctrl+Z`) asks the opponent; it does not roll back locally until
`UNDO_RESOLVED` with `accepted=true`. Server revision still increases.

## Dedicated machine later

`TcpGameServer` has no Qt dependency. The same module can later listen on a
Kali VM (`0.0.0.0`) while two GUI clients join; both seats would then be TCP.
This UI step uses **client-host** only: one GUI listens, one GUI connects.
