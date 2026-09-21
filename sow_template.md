# CS 457 Project Statement of Work (SOW) \& Protocol Specification Template

**Student Name:** Jack Birlingmar  
**Date:** 2026-09-21
**Course:** CS 457 - Computer Networks  
**Target Server Domain:** `server.birlingmair.edu`

\---

## 1\. Game Selection \& Scope (Sprint 0)

> Planning is going to be an iterative process through the sprints so you don't have to have all the details now. Focus on big overview concepts. You will be updating the SOW as we plan.
> You have a lot of freedom to choose a game. There are a couple caveats.  

> - It must run in the console. The lab nodes won't be able to handle extensive graphics.
> - It has to be self-contained. You can use a internet-connector to download you code, but because the architecture must run 5 nodes you won't be able to run 
> - You are encouraged to use python, but I'm not going to make it a strict requirement. The instructor and TA's ability to help with C or Rust, etc will be diminished in other languages.

### 1.1 Game Overview

* **Chosen Game:** Battleship
* **Player Capacity:** 2 Players (Simulated via 2 CML Client nodes)
* **Game Summary:** Players compete against each other. They each have a 12x12 board which they can place ships of a certain size, e.g. 1x2, 1x3, 1x4, 1x5, in a vertical or horizontal orientation. Once a player has placed their ships, they participate in a series of rounds where they guess one  coordinate of the other players board, which is either empty (miss) or has a ship on the tile (hit). The game continues until one player's ships tiles are all hit, in which case they lose and the other player wins.

### 1.2 Core Game Rules \& Win/Draw Conditions

* **Turn Mechanics:** At the start of the game, the server selects a random number from 1-10. It then asks the two players to guess the number between 1 and 10. Each player gets exactly only message, the server ignores any additional guesses. The player whose guess is closest to the server's number gets to go first. If both players choose the same number, the server makes a hash of each player's packet, taking the last digit of the hash as the player's number. The number closest to the server's number wins. If there is still a tie, the server goes down the hash until there is a difference in numbers.
Here, the players place their ships on their board. The game starts once both player's ships are all in position.
From there, the first player chooses a tile to shoot at, then the second player chooses. This is one round.
* **Victory Condition:** Once the round starts, it continues until one player's ships' tiles are all "hit." This player loses and the other player wins.
* **Draw/Tie Condition:** The game ends immediately upon all of one's ships being sunk. As this is turn based and sequential within the round, this means exactly one player can get to the winning condition at a time. There will not be any draws.

\---

## 2\. Application-Layer Messaging Protocol Blueprint (Sprint 1 Deliverable)

### 2.1 Message Transport \& Serialization Format

* **Transport Protocol:** TCP
* **Serialization Format:** \[JSON / Fixed-Header Binary / Delimited Text]
* **Framing Mechanism:** \[e.g., Newline-delimited (`\\n`) JSON payloads OR 4-byte big-endian length prefix]

### 2.2 Message Schema Definitions

#### Message Types:

1. `CONNECT` (Client -> Server): Request to join the game room.
2. `LOBBY\_WAIT` (Server -> Client): Notification that server is waiting for Player 2.
3. `GAME\_START` (Server -> Clients): Game initiated, assigns roles (e.g. Player X vs Player O).
4. `MOVE` (Client -> Server): Player action (e.g., cell coordinates or answer choice).
5. `STATE\_UPDATE` (Server -> Clients): Broadcast current game board / state and active player turn.
6. `GAME\_OVER` (Server -> Clients): Victory / Draw notification with final scores.
7. `ERROR` (Server -> Client): Invalid move or malformed packet error.

#### Example JSON Protocol Schema:

```json
{
  "msg\_type": "MOVE",
  "player\_id": "Player\_1",
  "payload": {
    "row": 0,
    "col": 2
  },
  "timestamp": 1727000000
}
```

\---

### 2.3 Game State Machine (FSM) Design (Sprint 1 Deliverable)

* **State Transitions:** Detail state flow: `INIT` -> `WAITING\_FOR\_PLAYERS` -> `PLAYER\_TURN` -> `EVALUATE\_MOVE` -> `CHECK\_WIN\_DRAW` -> `GAME\_OVER` -> `CLEANUP`.

\---

## 3\. Game Behavior \& Server Concurrency Architecture (Sprint 2 Deliverable)

### 3.1 Server Concurrency Strategy

* **Architecture Choice:** \[Multi-Threading (`threading.Thread`) OR Non-blocking I/O multiplexing (`select.select` / `selectors`)]
* **Synchronization Logic:** Explain how shared game state and client list are thread-safe (e.g. `threading.Lock`) to prevent race conditions during turn processing.

### 3.2 State \& Score Synchronization Across Clients

* **Turn Enforcement:** Detail how the server validates active player ID before processing moves and broadcasts updated turn notifications to all clients.
* **Score \& Board Synchronization:** Describe how state broadcasts keep client screens synchronized in real time.

\---

## 4\. Coding \& AI Implementation Plan (Sprint 3)

* **Permitted AI Tools:** \[e.g., GitHub Copilot, ChatGPT, Claude]
* **AI Prompting \& Constraint Strategy:** Explain how you will constrain AI models to generate code (in Python or your chosen language) that adheres strictly to the protocol blueprint and FSM designed in Sprints 1 \& 2.
* **Implementation Risk Management:** Detail your plan to leverage past programming experience and manage time to ensure code completion on schedule.

\---

## 5\. CML Multi-Subnet Topology \& Wireshark Deployment Plan (Sprint 4 \& 5 Deliverable)

> For now you can use the topology below. We may update this when we get to defining subnets.

### 5.1 Subnet \& Router Design

* **Subnet A (Client 1):** `192.168.10.0/24` (Interface `Gi0/1` on Router R1)
* **Subnet B (Client 2):** `192.168.11.0/24` (Interface `Gi0/2` on Router R1)
* **Subnet C (Game Server):** `192.168.20.0/24` (Interface `Gi0/1` on Router R2)
* **Router Backbone:** `10.0.0.0/30` (Interface `Gi0/0` on R1 <-> `Gi0/0` on R2)

### 5.2 DHCP Pools \& DNS Configuration Plan

* **Router R1 DHCP Pool 1 (`CLIENT1\_POOL`):** Leases `192.168.10.10` - `192.168.10.50`, gateway `192.168.10.1`, DNS `10.0.0.2`.
* **Router R1 DHCP Pool 2 (`CLIENT2\_POOL`):** Leases `192.168.11.10` - `192.168.11.50`, gateway `192.168.11.1`, DNS `10.0.0.2`.
* **Router R2 Authoritative DNS:** Configured with `ip dns server` and static host mapping `server.\[yourlastname].edu` -> `192.168.20.100`.

### 5.3 Deployment Strategy \& Wireshark Trace Capture

* **CML Deployment Strategy:** Deploy `server.py` onto Subnet C node (`192.168.20.100`) behind Router R2, and `client.py` onto Subnet A and Subnet B nodes behind Router R1.
* **Cisco Infrastructure Configuration:** Router R1 DHCP pools (`CLIENT1\_POOL`, `CLIENT2\_POOL`) and Router R2 authoritative DNS (`ip host server.\[lastname].edu 192.168.20.100`).
* **Wireshark Trace Capture Plan:** Capture DHCP DORA exchange (`dhcp\_negotiation.pcap`) and DNS query/response resolution (`dns\_lookup.pcap`).

